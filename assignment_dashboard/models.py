import os

from sqlalchemy import (CheckConstraint, Column, DateTime, Enum, ForeignKey, Integer, String, Table, Text,
                        UniqueConstraint)
from sqlalchemy.orm import backref, deferred, relationship

from .database import Base

DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///database.db')
MD5_HASH_CONSTRAINT = CheckConstraint('length(md5) = 32')
SHA_HASH_CONSTRAINT = CheckConstraint('length(sha) = 40')


def base__repr__(self):
    def short_enough(v):
        if not isinstance(v, str):
            return True
        return len(v) < 100

    cols = [c.name for c in self.__table__.columns]
    attrs = {k: getattr(self, k) for k in cols}
    return "<{} {})>".format(
        self.__class__.__name__,
        ', '.join("%s=%r" % (k, v)
                  for k, v in attrs.items()
                  if v and short_enough(v)))
Base.__repr__ = base__repr__


# These mirror GitHub
#


class FileCommit(Base):
    __tablename__ = 'file_commit'
    __table_args__ = (UniqueConstraint('repo_id', 'path'),)

    id = Column(Integer, primary_key=True)
    repo_id = Column(Integer, ForeignKey('repo.id'), nullable=False, index=True)
    path = Column(String(1024), nullable=False)
    mod_time = Column(DateTime, nullable=False)  # de-normalized from the related commit
    sha = Column(String(40), ForeignKey('file_content.sha'), SHA_HASH_CONSTRAINT, nullable=False)

    file_content = relationship('FileContent', backref='files')
    repo = relationship('Repo', backref='files')

    @property
    def content(self):
        return self.file_content.content


class FileContent(Base):
    __tablename__ = 'file_content'

    id = Column(Integer, primary_key=True)
    sha = Column(String(40), SHA_HASH_CONSTRAINT, nullable=False, index=True, unique=True)
    content_type = Column(String(40), nullable=True)
    content = deferred(Column(Text, nullable=True))

organization_users_table = Table(
    'organization_users', Base.metadata, Column('organization_id', ForeignKey('user.id'), primary_key=True),
    Column('user_id', ForeignKey('user.id'), primary_key=True),
)


class User(Base):
    __tablename__ = 'user'

    id = Column(Integer, primary_key=True)
    login = Column(String(100), nullable=False, index=True, unique=True)
    fullname = Column(String(100))
    avatar_url = Column(String(1024))
    gh_type = Column(Enum('Organization', 'User'))

    role = Column(Enum('student', 'instructor', 'organization'), nullable=False, server_default='student')
    status = Column(Enum('enrolled', 'waitlisted', 'dropped'))
    repos = relationship('Repo', backref='owner')

    members = relationship('User', secondary=organization_users_table,
                           primaryjoin=id == organization_users_table.c.user_id,
                           secondaryjoin=id == organization_users_table.c.organization_id,
                           back_populates='organizations')
    organizations = relationship('User', secondary=organization_users_table,
                                 primaryjoin=id == organization_users_table.c.organization_id,
                                 secondaryjoin=id == organization_users_table.c.user_id,
                                 back_populates='members')


class Repo(Base):
    __tablename__ = 'repo'
    __table_args__ = (UniqueConstraint('owner_id', 'name'),)

    id = Column(Integer, primary_key=True)
    owner_id = Column(Integer, ForeignKey('user.id'), nullable=False)
    source_id = Column(Integer, ForeignKey('repo.id'), nullable=True)
    name = Column(String(100), nullable=False)
    refreshed_at = Column(DateTime)

    source = relationship('Repo', remote_side=[id])
    forks = relationship('Repo')
    commits = relationship('Commit', backref='repo')

    @property
    def full_name(self):
        return '/'.join([self.owner.login, self.name])

    @property
    def html_url(self):
        return "https://github.com/%s/%s" % (self.owner.login, self.name)

    @property
    def is_fork(self):
        return bool(self.source_id)

    @property
    def is_source(self):
        return not self.source_id


class Commit(Base):
    __tablename__ = 'commit'
    __table_args__ = (UniqueConstraint('repo_id', 'sha'),)

    id = Column(Integer, primary_key=True)
    repo_id = Column(Integer, ForeignKey('repo.id'), nullable=False, index=True)
    sha = Column(String(40), SHA_HASH_CONSTRAINT, nullable=False, index=True)
    commit_date = Column(DateTime, nullable=False)


# Assignment-related models
#

class Assignment(Base):
    """A single assignment file within a repo that contains multiple assignments, one per file."""

    __tablename__ = 'assignment'
    __table_args__ = (UniqueConstraint('repo_id', 'path'),)

    id = Column(Integer, primary_key=True)
    repo_id = Column(Integer, ForeignKey('repo.id'), nullable=False, index=True)
    path = Column(String(1024), nullable=False)
    name = Column(String(128), nullable=False)
    nb_content = deferred(Column(Text, nullable=True))
    md5 = Column(String(32), MD5_HASH_CONSTRAINT, nullable=True)

    repo = relationship('Repo', backref=backref('assignments', cascade='all, delete-orphan'))
    # file = relationship('FileContent',
    #                     primaryjoin=and_(Assignment.repo_id == FileCommit.repo_id, Assignment.path == FileCommit.path),
    #                     foreign_keys=[repo_id, path])

    @property
    def content(self):
        # FIXME get `file` relationship above working; replace this query by that
        from sqlalchemy.orm.session import object_session
        fc = object_session(self).query(FileCommit). \
            filter(FileCommit.repo_id). \
            filter(self.repo_id and FileCommit.path == self.path). \
            first()
        return fc.content


class AssignmentQuestion(Base):
    """A question within an assignment."""

    __tablename__ = 'assignment_question'
    __table_args__ = (UniqueConstraint('assignment_id', 'position'),)

    id = Column(Integer, primary_key=True)
    assignment_id = Column(Integer, ForeignKey('assignment.id'), nullable=False)
    position = Column(Integer, nullable=False)
    question_name = Column(String(1024))
    notebook_data = deferred(Column(Text, nullable=True))

    assignment = relationship('Assignment', backref=backref('questions', cascade='all, delete-orphan'))


class AssignmentQuestionResponse(Base):
    __tablename__ = 'assignment_question_response'
    __table_args__ = (UniqueConstraint('assignment_question_id', 'user_id'),)

    id = Column(Integer, primary_key=True)
    assignment_question_id = Column(Integer, ForeignKey('assignment_question.id'), nullable=False)
    user_id = Column(Integer, ForeignKey('user.id'), nullable=False)
    status = Column(String(20))
    notebook_data = deferred(Column(Text, nullable=True))

    question = relationship('AssignmentQuestion', backref=backref('responses', cascade='all, delete-orphan'))
    user = relationship('User')
