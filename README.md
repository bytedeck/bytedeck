LMS originating from Timberline Secondary School's Digital Hackerspace

[![Build and Tests Status](https://github.com/bytedeck/bytedeck/workflows/Build%20and%20Tests/badge.svg?branch=develop)](https://github.com/bytedeck/bytedeck/actions?query=workflow%3A%22Build+and+Tests%22+branch%3Adevelop)
[![Flake8 Linting Status](https://github.com/bytedeck/bytedeck/workflows/Flake8/badge.svg?branch=develop)](https://github.com/bytedeck/bytedeck/actions?query=workflow%3ALint+branch%3Adevelop)
[![Coverage Status](https://coveralls.io/repos/github/bytedeck/bytedeck/badge.svg?branch=develop)](https://coveralls.io/github/bytedeck/bytedeck?branch=develop)

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

#### Make sure you have Python3.8

Using a different version of Python will probably give you errors when installing the dependancies due to slight changes between versions:    
`sudo apt install python3.8`

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
6. OPTIONAL: For development, we can run the django app in a local virtual environment (venv) instead of using the web container, however if this gives you any issues, just run everything in a container with docker-compose (explained below)
   1. Create a python virtual environment (we'll put ours in a venv directory):  
   `python3.8 -m venv venv --prompt bytedeck`
   1. Enter the virtual environment:  
   `source venv/bin/activate`
   1. Install wheel to prevent errors (why isn't this included in the new venv module?)   
   `python -m pip install wheel`
   1. Install our requirements:  
   `python -m pip install -r requirements.txt`
7. Run a management command to run initial migrations, create the public tenant, superuser, and some other stuff:  
   * using venv: `./src/manage.py initdb`
   * using docker: `docker-compose run web bash -c "./src/manage.py initdb"` 
8. Now run the django development server:   
   * using venv: `./src/manage.py runserver`
   * using docker: `docker-compose up web`  
8. You should now get the page at http://localhost:8000.  Note that the ip/url output by the django server, `0.0.0.0` will not work in this project, because our multitenant architecture requires a domain name, so you need to use `localhost` instead.
9. And you should be able to log in to the admin site at http://localhost:8000/admin/
   - user: admin
   - password: password (this is defined in the .env file under DEFAULT_SUPERUSER_PASSWORD)

10. Run redis, celery and celery-beat containers (you can run in the background too if you want with `-d`, but you wont see any errors if they come up).  the db container should already be running:  
`docker-compose up -d redis celery celery-beat`
11. To view errors in the containers when they are running in the background, you can use:  
`docker-compose logs -f`

### Creating a Tenant
If everything has worked so far, you should now be able to create your own bytedeck website (aka a new 'deck') as a new tenant:

0. If the server isn't already running, run it with: `./src/manage.py runserver` or `docker-compose up web` (and ignore the link it tells you to access the page)
1. Go to django admin at http://localhost:8000/admin/ (this is known as the Public tenant, it's where we can control all the other sites or tenants)
2. In the Tenants app near the bottom, create a new tenant by giving it a name, for example: `hackerspace`
3. This will create a new site at http://hackerspace.localhost:8000 go there and log in
   - user: admin
   - password: password (this is defined in TENANT_DEFAULT_SUPERUSER_PASSWORD in the .env file)
4. Now you should be in your own bytedeck site!
5. If you would like to stop the project, use `Ctrl + C` in the command lines, then wait for each of the containers to stop.

### Installing more Sample Data
New tenants will come with some basic initial data already installed, but if you want masses of data to simulate a more realistic site in production:

1. Open a Python shell specific to your tenant (make sure your virtual environment is activated), enter your tenant's name (for example, `hackerspace`) and paste these commands:
    ```
    $ ./src/manage.py tenant_command shell
    Enter Tenant Schema ('?' to list schemas): hackerspace

    In [1]: from hackerspace_online.shell_utils import generate_content
    
    In [2]: generate_content()  
    ```

    You can also do this from docker with:  
    `docker-compose exec web bash -c "./src/manage.py tenant_command shell"`

2. This will create 100 fake students, and 5 campaigns of 10 quests each, and maybe some other stuff we've added since writing this!  You should see the output of the objects being created.  Go to your map page and regenerate the map to see them.
3. use Ctrl + D or `exit()` to close the Python shell.

### Running Tests and Checking Code Style
You can run tests either locally, or through the web container:
1. This will run all the project's tests and if successful, will also check the code style using flake 8 (make sure you're in your virtual environment):  
   * using venv: `./src/manage.py test src && flake8 src`
   * using docker: `docker-compose exec web bash -c "./src/manage.py test src && flake8 src"`  (assuming it's running. If not, change `exec` to `run`)
2. Tests take too long, but you can speed them up by bailing after the first error or failure, and also by running th tests in parallel to take advantage of multi-core processors:  
`./src/manage.py test src --parallel --failfast && flake8 src`

### Further Development
After you've got everything set up, you can just run the whole project with:   
`docker-compose up`

And stop it with:   
`docker-compose down`

or to run in a local venv (assuming you have activated it), start all the docker services in the background (-d) except web, then run the django server locally:  
`docker-compose up -d db redis celery celery-beat -d`  
`./src/manage.py runserver`


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
2. Initialize pre-commit hooks: `git init --template=.git-template`
3. Add the upstream remote (if it doesn't already exist): `git remote add upstream git@github.com:bytedeck/bytedeck.git`
4. Pull in changes from the upstream master: `git pull upstream develop` (in case anything has changed since you cloned it)
5. Create a new branch with a name specific to the issue or feature or bug you will be working on: `git checkout -b yourbranchname`
6. Write code!
7. Before committing, make sure to run tests and linting locally (this will save you the annoyance of having to clean up lots of little "oops typo!" commits).  Note that the `--failfast` and `--parallel` modes are optional and used to speed up the tests.  `--failfast` will quit as soon as one test fails, and `--parallel` will run tests in multiple processes (however if a test fails, the output might not be helpful, and you might need to run the tests again without this option to get more info on the failing test):   
`./src/manage.py test src --failfast --parallel && flake8 src`
8. Commit your changes (you may need to `git add .` if you created any new files that need to be tracked).  If your changes resolve a specific [issue on github](https://github.com/bytedeck/bytedeck/issues), then add "Closes #123" to the commit where 123 is the issue number:  
`git commit -am "Useful description of your changes; Closes #123"`
9. Make sure your develop branch is up to date again and rebase onto any changes that have been made upstream since you started the branch: `git pull upstream develop --rebase`  (this command joins several steps: updating your local develop branch, and then rebasing your current feature branch on top of the updated develop branch)
10. Push your branch to your fork of the project on github (the first time you do this, it will create the branch on github for you): `git push origin yourbranchname`
11. Go to your fork of the repository on GitHub (you should see a dropdown allowing you to select your branch)
12. Select your recently pushed branch and create a pull request (you should see a button for this)
![image](https://user-images.githubusercontent.com/10604391/125674000-d02eb7a0-b85d-4c8f-b8dd-2b144e274f7d.png)

13. Complete pull request.
14. Start work on another feature by checking out the develop branch again: `git checkout develop`
15. Start again at Step 4 and repeat!

If you make mistakes during the commit process, or want to change or edit commits, [here's a great guide](http://sethrobertson.github.io/GitFixUm/fixup.html).
