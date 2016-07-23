from .base import *

try:
    from .production_hackerspace import *
except:
    print("***** NO PRODUCTION SETTINGS FOUND     *******")
    print("***** IMPORTING LOCAL SETTINGS         *******")
    from .local import *
