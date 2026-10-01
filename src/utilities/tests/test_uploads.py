from django.test import SimpleTestCase

from utilities.uploads import UploadToOwnFolder


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
