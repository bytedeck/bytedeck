LMS for Timberline Secondary School's Digital Hackerspace

[![Build Status](https://travis-ci.org/timberline-secondary/hackerspace.svg?branch=develop)](https://travis-ci.org/timberline-secondary/hackerspace)
[![Total alerts](https://img.shields.io/lgtm/alerts/g/timberline-secondary/hackerspace.svg?logo=lgtm&logoWidth=18)](https://lgtm.com/projects/g/timberline-secondary/hackerspace/alerts/)

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
3. The main branch of this repo is the `develop` branch, make sure you are on that branch.
3. Click the "Fork" button on the top right corner.
4. This will allow you to have your own copy of the project on your GitHub account.

#### Clone your fork

1. Open the directory where you want to put the code.  I like to create a new directory for my code projects called Developer:  
`mkdir ~/Developer`
2. Move into the parent directory of the project:  
`cd ~/Developer`
3. Go to your forked repository in github
4. Click "Clone or download" and copy the url, then paste it into the command:  
`git clone yoururlhere`
5. This will download the project into ~/Developer/hackerspace/

### Running the Code

#### Initial setup
This will create your docker containers and initialize the database by running migrations and creating some inital data that is required:

1. Open a terminal
2. Move into the project directory:  
`cd ~/Developer/hackerspace`
3. Build the containers:  
`docker-compose build`
4. Start 4 of the containers (the database, redis, celery, and celery-beat):
`docker-compose up`
5. Keep an eye out for errors as it goes through each step *(currently celery and celery-beat are not working, but you can ignore them for now)
6. Initialize the database with some key data in a new terminal:  
`bash init_public_schema.sh`
7. ALTERNATE - RUN LOCALLY: If the web container isn't working for you, or you find developing in a container annoying, you can run the django app locally:
   1. Create a python virtual environment (we'll put ours in a venv directory):   
   `virtualenv venv --python=python3.5`  
   Note: 3.5 is important, if you try a different python version you may get some migration inconsistancies or other problems!
   2. Enter the virtual environment:  
   `source venv/bin/activate`
   3. Install our requirements:  
   `pip install -r requirements.txt`
   3. Run migrations:  
   `./src/manage.py migrate_schemas --shared`
   4. Run the app with:  
   `./src/manage.py runserver`

8. You should get a 404 page (until we create a lnading page) at http://localhost:8000
9. But you should be able to log in to the admin site!  http://localhost:8000/admin/
   - user: admin
   - password: hellonepal

### Creating a Tenant
If everything has worked so far, you should now be able to create your own hackerspace website as a new tenant:

1. Go to django admin at http://localhost:8000/admin/ (this is known as the Public tenant, it's where we can control all the other sites or tenants)
2. In the Tenants app near the bottom, create a new tenant by giving it a name, for example: `hackerspace`
3. This will create a new site at http://hackerspace.localhost:8000 go there and log in
   - user: admin
   - password: password (this is defined in TENANT_DEFAULT_SUPERUSER_PASSWORD in settings/local.py)
4. Now you should be in your own Hackerspace site!
5. If you would like to stop the project, use `Ctrl + C` in the command lines, then wait for each of the containers to stop.

### Installing some initial Sample Data
The empty website is pretty boring, and kind of hard to get working because there is no data.  There is some initial sample data in the "tenant_specific_data.json" file you should import into your site.

Note: the [recommended way](https://django-tenant-schemas.readthedocs.io/en/latest/use.html#tenant-command) of installing fixtures (data) is [currently broken](https://github.com/bernardopires/django-tenant-schemas/issues/618#issuecomment-576455240), but we can use the shell instead:

1. Open a shell in the web container (this assumes the container is running, or you can run the next commands locally if you are using a virtual environment) 
`docker-compose exec web sh` 
2. Open a Python shell specific to your tenant:  
`./src/manage.py tenant_command shell`
2. Type `?` to see a list of tenants you've made.  You should have at least one that is not "public".  Select it by entering it's name (without the "- localhost" part).
3. Inside the shell, execute the following commands:
   ```python
   from django.core.management import call_command
   call_command('loaddata', 'src/tenant_specific_data.json')
   ```
4. use Ctrl + D or `exit()` to close the Python shell. 

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
   9. Got any good suggestions? =D
4. Restart VS Code so the extension work
5. Open the project in VS Code (File > Open Folder)

## Contributing Quick Reference

For full details on code contributions, please see [CONTRIBUTING.md](https://github.com/timberline-secondary/hackerspace/blob/develop/CONTRIBUTING.md)

1. Move into your cloned directory. `cd ~/Developer/hackerspace`
2. Add the upstream remote: `git remote add upstream git@github.com:timberline-secondary/hackerspace.git`
3. Pull in changes from the upstream master: `git pull upstream` (in case anything has changed since you cloned it)
5. Create a new branch: `git checkout -b yourbranchname`
6. Make your changes and them commit: `git commit -am "Useful description of your changes"`
7. Make sure your code is up to date again and rebase onto any changes: `git pull upstream --rebase`
7. Push your branch to your fork of the project: `git push origin yourbranchname`
8. Go to your fork of the repository on GitHub (you should see a dropdown allowing you to select your branch)
9. Select your recently pushed branch and create a pull request (you should see a button for this).
10. Complete pull request.
11. Start work on another feature by checking out the develop branch again: `git checkout develop`
12. Start again at Step 3 and repeat!
