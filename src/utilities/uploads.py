import datetime
import posixpath
import re
import secrets

from django.utils.deconstruct import deconstructible


#: The name UploadToOwnFolder gives a folder of its own: eight random hex digits.
OWN_FOLDER_NAME = re.compile(r'^[0-9a-f]{8}$')


def is_own_folder(path):
    """Whether `path` ends in a folder of its own, as UploadToOwnFolder makes one.

    Uploads stored before every upload got a folder of its own sit straight in their day's
    folder, which ends in the day of the month rather than in a random name.

    Args:
        path (str): a folder's path, relative to the storage's root.

    Returns:
        bool: True when its last part is a random folder name.
    """
    return bool(OWN_FOLDER_NAME.match(posixpath.basename(path)))


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
        """Store the dated folder the uploads go into.

        Args:
            folder (str): the dated folder, as a ``strftime`` format.
        """
        self.folder = folder

    def new_folder(self):
        """Return a new folder of its own: today's dated folder, then a random name.

        The date is the server's local date, as it is for a plain ``upload_to`` string.

        Returns:
            str: the folder's path, relative to the storage's root.
        """
        return posixpath.join(datetime.datetime.now().strftime(self.folder), secrets.token_hex(4))

    def __call__(self, instance, filename):
        """Return the path an upload is stored at: the dated folder, a random folder, then its name.

        Args:
            instance: the model instance the file belongs to. Django passes it to every
                ``upload_to``, and this one has no use for it.
            filename (str): the name the file was uploaded under.

        Returns:
            str: the path, relative to the storage's root.
        """
        return posixpath.join(self.new_folder(), filename)

    def __eq__(self, other):
        """Two are the same when they are the same kind and use the same dated folder, which is what
        the migrations compare.

        Args:
            other: the object to compare with.

        Returns:
            bool: True for an ``upload_to`` of the same class with the same dated folder.
        """
        return type(other) is type(self) and self.folder == other.folder
