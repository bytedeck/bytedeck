from datetime import date, datetime, timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import validate_comma_separated_integer_list
from django.db import connection, models, transaction
from django.db.models import Count, Sum
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.urls import reverse
from django.utils import timezone

import numpy
from colorful.fields import RGBColorField
from django_tenants.utils import get_public_schema_name

from badges.models import BadgeAssertion
from prerequisites.models import IsAPrereqMixin
from quest_manager.models import QuestSubmission
from siteconfig.models import SiteConfig


class MarkRangeManager(models.Manager):
    def get_range(self, mark, courses=None):
        """ return the MarkRange encompassed by this mark adn the list of courses """
        self.get_queryset().filter(active=True)
        day = timezone.localtime(timezone.now()).isoweekday()
        # ranges for all courses
        ranges_qs = self.get_queryset().filter(active=True, courses=None, days__contains=str(day))
        if courses:
            for course in courses:
                courses_qs = course.markrange_set.filter(active=True, days__contains=str(day))  # ranges for this course
                ranges_qs = ranges_qs | courses_qs

        ranges_qs = ranges_qs.filter(minimum_mark__lte=mark)  # filter out ranges that are too high

        return ranges_qs.last()  # return the highest range that qualifies

    def get_range_for_user(self, user):
        mark = user.profile.mark_cached
        student_course_ids = user.profile.current_courses().values_list('course', flat=True)
        if student_course_ids:
            courses = Course.objects.filter(id__in=student_course_ids)
            return self.get_range(mark, courses)
        else:
            return None


class MarkRange(models.Model):
    name = models.CharField(max_length=50, default="Chillax Line")
    minimum_mark = models.FloatField(default=72.5, help_text="Minimum mark as a percentage from 0 to 100 (or higher)")
    active = models.BooleanField(default=True)
    color_light = RGBColorField(default='#BEFFFA', help_text='Color to be used in the light theme')
    color_dark = RGBColorField(default='#337AB7', help_text='Color to be used in the dark theme')
    days = models.CharField(
        validators=[validate_comma_separated_integer_list],
        max_length=13,
        help_text='Comma seperated list of weekdays that this range is active, where Monday=1 and Sunday=7. \
                   E.g.: "1,3,5" for M, W, F.',
        default="1,2,3,4,5,6,7"
    )
    courses = models.ManyToManyField(
        "courses.course",
        blank=True,
        help_text="Which courses this Mark Range will be used for; if left blank it will apply to all courses."
    )

    objects = MarkRangeManager()

    class Meta:
        ordering = ['minimum_mark']

    def __str__(self):
        return self.name + " (" + str(self.minimum_mark) + "%)"


def invalidate_ranks_cache():
    """Remove the cached rank list (see RankManager.get_ranks_cached).
    Wired to every ORM write path: post_save/post_delete signals cover save(),
    create() and instance/queryset deletes; the RankQuerySet overrides below
    cover update(), bulk_create() and bulk_update(), which fire no signals."""
    from django.core.cache import cache
    cache.delete(RankManager.ranks_cache_key())


class RankQuerySet(models.query.QuerySet):
    def get_ranks_lte(self, xp):
        return self.filter(xp__lte=xp)

    def get_ranks_gt(self, xp):
        return self.filter(xp__gt=xp)

    # these write paths fire no signals, so they must invalidate the cache themselves
    def update(self, **kwargs):
        """Same as QuerySet.update(), but invalidates the rank cache (no signals fire)."""
        result = super().update(**kwargs)
        invalidate_ranks_cache()
        return result

    def bulk_create(self, *args, **kwargs):
        """Same as QuerySet.bulk_create(), but invalidates the rank cache (no signals fire)."""
        result = super().bulk_create(*args, **kwargs)
        invalidate_ranks_cache()
        return result

    def bulk_update(self, *args, **kwargs):
        """Same as QuerySet.bulk_update(), but invalidates the rank cache (no signals fire)."""
        result = super().bulk_update(*args, **kwargs)
        invalidate_ranks_cache()
        return result


class RankManager(models.Manager):

    @staticmethod
    def ranks_cache_key():
        from django.db import connection
        return f'{connection.schema_name}-ranks-all'

    def get_queryset(self):
        return RankQuerySet(self.model, using=self._db).order_by('xp')

    def get_ranks_cached(self):
        """The full list of Ranks (ordered by xp), cached to avoid a query per rank lookup.
        Rank lookups happen several times per page on profile/quest/map views, but the table
        is tiny and rarely changes.  The cache is invalidated by Rank.save() and Rank.delete().
        Key is schema-prefixed following the SiteConfig.cache_key() convention."""
        from django.core.cache import cache
        ranks = cache.get(self.ranks_cache_key())
        if ranks is None:
            ranks = list(self.get_queryset())
            cache.set(self.ranks_cache_key(), ranks, 60 * 60 * 24)
        return ranks

    def get_rank(self, user_xp=0):
        """Return the next closest Rank with an XP value <= user_xp
        Only allow user_xp values >= 0.  If no Rank is found, then create a Rank at xp=0
        """
        if user_xp < 0:
            user_xp = 0

        rank = None
        for r in self.get_ranks_cached():  # ordered by xp ascending
            if r.xp <= user_xp:
                rank = r
            else:
                break
        if not rank:
            rank = self.create_zero_rank()
        return rank

    def get_next_rank(self, user_xp=0):
        """Return the next closest Rank with an XP value > user_xp"""
        for r in self.get_ranks_cached():  # ordered by xp ascending
            if r.xp > user_xp:
                return r
        return None

    def create_zero_rank(self):
        zero_rank = Rank(xp=0, name="None", icon="fa fa-circle-o")
        zero_rank.save()
        return zero_rank


class Rank(IsAPrereqMixin, models.Model):
    name = models.CharField(max_length=50, unique=False, null=True)
    xp = models.PositiveIntegerField(help_text='The XP at which this rank is granted')
    icon = models.ImageField(upload_to='icons/ranks/', null=True, blank=True,
                             help_text="A backup where fa_icon can't be used.  E.g. in the quest maps.")
    fa_icon = models.TextField(null=True, blank=True,
                               help_text='html to render a font-awesome icon or icon stack etc.')

    objects = RankManager()

    class Meta:
        ordering = ['xp']

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('courses:ranks')

    def get_icon_url(self):
        if self.icon and hasattr(self.icon, 'url'):
            return self.icon.url
        else:
            return SiteConfig.get().get_default_icon_url()

    def condition_met_as_prerequisite(self, user, num_required):
        # num_required is not used for this one
        # profile = Profile.objects.get(user=user)
        return user.profile.xp_cached >= self.xp

    def get_map(self):
        """RankList pre-populates _map_cached for the whole page in a single
        query; fall back to an individual lookup when it isn't set."""
        if hasattr(self, '_map_cached'):
            return self._map_cached
        from djcytoscape.models import CytoScape
        return CytoScape.objects.get_map_for_init(self)


class Grade(IsAPrereqMixin, models.Model):
    name = models.CharField(max_length=20, unique=True)
    value = models.PositiveIntegerField(unique=True)

    def __str__(self):
        return str(self.name)

    class Meta:
        ordering = ["value"]

    def condition_met_as_prerequisite(self, user, num_required):
        # num_required is not used for this one
        coursestudents = CourseStudent.objects.current_courses(user)
        if coursestudents.filter(grade_fk__value=self.value):
            return True
        else:
            return False


class SemesterQuerySet(models.query.QuerySet):

    def upcoming(self):
        """Semesters being set up, which students can't join yet.

        Returns:
            SemesterQuerySet: the semesters with an UPCOMING status.
        """
        return self.filter(status=Semester.Status.UPCOMING)

    def open(self):
        """Semesters students can currently be registered in.

        Returns:
            SemesterQuerySet: the semesters with an OPEN status.
        """
        return self.filter(status=Semester.Status.OPEN)

    def archived(self):
        """Semesters that have been archived: final marks recorded, read-only.

        Returns:
            SemesterQuerySet: the semesters with an ARCHIVED status.
        """
        return self.filter(status=Semester.Status.ARCHIVED)


class SemesterManager(models.Manager.from_queryset(SemesterQuerySet)):
    """from_queryset so the lifecycle filters above are callable on the manager too,
    e.g. Semester.objects.open()."""

    def get_queryset(self):
        return SemesterQuerySet(self.model, using=self._db).order_by('-first_day')

    def get_current(self, as_queryset=False):
        """The semester students are currently earning XP in, or nothing when none is open.

        Returns:
            Semester or SemesterQuerySet: the deck's open semester (None when no semester is
            open), or when as_queryset is True a queryset holding it (empty when none is open).
        """
        active_semester = SiteConfig.get().open_semester
        if as_queryset:
            if active_semester is None:
                return self.get_queryset().none()
            return self.get_queryset().filter(pk=active_semester.pk)
        else:
            return active_semester

    def complete_semester(self, semester=None, clamp_negative_xp=False):
        """Archive one semester: record its students' final XP, free their seats, and make
        it read-only.

        Everything it touches is scoped to that semester (issue #2157 Phase 3), so a deck
        running a second one alongside keeps its registrations, its in-progress
        submissions, and its pending approvals: archiving one cohort's term must not
        disturb the other's.

        Args:
            semester: the Semester to archive. None means the deck's open semester, which
                is what the archive page passes when there is only one.
            clamp_negative_xp (bool): record a negative final XP as zero instead of
                refusing to archive (the deck-suspension auto-close uses this, #1734
                redesign B2; the staff-driven archive keeps the refusal so a teacher can
                investigate first).

        Returns:
            Semester: the semester just archived, or one of the Semester.NO_OPEN_SEMESTER
            / QUEST_AWAITING_APPROVAL / STUDENTS_WITH_NEGATIVE_XP sentinels when it was
            refused.
        """
        # Atomic so a failure partway leaves nothing half-closed: calc_semester_grades()
        # saves each registration as it iterates and raises on a negative-XP student,
        # so without the transaction the students processed before it would stay finalized.
        try:
            with transaction.atomic():
                # Lock the config row for the duration, the same lock set_active_semester()
                # takes. Without it an activation running alongside this could open its
                # semester and then have this archive clear the pointer, leaving a semester
                # open that the deck no longer points at (so students couldn't use it).
                # The locked row is used for the pointer write below rather than
                # SiteConfig.get(), whose cached copy can be behind the database.
                siteconfig = SiteConfig.objects.select_for_update().get(pk=SiteConfig.get().pk)

                if semester is None:
                    semester = self.get_current()
                if semester is None:
                    return Semester.NO_OPEN_SEMESTER

                # Re-read the semester under its own lock rather than trusting the instance
                # passed in: two requests can both load it while it is open, and the config
                # lock only makes them queue. The second would otherwise recalculate final
                # marks from XP the first already reset, recording zeroes.
                locked = self.get_queryset().select_for_update().filter(pk=semester.pk).first()
                if locked is None:  # pragma: no cover
                    # the row would have to be deleted between the caller loading it and
                    # this lock, and SemesterDelete refuses to delete an open semester
                    return Semester.NO_OPEN_SEMESTER
                semester = locked

                # nothing to archive. Only an open semester can be archived, so one that is
                # already archived (or still upcoming) is refused rather than archived twice.
                if not semester.is_open:
                    return Semester.NO_OPEN_SEMESTER

                # its own students' quests are still awaiting approval, can't close!
                if QuestSubmission.objects.all_awaiting_approval(semester=semester).exists():
                    return Semester.QUEST_AWAITING_APPROVAL

                # need to calculate all user XP and store in their Course
                CourseStudent.objects.calc_semester_grades(semester, clamp_negative_xp=clamp_negative_xp)

                QuestSubmission.objects.remove_in_progress(semester=semester)

                semester.status = Semester.Status.ARCHIVED
                semester.save()

                # Move the pointer off this semester when it named it, onto another one that
                # is still running, or to None when this was the last (issue #1177). The
                # pointer must never go stale while the deck has an open semester: it is the
                # default a student joins, and simplified registration registers straight
                # into it without going through the form's list of choices.
                if siteconfig.active_semester_id == semester.pk:
                    siteconfig.active_semester = self.open().first()
                    siteconfig.save()
        except ValueError:
            return Semester.STUDENTS_WITH_NEGATIVE_XP

        return semester


def default_end_date():
    return date.today() + timedelta(days=135)


class Semester(models.Model):
    """A period of time that student course registrations, quest submissions, and XP belong to.

    A semester moves through a one-way lifecycle (see Status): it is set up while UPCOMING,
    students earn XP in it while OPEN, and archiving records their final marks and makes it
    ARCHIVED, which is terminal.
    """
    NO_OPEN_SEMESTER = -1
    QUEST_AWAITING_APPROVAL = -2
    STUDENTS_WITH_NEGATIVE_XP = -3

    class Status(models.TextChoices):
        """The stages of a semester's lifecycle, in order. Archiving is one-way."""
        UPCOMING = 'upcoming', 'Upcoming'
        OPEN = 'open', 'Open'
        ARCHIVED = 'archived', 'Archived'

    name = models.CharField(
        blank=True, unique=False, max_length=50,
        help_text="If left blank, the semester will display it's First Day as a default name, in the form: mmm-YYYY."
    )

    first_day = models.DateField(null=True, default=date.today)
    last_day = models.DateField(null=True, default=default_end_date)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.UPCOMING,
        help_text="Upcoming: still being set up. Open: students can be registered in it and earn XP. "
                  "Archived: final marks have been recorded and it can no longer be changed."
    )

    objects = SemesterManager()

    class Meta:
        get_latest_by = "first_day"
        ordering = ['first_day']

    def __str__(self):
        if self.name:
            return self.name
        if self.first_day:
            return self.first_day.strftime("%b-%Y")
        return f"Semester {self.pk}"

    @property
    def is_upcoming(self):
        """Whether this semester is still being set up (students can't join it yet)."""
        return self.status == self.Status.UPCOMING

    @property
    def is_open(self):
        """Whether students can be registered in this semester and earn XP in it.

        This is the lifecycle status, not a date comparison: a semester stays open until
        it is archived, even once its last day has passed (see is_within_dates()).
        """
        return self.status == self.Status.OPEN

    @property
    def is_archived(self):
        """Whether this semester's final marks have been recorded, making it read-only."""
        return self.status == self.Status.ARCHIVED

    def is_within_dates(self):
        """
        :return: True if the current date falls within the semeseter's first and last day (inclusive)
        """
        # don't use timezone.now().date() because it uses UTC, and might not be the same as
        # the current local date.  Use current local date with date.today()
        return self.first_day <= date.today() <= self.last_day

    def has_ended(self):
        """Whether the semester's last day is in the past (local date, consistent with
        is_within_dates()). Used by the semester list to flag an open semester that has run
        past its end date and is probably due to be archived.

        Returns:
            bool: True when last_day is set and before today.
        """
        return self.last_day is not None and self.last_day < date.today()

    def num_days(self, upto_today=False):
        '''The number of classes in the semester (from start date to end date
        excluding weekends and ExcludedDates). '''

        if self.first_day is None or self.last_day is None:
            return 0

        excluded_days = self.excluded_days()
        if upto_today and date.today() < self.last_day:
            last_day = date.today()
        else:
            last_day = self.last_day
        count = numpy.busday_count(self.first_day, last_day, holidays=excluded_days)
        if numpy.is_busday(last_day, holidays=excluded_days):  # end date is not included, so add here.
            count += 1
        # We want to return an int because a numpty.int64 is not JSON serializable as of the moment
        return count.item() if hasattr(count, 'item') else count

    def excluded_days(self):
        return self.excludeddate_set.all().values_list('date', flat=True)

    def days_so_far(self):
        return self.num_days(True)

    def fraction_complete(self):
        current_days = self.num_days(True)
        total_days = self.num_days()
        return current_days / total_days

    def percent_complete(self):
        return self.fraction_complete() * 100.0

    def get_interim1_date(self):
        return self.get_date(0.25)

    def get_term_date(self):
        return self.get_date(0.5)

    def get_interim2_date(self):
        return self.get_date(0.75)

    def get_final_date(self):
        return self.last_day

    def get_date(self, fraction_complete):
        """ Gets the closest date, rolling back if it falls on a weekend or excluded
        after a fraction of the semester is over """
        days = self.num_days()
        days_to_fraction = int(days * fraction_complete)
        excluded_days = self.excluded_days()
        date_after_fraction = numpy.busday_offset(self.first_day, offsets=days_to_fraction, roll='backward',
                                                  holidays=excluded_days)
        return date_after_fraction.item()

    def get_datetime_by_days_since_start(self, class_days, add_holidays=False):
        """ The date `class days` from the start of the semester

        Arguments:
            class_days {int} -- number of days since start

        Keyword Arguments:
            add_holidays {bool} -- [description] (default: {False})

        Returns:
            {datetime} -- [description]
        """
        excluded_days = self.excluded_days()

        # The next day of class excluding holidays/weekends, -1 because first day counts as 1, not zero.
        d = numpy.busday_offset(self.first_day, class_days - 1, roll='forward', holidays=excluded_days).astype(date)

        # Might want to include the holidays (if class day is Friday, then work done on weekend/holidays won't show up
        # till Monday.  For chart, want to include those days
        # if (add_holidays):
        #     next_date = numpy.busday_offset(self.first_day, class_days + 1, roll='backward', holidays=excluded_days)
        #     # next_date = workday(self.first_day, class_days + 1, excluded_days)
        #     num_holidays_to_add = next_date - d - timedelta(days=1)  # If more than one day difference
        #     d += num_holidays_to_add

        # convert from date to datetime
        dt = datetime.combine(d, datetime.max.time())
        # make timezone aware
        return timezone.make_aware(dt, timezone.get_default_timezone())

    def reset_students_xp_cached(self):
        """Zero the cached XP of every student registered in this semester.

        Scoped to this semester's own registrations rather than the deck's active semester,
        because archiving clears that pointer: the students whose XP needs resetting are the
        ones who earned it here.
        """
        from profile_manager.models import Profile
        profile_ids = CourseStudent.objects.all_for_semester(self, students_only=True).values_list('user__profile',
                                                                                                   flat=True)
        profile_ids = set(profile_ids)
        profiles = Profile.objects.filter(id__in=profile_ids)

        for profile in profiles:
            profile.xp_cached = 0

        Profile.objects.bulk_update(profiles, ['xp_cached'])

    def get_student_mark_list(self, students_only=False):
        """The cached mark of every student registered in this semester.

        Read from this semester's own registrations, so a mark distribution describes the
        semester it is drawn for even when another one is open alongside it.

        Args:
            students_only (bool): leave out staff and test accounts.

        Returns:
            list: each registered student's mark_cached, including None for the unmarked.
        """
        # select_related the profile since we read profile.mark_cached for every
        # student below; without it that is a query per student.
        students = User.objects.filter(
            id__in=CourseStudent.objects.all_for_semester(
                self, students_only=students_only,
            ).values_list('user', flat=True),
            is_active=True,
        ).select_related('profile')
        mark_list = []
        for student in students:
            mark_list.append(student.profile.mark_cached)
        return mark_list


class BlockManager(models.Manager):

    def grouped_teachers_blocks(self):
        blocks = self.get_queryset().select_related('current_teacher').values_list('current_teacher', 'name')
        grouped = {}

        # Group by {teacher : [ blocks ]}
        for block in blocks:
            teacher, blk = block
            grouped.setdefault(teacher, []).append(blk)

        return grouped


class Block(IsAPrereqMixin, models.Model):
    name = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True, null=True)
    current_teacher = models.ForeignKey(settings.AUTH_USER_MODEL,
                                        null=True, blank=True,
                                        limit_choices_to={'is_staff': True},
                                        on_delete=models.SET_NULL)
    active = models.BooleanField(default=True)

    objects = BlockManager()

    class Meta:
        ordering = ['name']
        verbose_name = 'Group'

    def __str__(self):
        return self.name

    def condition_met_as_prerequisite(self, user, num_required=1):
        """ Returns True if the user has a current course in this block/group.  `num_required` is not used.
        """
        # num_required is not used for this one
        return CourseStudent.objects.current_courses(user).filter(block=self).exists()


class ExcludedDate(models.Model):
    semester = models.ForeignKey(Semester, on_delete=models.CASCADE)
    date = models.DateField(unique=True)
    label = models.CharField(max_length=100, blank=True, null=True, help_text="An optional label for this date.")

    def __str__(self):
        return self.date.strftime("%d-%b-%Y")


class Course(IsAPrereqMixin, models.Model):
    title = models.CharField(max_length=50, unique=True)
    icon = models.ImageField(upload_to='icons/', null=True, blank=True)
    xp_for_100_percent = models.PositiveIntegerField(default=1000)
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('courses:course_list')

    class Meta:
        ordering = ["title"]

    def condition_met_as_prerequisite(self, user, num_required):
        # num_required is not used for this one
        coursestudents = CourseStudent.objects.current_courses(user)
        if coursestudents.filter(course__pk=self.pk):
            return True
        else:
            return False

    @staticmethod
    def autocomplete_search_fields():  # for grapelli prereq selection
        return ("title__icontains",)

    @staticmethod
    def gfk_search_fields():
        return ["title__icontains"]


class CourseStudentQuerySet(models.query.QuerySet):
    def get_user(self, user):
        return self.filter(user=user)

    def get_semester(self, semester):
        """Registrations in `semester`.

        Args:
            semester: a Semester, or None when no semester is open.

        Returns:
            CourseStudentQuerySet: the registrations in that semester, or an empty queryset
            when there is no semester (no semester is open). Registrations whose semester was
            deleted are left out either way: they belong to no semester rather than to this one.
        """
        if semester is None:
            return self.none()
        return self.filter(semester=semester)

    def in_open_semesters(self):
        """Registrations in any semester that is open right now.

        What a deck-wide list of "current" registrations should filter on: a deck can run
        several semesters at once (issue #2157 Phase 3, #1781), and scoping to the deck's
        default instead would leave out the students in the other one, who are just as
        current as the rest.

        Returns:
            CourseStudentQuerySet: the registrations whose semester is open, empty between
            semesters.
        """
        return self.filter(semester__status=Semester.Status.OPEN)

    def get_active(self):
        return self.filter(active=True)

    def get_inactive(self):
        return self.filter(active=False)

    def get_students_only(self):
        return self.filter(user__is_staff=False, user__profile__is_test_account=False)


class CourseStudentManager(models.Manager):
    def get_queryset(self):
        return CourseStudentQuerySet(self.model, using=self._db).select_related('course')

    def all_for_user_semester(self, user, semester):
        return self.get_queryset().get_user(user).get_semester(semester)

    def all_for_user(self, user):
        return self.get_queryset().get_user(user)

    def all_for_user_active(self, user, active):
        if active:
            return self.all_for_user(user).get_active()
        else:
            return self.all_for_user(user).get_inactive()

    # for current active semester
    def calculate_xp(self, user):
        """The total of this student's manual XP adjustments across their current courses.

        Aggregated in the database rather than summed in Python: CourseStudent.xp() asks for
        this, and that runs once per registration for every student on the deck when a semester
        is archived.

        Returns:
            int: the sum of their registrations' xp_adjustment, 0 when they have no course.
        """
        return self.current_courses(user).aggregate(total=Sum('xp_adjustment'))['total'] or 0

    def calc_semester_grades(self, semester, clamp_negative_xp=False):
        """Record every registration's final XP and deactivate it.

        clamp_negative_xp: record a negative XP as zero instead of raising (used
        by the suspension auto-close, where there is no teacher around to fix
        the balance first).
        """
        coursestudents = self.get_queryset().get_semester(semester)
        # atomic: a negative-XP refusal mid-loop must roll back the registrations
        # already deactivated in this call, or they'd sit deactivated while the
        # semester stays open (CodeRabbit find on the #1734 B2 review)
        with transaction.atomic():
            for coursestudent in coursestudents:
                # each registration's own XP, not a single figure reused for all of them: a
                # student who assigned their work to one course must not have that course's
                # total recorded against the other one too (issue #2440)
                coursestudent.final_xp = coursestudent.xp()
                if coursestudent.final_xp < 0:
                    if not clamp_negative_xp:
                        raise ValueError(f"{coursestudent.user.get_full_name()} has a negative XP. "
                                         f"Fix it before closing the semester")
                    coursestudent.final_xp = 0
                coursestudent.active = False
                coursestudent.save()

    def all_for_semester(self, semester, students_only=False):
        """The registrations in one particular semester.

        Args:
            semester: the Semester wanted, or None for no semester at all.
            students_only (bool): leave out staff and test accounts.

        Returns:
            CourseStudentQuerySet: that semester's registrations, active or not. The
            roster of the deck as a whole is all_users_in_open_semesters() instead.
        """
        qs = self.get_queryset().get_semester(semester)
        if students_only:
            qs = qs.get_students_only()
        return qs

    # pick one of the courses...for now
    def current_course(self, user):
        return self.current_courses(user).first()

    def current_courses(self, user):
        """This user's registrations in the semester they are earning XP in right now.

        Read from the registrations themselves rather than from the deck's pointer
        (issue #2157 Phase 3): a student is registered in at most one open semester, so
        every open-semester registration they hold is in that one semester, however many
        courses and groups it covers.

        Args:
            user: the User whose registrations are wanted.

        Returns:
            CourseStudentQuerySet: their registrations in an open semester, empty when they
            are not in one.
        """
        return self.all_for_user(user).filter(semester__status=Semester.Status.OPEN)

    def current_semester(self, user):
        """The semester this user earns XP in right now.

        A student's semester is the one their own registration names, not the one the deck
        points at: once several semesters can be open at a time (#1781), the deck-wide
        pointer can no longer say which of them a given student is in, but their
        registration always can.

        Args:
            user: the User whose semester is wanted.

        Returns:
            Semester or None: the open semester this user is registered in. Someone with no
            such registration (a teacher trying out a quest, a student who hasn't joined a
            course yet) gets the deck's open semester, which is None between semesters.
        """
        registration = self.current_courses(user).select_related('semester').first()
        if registration is not None:
            return registration.semester
        return SiteConfig.get().open_semester

    def has_multicourse_students(self):
        """Whether anyone on the deck is currently registered in more than one course.

        Nothing about per-course XP (issue #2440) applies to a deck where every student takes
        one course, so the pages that would explain it stay quiet unless somebody is actually
        affected.

        Returns:
            bool: True when at least one student holds two or more registrations in an open
            semester. False on the public tenant, which has no courses to read.
        """
        if connection.schema_name == get_public_schema_name():  # pragma: no cover
            # unreachable from the tenant-only pages that ask this; guarded because the public
            # schema has no courses tables, the same way all_users_in_open_semesters() is
            return False

        return self.get_queryset().in_open_semesters().get_students_only().values('user').annotate(
            registrations=Count('id'),
        ).filter(registrations__gt=1).exists()

    def all_users_in_open_semesters(self, students_only=False, active_only=False):
        """Every user registered in a course in a semester that is open right now.

        The deck's roster is the union across its open semesters rather than the contents of
        one of them (issue #2157 Phase 3): with two cohorts running on different calendars,
        both are equally current, and a student appears once however many courses they hold.

        Args:
            students_only (bool): leave out staff and test accounts.
            active_only (bool): leave out registrations that are no longer active, so a
                semester closed by a suspension contributes no users.

        Returns:
            QuerySet[User]: the matching active users, without duplicates.
        """
        if connection.schema_name == get_public_schema_name():
            # the public tenant has no courses tables to read: this runs there while booting
            return User.objects.none()

        courses = self.get_queryset().filter(semester__status=Semester.Status.OPEN)
        if students_only:
            courses = courses.get_students_only()
        if active_only:
            courses = courses.filter(active=True)
        # the registrations stay a subquery rather than a set of ids read into python: the
        # callers that only count the roster then never load it. IN (subquery) yields each
        # user once, so a student in several courses is still one user
        return User.objects.filter(
            id__in=courses.values_list('user_id', flat=True), is_active=True,
        )

    # @cached(60*60*12)
    def get_current_teacher_list(self, user):
        return self.current_courses(user).values_list('block__current_teacher', flat=True)


def semester_for(user=None):
    """The semester that counts as "this semester" when reading or stamping XP.

    The single place that answers it, so a submission is never stamped with one semester
    and then filtered out by a query using another (issue #2157 Phase 3).

    Args:
        user (User): the student whose XP is in view, or None for a deck-wide view
            covering every student at once (a staff approval queue, for instance).

    Returns:
        Semester or None: that student's own semester, or the deck's open semester when no
        particular student is in view. None when neither exists, between semesters.
    """
    if user is None:
        return SiteConfig.get().open_semester
    return CourseStudent.objects.current_semester(user)


class CourseStudent(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    semester = models.ForeignKey(Semester, on_delete=models.SET_NULL, null=True)
    block = models.ForeignKey(Block, on_delete=models.PROTECT, null=True, verbose_name="Group")
    course = models.ForeignKey(Course, on_delete=models.PROTECT, null=True)
    # grade is deprecated, shouldn't be used anywhere any more
    grade_fk = models.ForeignKey(Grade, verbose_name="Grade", on_delete=models.SET_NULL, null=True, blank=True)
    xp_adjustment = models.IntegerField(default=0, help_text="A one-time adjustment to the the user's XP for this course.")
    xp_adjust_explanation = models.CharField(max_length=255, blank=True, null=True,
                                             help_text="An optional reminder why an XP Adjustment was provided.")
    final_xp = models.PositiveIntegerField(blank=True, null=True)
    final_grade = models.PositiveIntegerField(blank=True, null=True)
    active = models.BooleanField(default=True)

    objects = CourseStudentManager()

    class Meta:
        unique_together = (
            ('semester', 'block', 'user'),
            ('user', 'course', 'grade_fk'),
        )
        verbose_name = "Student Course"
        ordering = ['-semester', 'block']

    def __str__(self):
        return f"{self.user.get_username()}" \
               f'{", " + str(self.semester) if self.semester else ""}' \
               f'{", " + str(self.block.name) if self.block else ""}' \
               f': {self.course}'

    def clean(self):
        """Refuse a registration that would put this student in two open semesters at once.

        A deck can run several semesters at a time, but a student belongs to one of them
        (maintainer decision, #1781): they may take as many courses and groups as they like
        within their semester, and their XP, marks and quests are all read from it. Being in
        two at once would make "which semester did they earn this in?" ambiguous again, which
        is the whole thing #2157 Phase 3 set out to fix.

        Raises:
            ValidationError: when the student already has a registration in a different
                semester that is open.
        """
        super().clean()
        if self.user_id is None or self.semester_id is None or not self.semester.is_open:
            return

        others = CourseStudent.objects.filter(
            user_id=self.user_id, semester__status=Semester.Status.OPEN,
        ).exclude(semester_id=self.semester_id)
        if self.pk:
            others = others.exclude(pk=self.pk)

        clash = others.select_related('semester').first()
        if clash is not None:
            raise ValidationError({
                'semester': f'This student is already in {clash.semester}, which is also open. '
                            'A student can only be in one semester at a time.',
            })

    # def get_absolute_url(self):
    #     return reverse('courses:list')
    # return reverse('courses:detail', kwargs={'pk': self.pk})

    # @cached_property
    def xp(self, profile=None):
        """The XP that counts toward this one registration.

        A student in several courses splits their XP between them (issue #2440). Work they
        assigned to one of their current courses counts wholly toward it; everything else is
        shared evenly, which is what every submission did before they could assign one, and is
        still what happens to badge XP, to work handed in while the deck had the setting off,
        and to anything from before the choice existed.

        Args:
            profile (Profile): the student's profile, for a caller holding one whose xp_cached
                is newer than the database. Profile.xp_invalidate_cache() works out the new
                total and asks for the mark, so without this the mark would be a percentage of
                the previous total. Defaults to reading the profile.

        Returns:
            float: this registration's share of the student's XP, including its own
            xp_adjustment. Their whole total when this is their only course.
        """
        profile = profile if profile is not None else self.user.profile
        registrations = CourseStudent.objects.current_courses(self.user)
        current_course_ids = set(registrations.values_list('course_id', flat=True))
        if len(current_course_ids) <= 1:
            return profile.xp_cached

        # xp_cached is the student's deck-wide total: quest XP, badge XP, and every one of
        # their registrations' adjustments. Take out the parts that belong to a particular
        # course, share what is left, and hand this registration back its own pieces.
        xp_by_course = QuestSubmission.objects.xp_by_course(self.user)
        for course_id, xp in BadgeAssertion.objects.xp_by_course(self.user).items():
            xp_by_course[course_id] = xp_by_course.get(course_id, 0) + xp

        # only courses the student still holds can claim XP: work assigned to a course whose
        # registration has since been deleted has nowhere to count, so it goes back into the
        # shared pool rather than being subtracted from it and lost
        assigned_here = xp_by_course.get(self.course_id, 0) if self.course_id else 0
        assigned_anywhere = sum(xp for course_id, xp in xp_by_course.items() if course_id in current_course_ids)
        adjustments = CourseStudent.objects.calculate_xp(self.user)
        shared = profile.xp_cached - assigned_anywhere - adjustments

        return assigned_here + self.xp_adjustment + shared / len(current_course_ids)

    def mark(self, profile=None):
        """This registration's mark, worked out from its own XP.

        A student in two courses has a different amount of XP in each (issue #2440), so each
        registration has its own mark. Capping is a deck setting, applied here so every place
        that shows a mark agrees about it.

        Args:
            profile (Profile): passed through to xp(), for a caller holding a profile whose
                xp_cached is newer than the database.

        Returns:
            float: the percentage for this course, capped at 100 when the deck asks for that.
        """
        mark = self.calc_mark(self.xp(profile))
        if SiteConfig.get().cap_marks_at_100_percent:
            return min(mark, 100)
        return mark

    def calc_mark(self, xp):
        if not self.course:  # course may be null if it was deleted.
            return 0

        fraction_complete = self.semester.fraction_complete()
        if fraction_complete > 0:
            return xp / fraction_complete * 100 / self.course.xp_for_100_percent
        else:
            return 0

    def xp_per_day_ave(self):
        days = self.semester.days_so_far()
        if days > 0:
            return self.user.profile.xp_cached / days
        else:
            return 0


@receiver(post_save, sender=CourseStudent)
def coursestudent_post_save_callback(instance, **kwargs):
    """
    This model's objects are edited by teachers using the admin menu.
    If they make a manual XP adjustment we need to invalidate the user's xp_cache to recalculate xp
    """
    instance.user.profile.xp_invalidate_cache()


@receiver(post_save, sender=Rank)
@receiver(post_delete, sender=Rank)
def rank_invalidate_cache_callback(instance, **kwargs):
    """Keep the cached rank list (RankManager.get_ranks_cached) in sync.
    Signals (rather than model save/delete overrides) also cover queryset.delete(),
    because registering receivers disables the fast-delete path."""
    invalidate_ranks_cache()
