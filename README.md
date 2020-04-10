LMS for Timberline Secondary School's Digital Hackerspace

[![Build Status](https://travis-ci.org/timberline-secondary/hackerspace.svg?branch=develop)](https://travis-ci.org/timberline-secondary/hackerspace)
[![Total alerts](https://img.shields.io/lgtm/alerts/g/timberline-secondary/hackerspace.svg?logo=lgtm&logoWidth=18)](https://lgtm.com/projects/g/timberline-secondary/hackerspace/alerts/)
i
# Hackerspace development environment installation

## Installing and running the project

### Installing Tools

Although the hackerspace uses several tools, you only need to set up a two of them thanks to docker!

The instructions below will help you get the hackerspace running using [docker](https://www.docker.com/), and then help you set up a development environment with [VS Code](https://code.visualstudio.com/).

The instructions assume you are using Ubuntu (or another Debian based linux distro), although it is possible to get it working anywhere you can install docker.

#### Installing Docker

Follow the instructions the for installing Docker CE (community edition, i.e. free edition) using the repository:
https://docs.docker.com/install/linux/docker-ce/ubuntu/#install-using-the-repository

By the end, you should be able to run docker's test image:

`$ sudo docker run hello-world`

#### Install docker-compose
`sudo apt install docker-compose`

Add yourself to the docker group:

`sudo usermod -aG docker $USER`


### Getting the Code

#### Fork the repository

1. Create a Github account.
2. Go to https://github.com/timberline-secondary/hackerspace
3. Click the "Fork" button on the top right corner. 
4. This will allow you to have your own copy of the project on your GitHub account.

#### Clone your fork

1. Open the directory where you want to put the code.  I like to create a new directory for my code projects called Developer: `mkdir ~/Developer`
2. Move into the parent directory of the project: `cd ~/Developer`
3. Go to your forked repository in github
4. Click "Clone or download" and copy the url, then paste it into the command: `git clone yoururlhere`
5. This will download the project into ~/Developer/hackerspace/

#### Initial setup
This will create your docker containers and initialize the database by running migrations and creating some inital data that is required:

1. Open a terminal
2. Move into the project directory: `cd ~/Developer/hackerspace`
3. Build the containers: `docker-compose build`
4. Start 4 of the containers (the database, redis, celery, and celery-beat):
`docker-compose up db redis celery celery-beat`
5. Keep an eye out for errors as it goes through each step *(currently celery-beat is not working, but you can leave that one off for now)
6. Initialize the database with some key data: `bash init_public_schema.sh`
7. Try running the app locally in a new terminal with: `./src/manage.py runserver`
8. You should get a 404 page (until we create a lnading page) at http://localhost:8000
9. But you should be able to log in to the admin site!  http://http://localhost:8000/admin/
   - user: admin
   - password: hellonepal

### Creating a Tenant
If everything has worked so far, you should now be able to create your own hackerspace website as a new tenant:

1. Go to django admin at http://localhost:8000/admin/ (this is known as the Public tenant, it's where we can control all the other sites or tenants)
2. In the Tenants app near the bottom, create a new tenant by giving it a name, for example: `hackerspace`
3. This will create a new site at http://hackerspace.localhost:8000 go there and log in
   - user: admin
   - password: admin1234 (this is defined in TENANT_DEFAULT_SUPERUSER_PASSWORD in settings/local.py)
4. Now you should be in your own Hackerspace site!  
5. If you would like to stop the project, use `Ctrl + C` in the command lines, then wait for each of the containers to stop.

## Setting up a VS Code development environment

(UNTESTED)

1. Install [Visual Studio Code](https://code.visualstudio.com/docs/setup/setup-overview): 
2. Hit Ctrl + ` (back tick, above the tab key) to open a terminal in VS Code
3. Install the following extensions:
   1. Required: Python (Microsoft)
   3. Optional: Django Template (bibhasdn)
   4. Optional: ESLint: (Dirk Baeumer)
   5. Optional: GitLens (Eric Amodio)
   6. Optional: Docker (Microsoft) 
   7. Optional: Git Graph (mhutchie)
   8. Optional: YAML (Red Hat)
4. Restart VS Code so the extension work
5. Open the project in VS Code (File > Open Folder)

## Contributing

For full details on code contributions, please see [CONTRIBUTING.md](https://github.com/timberline-secondary/hackerspace/blob/develop/CONTRIBUTING.md)

1. Move into your cloned directory. `cd ~/Developer/hackerspace`
2. Add the upstream remote: `git remote add upstream git@github.com:timberline-secondary/hackerspace.git`
3. Pull in changes from the upstream master: `git fetch upstream`
4. Merge the changes: `git merge upstream/master`
5. Create a new branch: `git checkout -b yourbranchname`
6. Make your changes and them commit: `git commit -am "yourchangeshere"`
7. Push your branch to your fork of the project: `git push origin yourbranchname`
8. Go to your fork of the repository.
9. Select your recently pushed branch and create a pull request.
10. Complete pull request.
