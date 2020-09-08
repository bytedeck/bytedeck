LMS originating from Timberline Secondary School's Digital Hackerspace

[![Build and Tests Status](https://github.com/bytedeck/bytedeck/workflows/Build%20and%20Tests/badge.svg?branch=develop)](https://github.com/bytedeck/bytedeck/actions?query=workflow%3A%22Build+and+Tests%22+branch%3Adevelop)
[![Flake8 Linting Status](https://github.com/bytedeck/bytedeck/workflows/Flake8/badge.svg?branch=develop)](https://github.com/bytedeck/bytedeck/actions?query=workflow%3ALint+branch%3Adevelop)
[![Coverage Status](https://coveralls.io/repos/github/bytedeck/bytedeck/badge.svg?branch=HEAD)](https://coveralls.io/github/bytedeck/bytedeck?branch=HEAD)

# Hackerspace development environment installation

## Installing and running the project

### Installing Tools

Although bytedeck uses several tools, you only need to set up a two of them thanks to docker!

The instructions below will help you get bytedeck running using [docker](https://www.docker.com/), and then help you set up a development environment with [VS Code](https://code.visualstudio.com/).

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
2. Go to https://github.com/bytedeck/bytedeck
3. The main branch of this repo is the `develop` branch, make sure you are on that branch.
3. Click the "Fork" button on the top right corner.
4. This will allow you to have your own copy of the project on your GitHub account.

#### Clone your fork

1. Open the directory where you want to put the code.  I like to create a new directory for my code projects called Developer:
`mkdir ~/Developer`
2. Move into the parent directory of the project:
`cd ~/Developer`
3. Go to your forked repository in GitHub
4. Click "Clone or download" and copy the url, then paste it into the command:
`git clone yoururlhere`
5. This will download the project into ~/Developer/bytedeck/

### Running the Code

#### Initial setup
This will create your docker containers and initialize the database by running migrations and creating some initial data that is required:

1. Open a terminal
2. Move into the project directory:
`cd ~/Developer/bytedeck`
3. Copy the example environment file to the one you'll be using. Docker-compose and django will both be looking for a .env files with various settings that you can customize.  If you are not running the app locally (e.g. production), then be sure to set DOMAIN_ROOT to the FQDN.
`cp .env.example .env`
4. Build the containers (db, redis, celery, and celery-beat):
`docker-compose build`
5. Start the postgres database container (db) in the background/daemonized (-d)
`docker-compose up -d db`
6. For development, let's run the django app in a local virtual environment instead of using the web container:
   1. Create a python virtual environment (we'll put ours in a venv directory):
   `virtualenv venv --python=python3.8`
   2. Enter the virtual environment:
   `source venv/bin/activate`
   3. Install our requirements:
   `pip install -r requirements.txt`
7. Run a management command to run initial migrations, create the public tenant, superuser, and some other stuff:
`./src/manage.py initdb`
8. Now run the django development server:  
`./src/manage.py runserver`
8. You should now get the page at http://localhost:8000
9. And you should be able to log in to the admin site at http://localhost:8000/admin/
   - user: admin
   - password: password (this is defined in the .env file under DEFAULT_SUPERUSER_PASSWORD)

10. Run redis, celery and celery-beat containers (you can run in the background too if you want with `-d`, but you wont see any errors if they come up):
`docker-compose up celery celery-beat`
11. To view errors in the containers when they are running in the background, you can use `docker-compose logs -f`

### Creating a Tenant
If everything has worked so far, you should now be able to create your own bytedeck website (aka a new 'deck') as a new tenant:

0. If the server isn't already running, run it with: `./src/manage.py runserver` (and ignore the link it tells you to access the page)
1. Go to django admin at http://localhost:8000/admin/ (this is known as the Public tenant, it's where we can control all the other sites or tenants)
2. In the Tenants app near the bottom, create a new tenant by giving it a name, for example: `hackerspace`
3. This will create a new site at http://hackerspace.localhost:8000 go there and log in
   - user: admin
   - password: password (this is defined in TENANT_DEFAULT_SUPERUSER_PASSWORD in the .env file)
4. Now you should be in your own bytedeck site!
5. If you would like to stop the project, use `Ctrl + C` in the command lines, then wait for each of the containers to stop.

### TODO: Installing more Sample Data <-- NOT SETUP YET
New tenants will come with some basic initial data already installed, but if you want masses of data to simulate a more realistic site in production:

1. Open a Python shell specific to your tenant (make sure you're virtual environment is activated), enter you tenant's name and paste these commands:
    ```
    $ ./src/manage.py tenant_command shell
    Enter Tenant Schema ('?' to list schemas): my_tenant_name

    In [1]: from hackerspace_online.shell_utils import generate_content
    
    In [2]: generate_content()  
    ```

2. This will create 100 fake students, and 5 campaigns of 10 quests each, and maybe some other stuff we've added since writing this!
3. use Ctrl + D or `exit()` to close the Python shell.

### Running Tests and Checking Code Style
You can run tests either locally, or through the web container:
1. This will run all the project's tests and if successful, will also check the code style using flake 8 (make sure you're in your virtual environment):
`./src/manage.py test src && flake8 src`
2. Or run via the web container (assuming it's running. If not, change `exec` to `run`)
`docker-compose exec web bash -c "./src/manage.py test src && flake8 src"`
3. Tests take too long, but you can speed them up by bailing after the first error or failure, and also by running th tests in parallel to take advantage of multi-core processors:
`./src/manage.py test src --parallel --failfast && flake8 src`

### Advanced: Inspecting the database with pgadmin4
Using pgadmin4 we can inspect the postgres database's schemas and tables (helpful for a sanity check sometimes!)
1. Run the pg-admin container:
`docker-compose up pg-admin`
2. Log in:
   - url: [localhost:8080](http://localhost:8080)
   - email: admin@admin.com
   - password: password  (or whatever you changed this to in you `.env` file)
3. Click "Add New Server"
4. Give it any Name you want
5. In the Connection tab set:
   - Host name/address: db
   - Port: 5432
   - Maintenance database: postgres
   - Username: postgres
   - Password: Change.Me!  (or whatever you change the db password to in you `.env` file)
6. Hit Save
7. At the top left expand the Servers tree to find the database, and explore!
8. You'll probably want to look at Schemas > (pick a schema) > Tables


## Contributing Quick Reference

For full details on code contributions, please see [CONTRIBUTING.md](https://github.com/bytedeck/bytedeck/blob/develop/CONTRIBUTING.md)

1. Move into your cloned directory. `cd ~/Developer/bytedeck`
2. Add the upstream remote: `git remote add upstream git@github.com:bytedeck/bytedeck.git`
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

If you make mistakes during the commit process, or want to change or edit commits, [here's a great guide](http://sethrobertson.github.io/GitFixUm/fixup.html).
