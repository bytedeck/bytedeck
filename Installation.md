# Hackerspace installation instructions for students
LMS for Timberline Secondary School's Digital Hackerspace

#### Preparation
1. Install Python 3: `sudo apt install python3`
1. Install Git: `sudo apt install git`.  If working in Windows, install [Git Bash](https://git-for-windows.github.io/)
1. Pick/create a location for the project, e.g: `~/Developer`

#### Clone the repository
1. Move to the parent directory of the project: `cd ~/Developer`
2. `git clone https://github.com/timberline-secondary/hackerspace.git`

#### Python Virtual Environment
1. If on Windows, open Git Bash as an administrator
2. On Linux, ensure you are using Python 3.x: `python -V` (Some distros might have Python 2.7 installed)
3. Install virtualenv: `pip install virtualenv`
2. Move to the project directory: `cd ~/Developer/hackerspace`
2. Create the virtual environment named env, venv or virtualenv (git will ignore these names per `.gitignore`): `virtualenv env`








####Installing Pillow (Python Image Library):
```
#ref: http://pillow.readthedocs.org/en/latest/installation.html

sudo apt-get install python3-dev python3-setuptools

sudo apt-get install libtiff5-dev libjpeg8-dev zlib1g-dev \
    libfreetype6-dev liblcms2-dev libwebp-dev tcl8.6-dev tk8.6-dev python-tk

# enter virtual env then:
pip install Pillow
```

