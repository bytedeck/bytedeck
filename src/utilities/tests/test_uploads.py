from django.test import SimpleTestCase

from utilities.uploads import UploadToOwnFolder, is_own_folder


class UploadToOwnFolderTest(SimpleTestCase):
    """UploadToOwnFolder, the ``upload_to`` that gives each upload an address of its own (#2805)."""

    def test_call__stores_the_file_in_a_random_folder_inside_the_dated_one(self):
        """The upload keeps its own name, inside a random folder inside the dated one."""
        path = UploadToOwnFolder('documents/%Y/%m/%d')(None, 'New_Piskel_3.gif')

        self.assertRegex(path, r'^documents/\d{4}/\d{2}/\d{2}/[0-9a-f]{8}/New_Piskel_3\.gif$')

    def test_call__two_uploads_of_one_name_get_different_addresses(self):
        """Uploads sharing a name each get a folder of their own, so neither can take the other's address."""
        upload_to = UploadToOwnFolder('documents/%Y/%m/%d')

        self.assertNotEqual(upload_to(None, 'photo.jpg'), upload_to(None, 'photo.jpg'))

    def test_eq__compares_the_dated_folder(self):
        """Two are equal when their dated folders are, which keeps makemigrations from seeing a change each run."""
        self.assertEqual(UploadToOwnFolder('documents/%Y'), UploadToOwnFolder('documents/%Y'))
        self.assertNotEqual(UploadToOwnFolder('documents/%Y'), UploadToOwnFolder('portfolios/%Y'))
        self.assertNotEqual(UploadToOwnFolder('documents/%Y'), 'documents/%Y')

    def test_eq__a_subclass_is_not_the_same(self):
        """A subclass decides folders differently, so swapping one in has to read as a change to
        makemigrations even with the same dated folder."""
        class Subclass(UploadToOwnFolder):
            """A stand-in for an ``upload_to`` built on this one."""

        self.assertNotEqual(UploadToOwnFolder('documents/%Y'), Subclass('documents/%Y'))

    def test_new_folder__a_random_folder_inside_the_dated_one(self):
        """A new folder is today's dated folder with a random name inside it, a new one each time."""
        upload_to = UploadToOwnFolder('documents/%Y/%m/%d')

        self.assertRegex(upload_to.new_folder(), r'^documents/\d{4}/\d{2}/\d{2}/[0-9a-f]{8}$')
        self.assertNotEqual(upload_to.new_folder(), upload_to.new_folder())


class IsOwnFolderTest(SimpleTestCase):
    """is_own_folder, which tells a folder of its own from the day's folder older uploads sit in."""

    def test_is_own_folder__a_random_folder_is(self):
        """A folder UploadToOwnFolder made is one."""
        self.assertTrue(is_own_folder(UploadToOwnFolder('documents/%Y/%m/%d').new_folder()))

    def test_is_own_folder__a_day_folder_is_not(self):
        """The day's folder, which older uploads sit straight in, is not: it holds everyone's files
        from that day."""
        self.assertFalse(is_own_folder('documents/2026/09/30'))
        self.assertFalse(is_own_folder(''))
