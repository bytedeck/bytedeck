## Hackerspace test environment installation (instructions for students)
LMS for Timberline Secondary School's Digital Hackerspace

#### Preparation
1. Install Python 3: `sudo apt install python3`
1. Install Git: `sudo apt install git`.  If working in Windows, install [Git Bash](https://git-for-windows.github.io/)
1. Pick/create a location for the project, e.g: `~/Developer`

#### Fork the repository
1. Create a Github account.
2. Go to https://github.com/timberline-secondary/hackerspace
3. Click the "Fork" button on the top right corner. 
4. This will allow you to have your own copy of the project on your GitHub account.

#### Clone the repository
1. Move to the parent directory of the project: `cd ~/Developer`
2. Go to your forked repository.
3. Click "Clone or download" and copy the url.
4. `git clone yoururlhere`
3. This will download the project into ~/Developer/hackerspace/

#### Python Virtual Environment
1. If on Windows, open Git Bash as an administrator, or use the [Linux Bash Shell in Windows 10](https://www.howtogeek.com/249966/how-to-install-and-use-the-linux-bash-shell-on-windows-10/).  I fusing the Bash Shell in Windows 10, you can follow all the Linux instructions below.
1. Install the Python package manager, pip: `sudo apt install python3-pip`
3. Install [virtualenv](https://virtualenv.pypa.io/en/stable/userguide/) using pip: `pip3 install virtualenv`
1. If you are asked to upgrade pip: `pip3 install --upgrade pip`
2. Move to the parent directory of the project: `cd ~/Developer` 
2. Create the virtual environment named hackerspace.  This will place the virtual environment into the same folder as the project (just for convenience): `virtualenv hackerspace`
3. Move into the hackerspace dir: `cd hackerspace` (if using git bash, you should now see "(master)" at the end of your prompt
3. Activate your virtual environment: Linux: `source bin/activate` Windows w/Git Bash: `source Scripts/activate`
4. You should now see "(hackerspace)" appear before your prompt.
5. Later (don't do it now), when you are finished you can leave the environment by typing: `deactivate`

#### Installing required python packages
1. `pip install -r requirements-top.txt` (now that we're in our Python3 virtual environment we can just use pip instead of pip3, since our environment will default to python3 for everything)
2. This does not include what is needed for a PostGres database or other production-specific stuff, only development requirements

#### Creating the SQLite database (Easy Option)
1. A basic database to get started.  You can move to a more advanced PostgreSQL database later if you like, or try now (see next section)
`./src/manage.py migrate`  This will create your database and create tables for all the thrid-party apps/requirements
2. Now prepare tables for all of the hackerspace models: `./src/manage.py makemigrations badges announcements courses comments djcytoscape notifications portfolios profile_manager quest_manager prerequisites suggestions` (you might get an error later on if I forget to keep this list of apps updated =)
2. Create tables: `./src/manage.py migrate`
2. Populate the database with some default data: `./src/manage.py loaddata src/initial_data`
3. Create a superuser in the database (i.e.teacher/administrator account): `./src/manage.py createsuperuser`
4. Windows w/Git Bash: if you get an error, try: `winpty python src/manage.py createsuperuser`

#### Creating the PostgreSQL database (Advanced Option)
1. You can follow [these instructions](https://www.digitalocean.com/community/tutorials/how-to-use-postgresql-with-your-django-application-on-ubuntu-16-04) if you are on Linux (won't work on Windows).  Use the Python3 options.

#### Runniing the server
1. `./src/manage.py runserver`
2. Segmentation Fault?  try running it again...
3. In your browser go to [127.0.0.1:8000](http://127.0.0.1:8000) to see if it worked!
4. Log in as the superuser to see what a teacher/admin sees
5. Sign up to create a student account.
6. Stop running server (or any bash script in progress) with `Ctrl + C`

#### Setting up PyCharm IDE
1. Install some version of [PyCharmIDE](https://www.jetbrains.com/pycharm/download/#section=linux)
1. File > Open, then choose the ~/Developer/hackerspace directory
1. Run > Edit Configurations
1. it "+" and choose Django Server
1. Defaults should be good, but "Run Browser" option is handy, tick it if you want to auto open a browser when you run the server.
1. Turn on Django support.  Click "Fix" button at bottom
1. Tick "Enable Django Support
1. Set Django project root to: ~/Developer/hackerspace/src
1. Set Settings to: `hackerspace_online/settings` (this is relative to the root above)
1. OK, OK.
1. Hit the green play button to test.

#### Committing changes

1. Move into your cloned directory. `cd ~/Developer/hackerspace`
2. Add the upstream remote: `git remote add upstream git@github.com:timberline-secondary/hackerspace.git`
3. Pull in changes from the upstream master: `git fetch upstream`
4. Merge the changes: `git merge upstream`
5. Create a new branch: `git checkout -b yourbranchname`
6. Make your changes and them commit: `git commit -am "yourchangeshere"`
7. Push your branch to your fork of the project: `git push origin yourbranchname`
8. Go to your fork of the repository. 
9. Select your recently pushed branch and create a pull request.
10. Complete pull request.

