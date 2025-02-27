FROM python:3.10-slim

#### For development within the container in VS Code ##
# https://code.visualstudio.com/docs/remote/containers
# https://github.com/Microsoft/vscode-remote-try-python

# Allow for an orderly, graceful shutdown of services
# Specifically in our case:
# 1. give coverage a chance to send its report to coveralls.io
# 2. allow celerybeat to delete its pid file (does this actually happen?)
STOPSIGNAL SIGINT

# Configure apt
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get -y install --no-install-recommends apt-utils 2>&1

RUN pip install pylint

# Install git, process tools, lsb-release (common in install instructions for CLIs)
RUN apt-get install -y git procps lsb-release

# Required for psycopg2: https://github.com/psycopg/psycopg2/issues/699
RUN apt-get install -y --no-install-recommends libpq-dev

# Install any missing dependencies for enhanced language service
RUN apt-get install -y libicu[0-9][0-9]

# Install uwsgi
RUN apt-get install -y build-essential

#https://stackoverflow.com/questions/21669354/rebuild-uwsgi-with-pcre-support
RUN apt-get install -y libpcre3 libpcre3-dev

RUN python3 -m pip install --upgrade pip

# Why isn't this in requirements?!  Move it there?
RUN python3 -m pip install uwsgi

# Clean up
RUN apt-get autoremove -y \
    && apt-get clean -y \
    && rm -rf /var/lib/apt/lists/*
ENV DEBIAN_FRONTEND=dialog

# Set the default shell to bash rather than sh
ENV SHELL=/bin/bash

# Set environment variables

# Don't create .pyc files (why don't we want these?)
ENV PYTHONDONTWRITEBYTECODE=1
# Prevent docker from buffering console output
ENV PYTHONUNBUFFERED=1


# Install python requirements
# Docker only rebuilds when there are changes to these files
# https://docs.docker.com/develop/develop-images/dockerfile_best-practices/
COPY ./requirements-production.txt requirements-production.txt
COPY ./requirements.txt requirements.txt
RUN python3 -m pip install -r requirements.txt
######################################################

# Enable below when uwsgi-nginx uses unix sock
# RUN mkdir /bytedeck-volume
# ARG WUID
# ARG WGID
# RUN chown -R ${WUID}:${WGID} /bytedeck-volume

# Set working directory for subsequent RUN ADD COPY CMD instructions
COPY . /app/
WORKDIR /app/


#### More from https://github.com/Microsoft/vscode-remote-try-python ##

#######################################################################

# RUN adduser --disabled-password appuser
# USER appuser
