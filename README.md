# Assignment Dashboard

[![Updates](https://pyup.io/repos/github/olin-computing/assignment-dashboard/shield.svg)](https://pyup.io/repos/github/olin-computing/assignment-dashboard/)
[![Python 3](https://pyup.io/repos/github/olin-computing/assignment-dashboard/python-3-shield.svg)](https://pyup.io/repos/github/olin-computing/assignment-dashboard/)
[![Requirements Status](https://requires.io/github/olin-computing/assignment-dashboard/requirements.svg?branch=master)](https://requires.io/github/olin-computing/assignment-dashboard/requirements/?branch=master)
[![Codacy Badge](https://api.codacy.com/project/badge/Grade/bc6108c6014640119f948d0d371dde9d)](https://www.codacy.com/app/steele/assignment-dashboard?utm_source=github.com&amp;utm_medium=referral&amp;utm_content=olin-computing/assignment-dashboard&amp;utm_campaign=Badge_Grade)

Assignment Dashboard is a [Flask](http://flask.pocoo.org) web application that displays [Jupyter notebook files](http://jupyter.org) within a GitHub "assignment" repository, and their status within each forked "student" repository.

The app displays whether files are present in the student repository; if so, whether they have been changed, and whether they are valid Jupyter notebook files. Student repositories and files are linked to GitHub.

<a href=""./docs/images/repo.jpeg"><img src="./docs/images/repo.jpeg" width="640"/></a>

Clicking on an assignment title displays a collated notebook, with all student answers collected beneath each prompt.

<a href=""./docs/images/collated.jpeg"><img src="./docs/images/collated.jpeg" width="320"/></a>

The app also displays additional information about each assignment.

<a href=""./docs/images/answer-table><img src="./docs/images/answer-table.jpeg" width="320"/></a>

## Status

The application does not use authentication, so it should not be run on the open web or in a shared location. (Technically it does not expose any information that is not openly available from the GitHub web interface and API, but it makes this information easier to find.)

## Setup

These instructions use Docker.
See [here](./docs/install-without-docker.md) for alternate instructions that don't use Docker.

![](docs/setup.png)

... generated by [Railroad Diagram Generator](http://www.bottlecaps.de/rr/ui)

Do these once:

### 1. Install docker-compose

For example: `pip install docker-compose`; or one of the installers [here](https://docs.docker.com/compose/install/).

### 2. Create a GitHub personal API token

[Create a GitHub personal API token](https://github.com/blog/1509-personal-api-tokens).
Set the `GITHUB_API_TOKEN` environment variable to this value.

### 3. Initialize the database

    docker-compose run web initdb

This creates a database in `data/database.db`.

It will take a while to run, as Docker creates the application image.

If you subsequently need to run it again in order to reset the database, it will use this existing image.

### 4. Add an assignment repository

    $ docker-compose run web add_repo repo_owner/repo_name

Add a repository to the database, and download its information from GitHub.

## Usage

These instructions use Docker.
See [here](./docs/install-without-docker.md) for alternate instructions that don't use Docker.

The admin tasks update the project database from GitHub.
The web application browses the data in this database.

![](docs/use.png)

... generated by [Railroad Diagram Generator](http://www.bottlecaps.de/rr/ui)

### Admin Tasks

#### Update the database

    $ docker-compose run web updatedb

Update the application database with new users and commits from GitHub.

#### Set User Names

    $ docker-compose run web set_usernames usernames.csv

Update user names in the database from the rows in `usernames.csv`.

`usernames.csv` should be a CSV file with a column named "name" or "username",
and a column that contains the string "git" (or mixed-case versions of these
strings).

Subsequent execution of `updatedb` will replace usernames in the database
by the user's GitHub name if the GitHub name is not empty.


### Run the Web Application

    $ docker-compose up

Then browse to <http://localhost:5000>.


File bugs and enhancement requests [here](https://github.com/osteele/assignment-dashboard/issues).


## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines.


## Acknowledgments

The notebook collation code is derived from original work ([paulruvolo/SoftDesSp16Prep](https://github.com/paulruvolo/SoftDesSp16Prep)) by Paul Ruvolo at Olin College, further modified at [osteele/assignment-tools](https://github.com/osteele/assignment-tools).
