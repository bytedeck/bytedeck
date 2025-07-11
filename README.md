LMS originating from Timberline Secondary School's Digital Hackerspace

[![Build and Tests Status](https://github.com/bytedeck/bytedeck/actions/workflows/build_and_test.yml/badge.svg?branch=develop)](https://github.com/bytedeck/bytedeck/actions?query=workflow%3A%22Build+and+Tests%22+branch%3Adevelop)
[![Flake8 Linting Status](https://github.com/bytedeck/bytedeck/actions/workflows/lint.yml/badge.svg?branch=develop)](https://github.com/bytedeck/bytedeck/actions?query=workflow%3ALint+branch%3Adevelop)
[![codecov](https://codecov.io/gh/bytedeck/bytedeck/branch/develop/graph/badge.svg)](https://codecov.io/gh/bytedeck/bytedeck)

# Hackerspace development environment installation

## Installing and running the project

### Installing Tools

Although bytedeck uses several tools, you only need to set up two of them thanks to docker!

The instructions below will help you get bytedeck running using [docker](https://www.docker.com/), and then help you set up a development environment with [VS Code](https://code.visualstudio.com/).

The instructions assume you are using Ubuntu (or another Debian based linux distro), although it is possible to get it working anywhere you can install docker.

#### Installing Docker

Follow the instructions the for installing Docker Engine.
https://docs.docker.com/engine/install/, if using Ubuntu and you don't want Docker Desktop, you can install just the enginge from their repository: https://docs.docker.com/engine/install/ubuntu/#install-using-the-repository

By the end, you should be able to run docker's test image:
`$ sudo docker run hello-world`

As a sanity check, make sure docker compose works too:
`$ docker compose --version`

If you can't run docker without sudo, you can try adding yourself to the docker group (is this still needed? I don't think so)
`sudo usermod -aG docker $USER`

#### Make sure you have Python3.10

Using a different version of Python will probably give you errors when installing the dependencies due to slight changes between versions:
`sudo apt install python3.10`

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
1. Move into the project directory:
`cd ~/Developer/bytedeck`
1. Copy the example environment file to the one you'll be using. Docker-compose and django will both be looking for a .env files with various settings that you can customize.  If you are not running the app locally (e.g. production), then be sure to set DOMAIN_ROOT to the FQDN.
`cp .env.example .env`
1. Build the containers (db, redis, celery, and celery-beat):
`docker compose build`
1. Start the postgres database container (db) in the background/daemonized (-d)
`docker compose up -d db`
1. OPTIONAL: For development, we can run the django app in a local virtual environment (venv) instead of using the web container, however if this gives you any issues, just run everything in a container with docker compose (explained below)
   1. Create a python virtual environment (we'll put ours in a venv directory):
   `python -m venv venv --prompt bytedeck`
   1. Enter the virtual environment:

      **Linux / macOS**
      `source venv/bin/activate`

      **Windows (bash)**
      `source venv/Scripts/activate`

      **Windows**
      `venv/Scripts/activate`

   1. Install wheel to prevent errors (why isn't this included in the new venv module?)
   `python -m pip install wheel`
   1. Install our requirements:
   `python -m pip install -r requirements.txt`
1. Initialize pre-commit:
   * Using venv: `pre-commit install`
   * Using docker: `docker compose run web bash -c "pre-commit install"`
1. Run a management command to run initial migrations, create the public tenant, superuser, and some other stuff:
   * using venv: `python src/manage.py initdb`
   * using docker: `docker compose run web bash -c "python src/manage.py initdb"`
1. Now run the django development server:
   * using venv: `python src/manage.py runserver`
   * using docker: `docker compose up web`
1. You should now get the page at http://localhost:8000.  Note that the ip/url output by the django server, `0.0.0.0` will not work in this project, because our multitenant architecture requires a domain name, so you need to use `localhost` instead.
1. And you should be able to log in to the admin site at http://localhost:8000/admin/
   - user: admin
   - password: password (this is defined in the .env file under DEFAULT_SUPERUSER_PASSWORD)

1. Run redis, celery and celery-beat containers (you can run in the background too if you want with `-d`, but you won't see any errors if they come up).  the db container should already be running:
`docker compose up -d redis celery celery-beat`
1. To view errors in the containers when they are running in the background, you can use:
`docker compose logs -f`

### Creating a Tenant

If everything has worked so far, you should now be able to create your own Bytedeck website (aka a new "deck") as a new tenant:

0. If the server isn't already running, start it with:
   - `python src/manage.py runserver`
     **or**
   - `docker compose up web`
     *(Ignore the link it outputs; it won’t take you to the right place.)*

1. Go to [http://localhost:8000/decks/new/](http://localhost:8000/decks/new/) to create a new deck.
   > **Note:** You may be prompted to log in to the Django admin interface before accessing the page.
   >
   > Use the following credentials:
   > - **Username**: `admin`
   > - **Password**: `password`
   >   *(Defined in `TENANT_DEFAULT_SUPERUSER_PASSWORD` in your `.env` file)*

2. Fill in all required fields and click the **Create** button at the bottom.

3. You’ll now be at the login page. To log in as the default admin:
   - **Username**: `admin`
   - **Password**: `password`
     *(Defined in `TENANT_DEFAULT_SUPERUSER_PASSWORD` in your `.env` file)*

4. To log in as the **owner of the deck**:
   1. Go to the `_sent_mail` directory.
   2. Open the most recent file—it contains a confirmation link.
   3. Click the link and press the **Confirm** button; you'll be taken to the login page.
   4. Return to the `_sent_mail` directory.
   5. Open the latest file—this will contain the owner’s login credentials.
   6. On the login page, log in using:
      - **Username**: as shown in the email (e.g. `firstname.lastname`)
      - **Password**: as shown in the email

5. You should now be inside your own Bytedeck site!

6. To stop the project:
   - Press `Ctrl + C` in the terminal windows
   - Wait for all containers to shut down completely

### Installing more Sample Data
New tenants will come with some basic initial data already installed, but if you want masses of data to simulate a more realistic site in production:

+ Using venv: ```python src/manage.py generate_content hackerspace```
+ Using docker: ```docker compose exec web bash -c "python src/manage.py generate_content hackerspace"```

This will create 100 fake students, and 5 campaigns of 10 quests each, and maybe some other stuff we've added since writing this!  You should see the output of the objects being created.  Go to your map page and regenerate the map to see them.

Some examples of the command in use:
```
$ python src/manage.py generate_content --help
# lists positional arguments and optional flags

$ python src/manage.py generate_content --quiet
# Generates fake students, campaigns, and quests without printing anything to the console

$ python src/manage.py generate_content hackerspace --num_quests_per_campaign 7 --num_campaigns 3
# Creates 3 campaigns of 7 quest each. Additionally creates 100 students because `--num_students` were unspecified

$ python src/manage.py generate_content hackerspace --num_students 50
# Creates 50 fake students. Additionally creates 5 campaigns of 10 quests each because both `--num_quests_per_campaign` and `--num_campaigns` were unspecified

$ python src/manage.py generate_content hackerspace --num_quests_per_campaign 7 --num_campaigns 3 --num_students 50
# create 50 fake students, and 3 campaigns of 7 quests each.
```

### Enabling Google Sign In (Optional)

Here are the steps, assuming that you now have a functional tenant:

1. Obtain Google credentials: https://developers.google.com/workspace/guides/create-credentials#oauth-client-id
2. In the OAuth Client ID's Authorized Redirect URIs, add `http://hackerspace.localhost.net:8000/accounts/google/login/callback/`. We will explain why we are using `localhost.net` later.
3. Go to Social Applications in the public tenant admin: http://localhost:8000/admin/socialaccount/socialapp/
4. Click Add Social Application
5. Fill in `Client Id` and `Secret Key` from the Google OAuth Client ID, then add the `Available Sites` to `Chosen Sites`
6. Click Save
7. Go to Tenants on the public tenant admin: http://localhost:8000/admin/tenant/tenant/
8. There should be a checkbox beside the tenant's schema name. Check the checkbox and choose `Enable google signin for tenant(s)` from the admin actions at the bottom, and click `Go`.
9. Done

When you are developing locally, Google won't allow you to add `http://hackerspace.localhost:8000/accounts/google/login/callback/` in the Authorized URIs. So we need a way to bypass this in our local machine by mapping our localhost to `localhost.net` so we can access our tenant via `http://hackerspace.localhost.net:8000`.

1. You need to [modify your hosts file](https://www.howtogeek.com/27350/beginner-geek-how-to-edit-your-hosts-file/) by adding this to the bottom of `/etc/hosts`:

   ```conf
   127.0.0.1 localhost.net hackerspace.localhost.net
   ```

2. Update the `ALLOWED_HOSTS` in the project's `.env` file:

   ```bash
   ALLOWED_HOSTS=.localhost,.localhost.net
   ```

3. Let `django-tenants` know that `hackerspace.localhost.net` is also a valid domain.  Run `$ ./src/manage.py shell` and type in the following commands

```python
from tenant.models import Tenant
tenant = Tenant.objects.get(schema_name='hackerspace')
tenant.domains.create(domain='hackerspace.localhost.net', is_primary=False)
```

4. Done! You should now be able to access your site via `http://hackerspace.localhost.net:8000/` and use the Google Sign In.  Note that Google Sign In will only work using the `.net` url.

## Contributing

See [CONTRIBUTING.md](https://github.com/bytedeck/bytedeck/blob/develop/CONTRIBUTING.md) if you plan to contribute code to this project.  It contains critical information for your pull request to be accepted and will save you a lot of time!
