"""Helpers shared by the courses tests."""
from unittest.mock import patch


def patch_registration_xp(xp):
    """Patch the per-course XP split so a test can say what each registration is worth.

    Archiving a semester works a student at a time and asks
    `CourseStudentManager.xp_across()` for all of one student's registrations at once (issue
    #2459), so that is the seam a test controls. Patching `CourseStudent.xp()` instead would
    miss it: nothing on the archive path goes through the per-registration method.

    The patch has to be in place before the registrations are saved, not just before
    archiving: saving one refreshes the student's cached mark, which asks for its XP, and a
    mark that is a MagicMock rather than a number raises FieldError on the profile save.

    Args:
        xp: the XP every registration is worth, or a callable taking a CourseStudent and
            returning its XP, for a test that needs them to differ.

    Returns:
        The patcher, for use as a decorator or a context manager.
    """
    def split(manager, user, registrations, profile=None):
        return [(registration, xp(registration) if callable(xp) else xp) for registration in registrations]

    return patch('courses.models.CourseStudentManager.xp_across', autospec=True, side_effect=split)
