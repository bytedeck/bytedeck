In production, use the production_template.py to create a settings file specific to
these production settings.

IMPORTANT !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
keep "production_" at the beginning of the filename so
it will be ignored by git (see .gitignore) to prevent publication of
secret keys and email pw's etc.

remove the initial underscore (this was added so the template is not ignored)
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

*Add to __init__.py:

try:
    from .production_x import *
except:
    pass

*Add a new SECRET_KEY
*update database setting to use POSTGRESQL
*update static file settings
*add proper email info and password
