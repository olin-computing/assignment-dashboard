"""
Update the database.

This depends on the database already having been created.

The code is meant to be run as a script.
It's written in notebook format rather than packaged into a function that can be run on demand.
See the README for a discussion.
"""

import base64
import os
from collections import namedtuple
from datetime import datetime, timedelta

import arrow
from github import Github
# main
#
from sqlalchemy.orm import joinedload

from .database import session
from .models import Commit, FileCommit, FileContent, Repo, User
from .sql_alchemy_helpers import find_or_create, update_instance, upsert_all

# globals
#

REPO_LIMIT = int(os.environ.get('REPO_LIMIT', 0))
COMMIT_LIMIT = int(os.environ.get('COMMIT_LIMIT', 0))
USER_FILTER = list(filter(None, os.environ.get('USER_FILTER', '').split(',')))

REPROCESS_COMMITS = os.environ.get('REPROCESS_COMMITS', 'False') not in ('False', '0')
REPORT_FILE_SHAS = None  # e.g. 'day3_reading_journal.ipynb'

GITHUB_API_TOKEN = os.environ.get('GITHUB_API_TOKEN', None)
assert GITHUB_API_TOKEN

gh = Github(GITHUB_API_TOKEN)


# helpers
#

RepoCommitFile = namedtuple('RepoCommitItem', 'commit file')


def unique_by(iter):
    """Return a list of items with distinct keys. iter yields (item, key)."""
    # return a list rather than a set, because items might not be hashable
    return list({key: item for item, key in iter}.values())


def get_file_content(repo, blob_url):
    blob = repo.get_git_blob(blob_url.split('/')[-1])
    content = blob.content
    if blob.encoding == 'base64':
        content = base64.b64decode(content)
    return content


def is_downloadable_path(path):
    return any(path.endswith(suffix) for suffix in ['.ipynb', '.py', '.md', '.txt'])


def parse_git_datetime(s):
    return arrow.get(s, 'ddd, DD MMM YYYY HH:mm:ss ZZZ').datetime


def own_commit(repo, commit):
    """Return true iff commit appears to be from the repo owner."""
    return not commit.author or commit.author == repo.owner or commit.author.login == 'web-flow'


# read the repos
#

def get_instructor_logins(source_repo):
    print('Reading organization members from GitHub')
    organization_name = source_repo.full_name.split('/')[0]
    return {user.login
            for team in gh.get_organization(organization_name).get_teams()
            for user in team.get_members()}


def get_forks(source_repo, ignore_logins=None):
    if ignore_logins is None:
        ignore_logins = get_instructor_logins(source_repo)

    print('Reading repos from GitHub')
    repos = [repo for repo in source_repo.get_forks()
             if repo.owner.login not in ignore_logins]

    return repos


# read and update students
#

user_instance_map = {}


def save_users(users, role='student', verbose=True):
    if verbose:
        print('Updating students in database')
    saved_instances = {instance.login: instance
                       for instance in session.query(User).filter(User.login.in_(user.login for user in users))}
    for user in users:
        attrs = dict(login=user.login,
                     avatar_url=user.avatar_url or repo.owner.gravatar_url,
                     role=role,
                     **dict(fullname=user.name) if user.name else {})

        instance = saved_instances.get(user.login, None)
        if instance:
            update_instance(instance, attrs)
        else:
            instance = User(**attrs)
        session.add(instance)

    session.commit()

    user_instances = list(session.query(User).filter(User.login.in_([user.login for user in users])))
    user_instance_map.update({instance.login: instance for instance in user_instances})  # FIXME there's surely some way to do this within the ORM


def get_user_instance(user):
    return user_instance_map[user.login]

# update repos
#

repo_instance_map = None


def get_repo_instance(repo):
    global repo_instance_map
    if not repo_instance_map:
        repo_instance_map = {(instance.owner_id, instance.name): instance for instance in session.query(Repo)}
    owner = get_user_instance(repo.owner)
    return repo_instance_map[owner.id, repo.name]


def save_repos(source_repo, repos):
    print('Updating %d repos in database' % len(repos))
    source_repo_instance = find_or_create(session, Repo, owner_id=get_user_instance(source_repo.owner).id, name=source_repo.name)
    session.commit()
    assert source_repo_instance.id

    repo_instances = [Repo(owner_id=user_instance_map[repo.owner.login].id, name=repo.name, source_id=source_repo_instance.id)
                      for repo in repos
                      if repo != source_repo]
    upsert_all(session, [source_repo_instance] + repo_instances, Repo.owner_id, Repo.name)
    session.commit()


# record file commits
#

def gh2db_repo(gh_repo):
    owner_login, repo_name = gh_repo.full_name.split('/')
    instance = (session.query(Repo)
                .join(Repo.owner)
                .filter(User.login == owner_login)
                .filter(Repo.name == repo_name)).first()
    assert instance
    return instance

def get_new_repo_commits(repo, commit_limit=None):
    repo_instance = gh2db_repo(repo)

    saved_commits = set() if REPROCESS_COMMITS else get_repo_instance(repo).commits
    saved_commit_shas = {commit.sha for commit in saved_commits}

    def get_commit_kwargs(repo):
        since = None
        if REPROCESS_COMMITS:
            pass
        elif repo_instance.refreshed_at:
            since = repo_instance.refreshed_at + timedelta(days=-1)
        else:
            date_tuple = (session.query(FileCommit.mod_time).
                          filter(FileCommit.repo_id == Repo.id).
                          filter(Repo.owner_id == User.id).
                          filter(User.login == repo.owner.login).
                          order_by(FileCommit.mod_time.desc())).first()
            if date_tuple:
                since = date_tuple[0] + timedelta(weeks=-1)

        args = {}
        if since:
            args['since'] = since
        return args

    repo_commits = [commit
                    for commit in repo.get_commits(**get_commit_kwargs(repo))
                    if commit.sha not in saved_commit_shas]

    if commit_limit:
        repo_commits = repo_commits[:commit_limit]

    if REPORT_FILE_SHAS:
        print('commits for %s:' % REPORT_FILE_SHAS,
              [item.sha
               for commit in reversed(repo_commits)
               for item in commit.files
               if item.filename == REPORT_FILE_SHAS])

    messages = []
    if repo_commits:
        messages.append("processing %d new commits" % len(repo_commits))
    if saved_commits:
        messages.append("ignoring %d previous commits" % len(saved_commits))
    if messages:
        print("; ".join(messages))

    return repo_commits


def get_file_commit_recs(repo, repo_commits, all_commits=False):
    file_commit_recs = unique_by(
        (RepoCommitFile(commit, item), (repo.full_name, item.filename))
        for commit in reversed(repo_commits)
        if all_commits or own_commit(repo, commit)
        for item in commit.files
        if item.sha)

    print('processing %d file commits' % len(file_commit_recs))

    if REPORT_FILE_SHAS:
        print('filtered commits for %s:' % REPORT_FILE_SHAS,
              [item.file.sha for item in file_commit_recs if item.file.filename == REPORT_FILE_SHAS])

    return file_commit_recs


def download_files(repo, repo_commits, file_commit_recs):
    incoming_file_shas = {item.file.sha for item in file_commit_recs}
    if not incoming_file_shas:
        return

    db_file_content_shas = {sha for sha, in session.query(FileContent.sha).filter(FileContent.sha.in_(incoming_file_shas))}
    missing_shas = incoming_file_shas - db_file_content_shas
    if not missing_shas:
        return

    print('downloading %d files' % len(missing_shas))

    download_commits = ((commit, {item.file.filename
                                  for item in file_commit_recs if item.commit == commit
                                  if item.file.sha not in db_file_content_shas})
                        for commit in repo_commits)

    download_commits = ((commit, paths)
                        for (commit, paths) in download_commits
                        if paths)

    seen = set()
    for commit, paths in download_commits:
        items = [item
                 for item in repo.get_git_tree(repo.get_commits()[0].sha, recursive=True).tree
                 if item.path in paths]
        for item in items:
            if item.sha in seen:
                continue
            print('downloading %s/%s (sha=%s)' % (repo.full_name, item.path, item.sha))
            content = get_file_content(repo, item.url) if is_downloadable_path(item.path) else None
            fc = FileContent(sha=item.sha, content=content)
            session.add(fc)
            session.commit()
            seen |= {item.sha}


def update_file_commits(repo, file_commit_recs):
    file_commits = [FileCommit(repo_id=get_repo_instance(repo).id,
                               path=item.file.filename,
                               mod_time=parse_git_datetime(item.commit.last_modified),
                               sha=item.file.sha)
                    for item in file_commit_recs]
    upsert_all(session, file_commits, FileCommit.repo_id, FileCommit.path)
    session.commit()


# record repo commits
#

def record_repo_commits(repo, repo_commits, timestamp):
    repo_instance = gh2db_repo(repo)
    repo_instance.refreshed_at = timestamp

    commit_instances = [Commit(repo_id=get_repo_instance(repo).id,
                               sha=commit.sha,
                               commit_date=parse_git_datetime(commit.last_modified))
                        for commit in repo_commits]
    upsert_all(session, commit_instances, Commit.repo_id, Commit.sha)
    session.commit()


def update_repo_files(repo, all_commits=False, commit_limit=None):
    timestamp = datetime.utcnow()
    repo_commits = get_new_repo_commits(repo, commit_limit=COMMIT_LIMIT)
    file_commit_recs = get_file_commit_recs(repo, repo_commits, all_commits=all_commits)
    if repo_commits:
        download_files(repo, repo_commits, file_commit_recs)
        update_file_commits(repo, file_commit_recs)
    record_repo_commits(repo, repo_commits, timestamp)


def add_repo(repo_name):
    owner_login, shortname = repo_name.split('/')
    instance = (session.query(Repo)
                .join(Repo.owner)
                .filter(User.login == owner_login)
                .filter(Repo.name == shortname)).first()
    assert not instance.source_id
    update_db(repo_name)


def update_db(source_repo_name):
    source_repo = gh.get_repo(source_repo_name)
    repo = session.query(Repo).filter(Repo.source_id.is_(None)).all()
    forks = get_forks(source_repo)
    if USER_FILTER:
        repos = [repo for repo in repos if repo.owner.login in USER_FILTER]

    save_users([source_repo.owner], role='organization', verbose=False)
    save_users([repo.owner for repo in forks], role='student')
    save_repos(source_repo, forks)

    repos = [source_repo] + forks
    if REPO_LIMIT:
        repos = repos[:REPO_LIMIT]

    for i, repo in enumerate(repos):
        print("Updating %s (%d/%d)" % (repo.full_name, i + 1, len(repos)))
        update_repo_files(repo, all_commits=(repo == source_repo), commit_limit=COMMIT_LIMIT)
