## Hackerspace installation from scratch (instructions for students)
LMS for Timberline Secondary School's Digital Hackerspace

#### Preparation
1. Install Python 3: `sudo apt install python3`
1. Install Git: `sudo apt install git`.  If working in Windows, install [Git Bash](https://git-for-windows.github.io/)
1. Pick/create a location for the project, e.g: `~/Developer`

#### Clone the repository
1. Move to the parent directory of the project: `cd ~/Developer`
2. `git clone https://github.com/timberline-secondary/hackerspace.git`
3. This will download the project into ~/Developer/hackerspace/

#### Python Virtual Environment
1. If on Windows, open Git Bash as an administrator
2. On Linux, ensure you are using Python 3.x: `python -V` (Some distros might have Python 2.7 installed)
3. Install [virtualenv](https://virtualenv.pypa.io/en/stable/userguide/): `pip install virtualenv`
2. Move to the parent directory of the project: `cd ~/Developer`
2. Create the virtual environment named hackerspace.  This will place the virtual environment into the same folder as the project (just for convenience): `virtualenv hackerspace`
3. Move into the hackerspace dir: `cd hackerspace` (if using git bash, you should now see "(master)" at the end of your prompt
3. Activate your virtual environment: Linux: `source bin/activate` Windows w/Git Bash: `source Scripts/activate`
4. You should now see "(hackerspace)" appear before your prompt.
5. Later, when you are finished you can leave the environment by typing: `deactivate`

#### Installing required python packages
1. `pip install -r requirments-basic.txt`
2. This does not include what is needed for a PostGres database, and does not include Pillow, which we'll need to install now...
3. Note pip install Pillow works in Git Bash... maybe just need to update version?
4. Also missing django-djconfig in requirements.txt

#### Creating the SQLite database
A basic database to get started.  You can move to PostgreSQL later if you like
`./src/manage.py migrate`

#### Runniing the server!
`./src/manage.py runserver`

Segmentation Fault?  try running it again...  
In your browser go to [127.0.0.1:8000](http://127.0.0.1:8000) to see if it worked!

Sign up to create a student account.

Create a superuser in the database (i.e.teacher/administrator account): `./src/manage.py createsuperuser`
Git Bash: if you get an error, try: `winpty python src/manage.py createsuperuser`




Old stuff below:

####Installing Pillow (Python Image Library):
```
#ref: http://pillow.readthedocs.org/en/latest/installation.html

sudo apt-get install python3-dev python3-setuptools

sudo apt-get install libtiff5-dev libjpeg8-dev zlib1g-dev \
    libfreetype6-dev liblcms2-dev libwebp-dev tcl8.6-dev tk8.6-dev python-tk

# enter virtual env then:
pip install Pillow
```

