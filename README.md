LMS for Timberline Secondary School's Digital Hackerspace

[![Build Status](https://travis-ci.org/timberline-secondary/hackerspace.svg?branch=develop)](https://travis-ci.org/timberline-secondary/hackerspace)

# Hackerspace development environment installation (instructions for students)

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

#### Clone the repository

1. Open the directory where you want to put the code.  I like to create a new direcotry for my code projects called Developer: `mkdir ~/Developer`
2. Move into the parent directory of the project: `cd ~/Developer`
3. Go to your forked repository in github
4. Click "Clone or download" and copy the url, then paste it into the command: `git clone yoururlhere`
5. This will download the project into ~/Developer/hackerspace/

#### Initial setup
All the steps required to initially set up the project have been placed into the `setup.sh` script.  Take a look. If you've used Django before you should recognize some of the steps.

1. Open a terminal
2. Move into the project directory: `cd ~/Developer/hackerspace`
3. Run `export DOCKER_HOST=127.0.0.1:8000`
4. Restart the server with `sudo reboot`
5. Reconnect to the server
6. Move into the project directory: `cd ~/Developer/hackerspace`
7. Run the setup script to bulid the docker image, and setup your django web app container: `bash setup.sh`
8. Keep an eye out for errors as it goes through each step.

### Running the server
If everything has worked so far, you should now be able to run your own version of the Hackerspace website:

1. make sure you are in the project's root directory: `cd ~/Developer/hackerspace`
2. Then run it: `docker-compose up`
3. Keep an eye out for errors as it runs each of the 4 containers (web, redis, db, and celery)
4. Once you see this `celery-beat_1  | [2019-09-19 16:11:00,636: INFO/MainProcess] Writing entries...`, press Ctrl+C.
5. Run `docker-compose up db redis`, and once you get `db_1           | LOG:  autovacuum launcher started`, open a new terminal window
6. Connect to your server again in the new window
7. Make sure you are in the project's root directory: `cd ~/Developer/hackerspace`
8. Run `docker-compose up`
9. If everything works, then you should see something like this at the end:
```
web_1     | System check identified no issues (0 silenced).
web_1     | July 21, 2019 - 00:00:45
web_1     | Django version 2.0.13, using settings 'hackerspace_online.settings'
web_1     | Starting development server at http://0.0.0.0:8000/
web_1     | Quit the server with CONTROL-C.
```
10. In your browser go to [127.0.0.1:8000](http://127.0.0.1:8000) or if running on a remote server, `serverpublicip:8000` to see if it worked! You can now close your terminals! 

10a. If you see a message about Disallowed hosts, reconnect to your server, make sure you are in the project's root directory: `cd ~/Developer/hackerspace`, and add your server IP as a string to the `ALLOWED_HOSTS` list in  `/src/hackerspace_online/settings/local.py`

11. Log in as the superuser you created to see what a teacher/admin sees, or create a new student account.

11a. If you didn't create a sueruser, or `setup.sh` never prompted you to, make sure you are in the project's root directory: `cd ~/Developer/hackerspace`, then run `docker-compose run web python src/manage.py createsuperuser`

12. If you would like to stop the project, use `Ctrl + C` in the command line, then wait for each of the containers to stop.

## Setting up a VS Code development environment

(UNTESTED)

1. Install Visual Studio Code: https://code.visualstudio.com/docs/setup/setup-overview
2. Hit Ctrl + ` (back tick, above the tab key) to open a terminal in VS Code
3. Install the following extensions:
   1. Required: Python (Microsoft)
   2. Required: Remote - Containers (Microsoft) 
   3. Optional: Django Template (bibhasdn)
   4. Optional: ESLint: (Dirk Baeumer)
   5. Optional: GitLens (Eric Amodio)
   6. Optional: Docker (Microsoft) 
   7. Optional: Git Graph (mhutchie)
   8. Optional: YAML (Red Hat)
4. Restart VS Code so the extension work
5. Open the project in VS Code (File > Open Folder)
6. You should see a pop up askign if you want to open the project in a container, of not, open the command palette with Ctrl + Shift + P and type: "Remote-Containers" and select: "Reopen Folder in Container"
7. VS Code will now spin up the projects conatainers, and your code will open with the django server running.
8. You can now edit code with live results

## Contributing

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
