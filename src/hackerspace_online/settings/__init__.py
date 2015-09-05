from .base import *

try:
    from .production_hackerspace import *
except:
    print("***** EXCEPTION IMPORTING PRODUCTION SETTINGS! *******")
    print("***** IMPORTING LOCAL SETTINGS INSTEAD         *******")
    from .local import *
