import datetime
import posixpath
import secrets

from django.utils.deconstruct import deconstructible


@deconstructible
class UploadToOwnFolder:
    """An ``upload_to`` that stores each upload in a folder of its own, inside a dated folder.

    Students' uploads are public at their storage address, and on production that address is
    served through a CDN that keeps a copy of a file for up to a day. Stored straight in the
    day's folder, a file's address would be just its name: once a file is deleted (a draft
    attachment the student removed, say), the next upload of the same name that day would be
    stored at the same address, and anyone opening it would get the deleted file from the CDN's
    copy (#2805). A random folder name between the date and the file's own name gives every
    upload an address no earlier file has had, while the file keeps the name the student chose.

    Args:
        folder (str): the dated folder, formatted with ``strftime`` as a plain ``upload_to``
            string is, e.g. ``'documents/%Y/%m/%d'``.
    """

    def __init__(self, folder):
        """Store the dated folder the uploads go into."""
        self.folder = folder

    def __call__(self, instance, filename):
        """Return the path an upload is stored at: the dated folder, a random folder, then its name.

        The date is the server's local date, as it is for a plain ``upload_to`` string.
        """
        return posixpath.join(datetime.datetime.now().strftime(self.folder), secrets.token_hex(4), filename)

    def __eq__(self, other):
        """Two are the same when they use the same dated folder, which is what the migrations compare."""
        return isinstance(other, UploadToOwnFolder) and self.folder == other.folder
