LMS originating from Timberline Secondary School's Digital Hackerspace

[![Build and Tests Status](https://github.com/bytedeck/bytedeck/workflows/Build%20and%20Tests/badge.svg?branch=develop)](https://github.com/bytedeck/bytedeck/actions?query=workflow%3A%22Build+and+Tests%22+branch%3Adevelop)
[![Flake8 Linting Status](https://github.com/bytedeck/bytedeck/workflows/Flake8/badge.svg?branch=develop)](https://github.com/bytedeck/bytedeck/actions?query=workflow%3ALint+branch%3Adevelop)
[![Coverage Status](https://coveralls.io/repos/github/bytedeck/bytedeck/badge.svg?branch=develop)](https://coveralls.io/github/bytedeck/bytedeck?branch=develop)

# Hackerspace development environment installation

## Installing and running the project

### Installing Tools

Although bytedeck uses several tools, you only need to set up two of them thanks to docker!

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

Using a different version of Python will probably give you errors when installing the dependencies due to slight changes between versions:
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
   1. Initialize pre-commit
   `pre-commit install`
8. Run a management command to run initial migrations, create the public tenant, superuser, and some other stuff:
   * using venv: `./src/manage.py initdb`
   * using docker: `docker-compose run web bash -c "./src/manage.py initdb"`
9. Now run the django development server:
   * using venv: `./src/manage.py runserver`
   * using docker: `docker-compose up web`
9. You should now get the page at http://localhost:8000.  Note that the ip/url output by the django server, `0.0.0.0` will not work in this project, because our multitenant architecture requires a domain name, so you need to use `localhost` instead.
10. And you should be able to log in to the admin site at http://localhost:8000/admin/
   - user: admin
   - password: password (this is defined in the .env file under DEFAULT_SUPERUSER_PASSWORD)

10. Run redis, celery and celery-beat containers (you can run in the background too if you want with `-d`, but you won't see any errors if they come up).  the db container should already be running:
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


### Enabling Google Sign In (Optional)


Here are the steps, assuming that you now have a functional tenant:

1. Obtain Google credentials: https://developers.google.com/workspace/guides/create-credentials#oauth-client-id
2. Make sure that in the Authorized URIs, add `http://hackerspace.localhost.net:8000/accounts/google/login/callback/`. We will explain why we are using `localhost.net` later but for now, just add this.
3. Go to Social Applications: http://localhost:8000/admin/socialaccount/socialapp/
4. Click Add Social Application
5. Fill in `Client Id` and `Secret Key`. And then add the `Available Sites` to `Chosen Sites`
6. Click Save
7. Go to the Admin tenants page: http://localhost:8000/admin/tenant/tenant/
8. There should be a checkbox beside the tenant's schema name. Check the checkbox and choose `Enable google signin for tenant(s)` and click `Go`.
9. Done

When you are developing locally, Google won't allow you to add `http://hackerspace.localhost:8000/accounts/google/login/callback/` in the Authorized URIs. So we need a way to bypass this in our local machine by mapping
our localhost to `localhost.net` so we can access our tenant via `http://hackerspace.localhost.net:8000`.

We need to modify our hosts file aka `/etc/hosts`. You can also take a look at this [tutorial](https://www.howtogeek.com/27350/beginner-geek-how-to-edit-your-hosts-file/).

1. Add the following, preferably at the bottom of the file:

```conf
127.0.0.1 localhost.net hackerspace.localhost.net
```

2. We need to update the`ALLOWED_HOSTS` in our .env file:

```bash
ALLOWED_HOSTS=.localhost,.localhost.net
```

3. For the final step, we need to let `django-tenants` know that `hackerspace.localhost.net` is also a valid domain.
Run `$ ./src/manage.py shell` and type in the following commands

```python
from tenant.models import Tenant
tenant = Tenant.objects.get(schema_name='hackerspace')
tenant.domains.create(domain='hackerspace.localhost.net', is_primary=False)
```

4. Done! You should now be able to access your site via `http://hackerspace.localhost.net:8000/` and use the Google Sign In.

## Contributing

See [CONTRIBUTING.md](https://github.com/bytedeck/bytedeck/blob/develop/CONTRIBUTING.md) if you plan to contribute code to this project.  It contains critical information for your pull request to be accepted and will save you a lot of time!
