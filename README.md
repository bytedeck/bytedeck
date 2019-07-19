## Hackerspace test environment installation (instructions for students)
LMS for Timberline Secondary School's Digital Hackerspace

This guide assumes you are running Linux.  If not, then you can use the [Windows subsystem for Linux](https://docs.microsoft.com/en-us/windows/wsl/install-win10) if you have Windows 10.  Another option is [Git Bash](https://git-for-windows.github.io/)

#### Preparation
1. Make sure you have python 3.5 installed: `python3 --version` or install it: `sudo add-apt-repository ppa:deadsnakes/ppa && sudo apt-get update && sudo apt-get install python3.5`
1. Install Git: `sudo apt install git`.
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
1. Make sure you have the Python package manager pip installed: `pip --version`, or install it: `sudo apt install pip`
2. Install [pipenv](https://docs.pipenv.org/en/latest/install/#installing-pipenv) using pip: `pip install --user --upgrade pipenv`
3. Activate pipenv: `pipenv shell`
4. You should now see "(hackerspace)" appear before your prompt.
5. Later (don't do it now), when you are finished you can leave the environment by typing: `deactivate`

#### Installing required python packages
1. `pipenv install` - it will install all required packages, `pipenv install --dev` install required packages for dev mode
2. To install any new packeage use `pipenv install package_name`

#### Creating the SQLite database (Easy Option)
1. A basic database to get started.  You can move to a more advanced PostgreSQL database later if you like, or try now (see next section)
`./src/manage.py migrate`  This will create your database and create tables for all the models
2. Populate the database with some default data: `./src/manage.py loaddata src/initial_data`
3. Create a superuser in the database (i.e.teacher/administrator account): `./src/manage.py createsuperuser`
4. Windows w/Git Bash: if you get an error, try: `winpty python src/manage.py createsuperuser`
5. Create the cache table: `./src/manage.py createcachetable`

#### Creating the PostgreSQL database (Advanced Option)
1. You can follow [these instructions](https://www.digitalocean.com/community/tutorials/how-to-use-postgresql-with-your-django-application-on-ubuntu-16-04) if you are on Linux (won't work on Windows).  Use the Python3 options.

#### Running the server
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
4. Merge the changes: `git merge upstream/master`
5. Create a new branch: `git checkout -b yourbranchname`
6. Make your changes and them commit: `git commit -am "yourchangeshere"`
7. Push your branch to your fork of the project: `git push origin yourbranchname`
8. Go to your fork of the repository.
9. Select your recently pushed branch and create a pull request.
10. Complete pull request.

####BAGLEY WAS HERE
