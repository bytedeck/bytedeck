FROM python:3.5-slim

#### For development within the container in VS Code ##
# https://code.visualstudio.com/docs/remote/containers
# https://github.com/Microsoft/vscode-remote-try-python

# Configure apt
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get -y install --no-install-recommends apt-utils 2>&1

RUN pip install pylint

# Install git, process tools, lsb-release (common in install instructions for CLIs)
RUN apt-get install -y git procps lsb-release

# Install any missing dependencies for enhanced language service
RUN apt-get install -y libicu[0-9][0-9]

# Install uwsgi
RUN apt-get install -y build-essential
RUN pip install uwsgi

######################################################

# Set environment variables 

# Don't create .pyc files (why don't we want these?)
ENV PYTHONDONTWRITEBYTECODE 1  
# Prevent docker from buffering console output
ENV PYTHONUNBUFFERED 1

ENV POSTGRES_HOST "db"

ENV REDIS_HOST "redis"

# Set working directory for subsequent RUN ADD COPY CMD instructions
RUN mkdir /app
WORKDIR /app

# copy the entire project into the app directory.
# should we just copy over the code in src/ and requirements.txt?
COPY . /app/

# Install our dependancies (currently installing on the base image, not in venv)
RUN pip install -r requirements.txt

# The port
EXPOSE 8000

#### More from https://github.com/Microsoft/vscode-remote-try-python ##

# Clean up
RUN apt-get autoremove -y \
    && apt-get clean -y \
    && rm -rf /var/lib/apt/lists/*
ENV DEBIAN_FRONTEND=dialog

# Set the default shell to bash rather than sh
ENV SHELL /bin/bash

#######################################################################

# RUN adduser --disabled-password appuser
# USER appuser
