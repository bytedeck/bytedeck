from allauth.socialaccount.models import SocialLogin
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import UserPassesTestMixin
from django.db.models import F, Prefetch, Q, Value
from django.db.models.functions import Coalesce, NullIf
from django.http import Http404, HttpResponseForbidden, HttpResponseRedirect

from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.html import format_html
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, ListView, TemplateView
from django.views.generic.edit import UpdateView, FormView, DeleteView

from hackerspace_online.decorators import staff_member_required
from siteconfig.models import SiteConfig

from .models import Profile
from .forms import ProfileForm, UserForm
from .tasks import invalidate_profile_xp_cache_on_schema
from badges.models import BadgeAssertion
from courses.models import CourseStudent, Block, Semester
from notifications.signals import notify
from quest_manager.models import QuestSubmission
from tags.models import get_user_tags_and_xp
from tenant.views import NonPublicOnlyViewMixin, non_public_only_view
from tags.models import Tag

from django.contrib.auth.forms import SetPasswordForm

from profile_manager.allauth_compat import send_email_confirmation
from allauth.account.models import EmailAddress
from allauth.account.utils import perform_login

User = get_user_model()


class ProfileViewTypes:
    """ enum for ProfileList and its descendants.
    Note: using enum.auto() will not work as django template tags cant properly define its value.
    """
    LIST = 0
    CURRENT = 1
    STAFF = 2
    INACTIVE = 3
    BLOCK = 4


class ProfileList(NonPublicOnlyViewMixin, UserPassesTestMixin, ListView):
    model = Profile
    template_name = 'profile_manager/profile_list.html'

    # this will determine which button will be active in self.template_name
    # also if view_type=ProfileViewTypes.STAFF will render a different partial template
    view_type = ProfileViewTypes.LIST

    # The list is paginated server-side so a single request only ever loads (and
    # renders) one page of profiles instead of every student on the deck at once.
    paginate_by = 50

    # Maps a ?sort= value (matching a column's data-field in the template) to the
    # ORM ordering it produces. Columns whose displayed value can't be ordered in
    # the database -- the avatar, the multi-valued blocks/courses lists, and the
    # portfolio link -- are intentionally absent and render as plain headers.
    SORT_FIELDS = {
        'first': 'user__first_name',
        'preferred': 'preferred_sort',  # annotated in apply_sort()
        'last': 'user__last_name',
        'alias': 'alias',
        'custom_profile_field': 'custom_profile_field',
        'xp': 'xp_cached',
        'mark': 'mark_cached',
        'last_sub': 'time_of_last_submission',
        'last_login': 'user__last_login',
        'username': 'user__username',
    }
    DEFAULT_SORT = 'first'
    DEFAULT_ORDER = 'asc'

    # Sort keys a non-staff viewer may use. ProfileListCurrent is open to any
    # authenticated user, so this is limited to the always-visible name columns:
    # XP/Mark are per-student privacy-gated (an eye-slash for students who opt
    # out) and Last Quest/Last Login/Username are only rendered to staff, so
    # letting a student sort by them would leak the ordering of values they
    # can't actually see. See get_allowed_sort_fields().
    NON_STAFF_SORT_FIELDS = ('first', 'preferred', 'last', 'alias', 'custom_profile_field')

    # Fields the ?q= search box matches against (the visible text columns).
    SEARCH_FIELDS = [
        'user__first_name', 'preferred_name', 'user__last_name',
        'alias', 'user__username', 'custom_profile_field',
    ]

    # Search fields a non-staff viewer may match against. Username is staff-only for the
    # same reason it is excluded from NON_STAFF_SORT_FIELDS: the column is rendered only
    # to staff, so letting a student search it turns the list into a lookup that confirms
    # a classmate's username from a guess. The name columns a student can already read
    # stay searchable. See get_allowed_search_fields().
    NON_STAFF_SEARCH_FIELDS = [
        'user__first_name', 'preferred_name', 'user__last_name',
        'alias', 'custom_profile_field',
    ]

    # Querystring parameter carrying the group/block filter, and whether this list offers
    # it at all. ProfileListBlock is already one block, and the staff and inactive lists
    # render no group column, so only the deck-wide and current-semester lists show it.
    BLOCK_FILTER_PARAM = 'block'
    show_block_filter = True

    def test_func(self):
        return self.request.user.is_staff

    def queryset_append(self, profiles_qs):
        profiles_qs = profiles_qs.select_related('user__portfolio')

        # this prefetch prevents runnaway queries when looping through profiles in list view
        # in Profile_list.html it is used to get courses via:
        #  {% for course in object.user.coursestudent_set.all %}{{ course.course.title }}...etc
        # and blocks via
        #  {% for course in object.user.coursestudent_set.all %}{{ course.block }}...etc
        profiles_qs = profiles_qs.prefetch_related(
            Prefetch(
                'user__coursestudent_set',
                # every open semester, not just the deck's default: a student in the other
                # cohort's semester is listed as current, so their course and group must show
                # too rather than leaving their row blank. Empty between semesters, when
                # nobody has a current course.
                queryset=CourseStudent.objects.get_queryset().in_open_semesters().select_related('course', 'block'),
            )
        )

        return profiles_qs

    def get_base_queryset(self):
        """The unfiltered/unsorted set of profiles this list shows.

        Subclasses override this (instead of get_queryset) so that the shared
        prefetching, search and sorting below apply to every profile list.
        """
        return Profile.objects.all_students().get_active()

    def get_search_query(self):
        """Return the trimmed ?q= search term (empty string if none)."""
        return self.request.GET.get('q', '').strip()

    def get_allowed_sort_fields(self):
        """The subset of SORT_FIELDS this request is permitted to sort by.

        Staff may sort by any column; non-staff are limited to
        NON_STAFF_SORT_FIELDS so they can't infer the ordering of columns that
        are hidden from them (staff-only or privacy-gated). Returns a dict of
        {sort key: ORM ordering}.
        """
        if self.request.user.is_staff:
            return self.SORT_FIELDS
        return {key: self.SORT_FIELDS[key] for key in self.NON_STAFF_SORT_FIELDS}

    def get_allowed_search_fields(self):
        """The subset of SEARCH_FIELDS this request is permitted to match against.

        Staff may search every column; non-staff are limited to
        NON_STAFF_SEARCH_FIELDS, which drops the staff-only username column.

        Returns:
            list[str]: ORM lookups the ?q= term may be matched against.
        """
        if self.request.user.is_staff:
            return self.SEARCH_FIELDS
        return self.NON_STAFF_SEARCH_FIELDS

    def show_block_filter_to(self, user):
        """Whether this request should be offered the group/block filter.

        Staff only, even on the lists a student can reach: the group column is rendered
        only to staff, so offering a student the filter would let them partition their
        classmates by a column they cannot see.

        Args:
            user: the requesting user.

        Returns:
            bool: True when the filter should be rendered and honoured.
        """
        return self.show_block_filter and user.is_staff

    def get_block_filter(self):
        """Return the Block the ?block= parameter selects, or None for no filter.

        An unknown, non-numeric or not-currently-running block id falls back to no filter,
        so untrusted querystring input can only ever widen the list back to everybody
        rather than error or reach a group that is not on offer.

        Returns:
            Block | None: the selected group, or None when none is selected.
        """
        if not self.show_block_filter_to(self.request.user):
            return None
        block_pk = self.request.GET.get(self.BLOCK_FILTER_PARAM, '')
        if not block_pk.isdigit():
            return None
        return self.get_block_filter_choices().filter(pk=int(block_pk)).first()

    def get_block_filter_choices(self):
        """The groups offered in the filter: those running in a semester that is open now.

        Scoped the same way as the group column beside it, which is prefetched from
        in_open_semesters() registrations, so the dropdown offers exactly the groups the
        list can actually show and never an option that would return nobody.

        Returns:
            QuerySet[Block]: the selectable groups, ordered by name (Block.Meta).
        """
        return Block.objects.in_open_semesters()

    def apply_block_filter(self, profiles_qs):
        """Narrow ``profiles_qs`` to the students in the selected group.

        Matched through the registrations themselves rather than by joining the profile
        queryset to CourseStudent, so a student registered in the group more than once
        is still listed once and cannot inflate the page counts.

        Args:
            profiles_qs (QuerySet[Profile]): the profiles to narrow.

        Returns:
            QuerySet[Profile]: filtered to the group, or unchanged when none is selected.
        """
        block = self.get_block_filter()
        if block is None:
            return profiles_qs
        return profiles_qs.filter(user_id__in=block.current_student_ids())

    def get_sort(self):
        """Return the validated ``(sort, order)`` pair from the querystring.

        An unknown/forbidden sort key or an invalid order falls back to the
        defaults, so untrusted querystring input can't reorder by a column the
        viewer isn't allowed to sort by.
        """
        sort = self.request.GET.get('sort', self.DEFAULT_SORT)
        if sort not in self.get_allowed_sort_fields():
            sort = self.DEFAULT_SORT
        order = self.request.GET.get('order', self.DEFAULT_ORDER)
        if order not in ('asc', 'desc'):
            order = self.DEFAULT_ORDER
        return sort, order

    def apply_search(self, profiles_qs):
        """Filter ``profiles_qs`` by the ?q= term (OR-matched, case-insensitive,
        partial) across SEARCH_FIELDS; returns it unchanged when there's no term."""
        query = self.get_search_query()
        if query:
            search = Q()
            for field in self.get_allowed_search_fields():
                search |= Q(**{f'{field}__icontains': query})
            profiles_qs = profiles_qs.filter(search)
        return profiles_qs

    def apply_sort(self, profiles_qs):
        """Order ``profiles_qs`` by the validated ?sort=/?order= column.

        NULLs sort last in both directions and username is the tie-break, so a
        nullable column surfaces students who have a value (rather than every
        unset one) and pages stay deterministic. Returns the ordered queryset.
        """
        sort, order = self.get_sort()
        if sort == 'preferred':
            # get_preferred_name() shows preferred_name, falling back to first_name
            # when it's blank; NullIf treats an empty string as blank so the sort
            # order matches what the column actually displays.
            profiles_qs = profiles_qs.annotate(
                preferred_sort=Coalesce(NullIf('preferred_name', Value('')), 'user__first_name', Value('')),
            )
        field = F(self.SORT_FIELDS[sort])
        # nulls_last so sorting a nullable column (mark, last submission, last login)
        # surfaces students who *have* a value first, rather than every unset student
        # bubbling to the top (Postgres orders NULLs first on DESC by default).
        ordering = field.desc(nulls_last=True) if order == 'desc' else field.asc(nulls_last=True)
        # Tie-break on username so rows have a stable order across pages.
        return profiles_qs.order_by(ordering, 'user__username')

    def get_queryset(self):
        """The list's base queryset with shared prefetching, search and sort applied."""
        profiles_qs = self.queryset_append(self.get_base_queryset())
        profiles_qs = self.apply_block_filter(profiles_qs)
        profiles_qs = self.apply_search(profiles_qs)
        return self.apply_sort(profiles_qs)

    def get_context_data(self, **kwargs):
        """Add the view type, the active search/sort state, and the pagination
        helpers (querystring without ``page`` and a windowed page range) the
        template needs to render search-, sort- and page-preserving links."""
        context = super().get_context_data(**kwargs)
        context['VIEW_TYPES'] = ProfileViewTypes
        context['view_type'] = self.view_type

        sort, order = self.get_sort()
        context['search_query'] = self.get_search_query()
        context['current_sort'] = sort
        context['current_order'] = order

        # The group filter beside the search box, and the group it currently selects.
        # Absent entirely on the lists that don't offer it, which is what the template
        # keys off to decide whether to render the control at all.
        if self.show_block_filter_to(self.request.user):
            context['block_filter_choices'] = self.get_block_filter_choices()
            selected = self.get_block_filter()
            context['current_block'] = selected.pk if selected else ''

        # Querystring (minus page) so pagination links keep the active search/sort.
        params = self.request.GET.copy()
        params.pop('page', None)
        context['querystring'] = params.urlencode()

        # Windowed page numbers (with ELLIPSIS markers) for the pagination nav so a
        # deck with thousands of students doesn't render thousands of page links.
        # paginate_by is always set, so ListView always provides these.
        context['page_range'] = context['paginator'].get_elided_page_range(
            context['page_obj'].number, on_each_side=2, on_ends=1,
        )
        return context

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


class ProfileListCurrent(ProfileList):
    """This view only displays currently enrolled students in its list, as opposed to
    all students ever.  Student's shouldn't be able to view all students ever, only their
    current colleagues.

    Arguments:
        ProfileList -- Base class
    """
    view_type = ProfileViewTypes.CURRENT

    # override the staff requirement for ProfileList
    def test_func(self):
        return self.request.user.is_authenticated

    def get_base_queryset(self):
        return Profile.objects.all_in_open_semesters()


@method_decorator(staff_member_required, name='dispatch')
class ProfileListBlock(ProfileList):
    """lists all students in a given block, is accessed through the block list view and acts as a hybrid profile list and block detail view"""
    view_type = ProfileViewTypes.BLOCK
    block_object = None
    # This list is already one group, so a group filter on it would only ever narrow it
    # to itself or to nothing.
    show_block_filter = False

    def get_base_queryset(self):
        """The profiles of the students currently in this block.

        The block and the semester have to be matched on the same registration: filtering
        profiles by block separately would also list a student who is in an open semester
        for one course and in this block only through an archived one. Matching on the
        registration also means each student is named once, so the paginated page counts
        cannot be inflated by a student registered in this block more than once.

        Returns:
            QuerySet[Profile]: the student profiles registered in this block in a semester
            that is open right now, each appearing once.
        """
        block_pk = self.kwargs['pk']
        self.block_object = get_object_or_404(Block, pk=block_pk)
        registered_in_block = CourseStudent.objects.filter(
            block=self.block_object, semester__status=Semester.Status.OPEN,
        ).values_list('user_id', flat=True)
        return Profile.objects.all_in_open_semesters().filter(user_id__in=registered_in_block)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # block object is queried again to pull name + description data from
        context["block_object"] = self.block_object

        return context


@method_decorator(staff_member_required, name='dispatch')
class ProfileListStaff(ProfileList):
    view_type = ProfileViewTypes.STAFF
    # Teachers are not registered in groups, and this list renders no group column.
    show_block_filter = False

    def get_base_queryset(self):
        return Profile.objects.filter(user__is_staff=True)


@method_decorator(staff_member_required, name='dispatch')
class ProfileListInactive(ProfileList):
    view_type = ProfileViewTypes.INACTIVE
    # An inactive student has no registration in an open semester, so every group would
    # filter this list down to nobody.
    show_block_filter = False

    def get_base_queryset(self):
        return Profile.objects.all_inactive()


# Profiles are automatically created with each user, so there is never a teacher to create on manually.
# class ProfileCreate(CreateView):
#     model = Profile
#     form_class = ProfileForm
#     template_name = 'profile_manager/form.html'
#
#     @method_decorator(login_required)
#     def form_valid(self, form):
#         data = form.save(commit=False)
#         data.user = self.request.user
#         data.save()
#         return super(ProfileCreate, self).form_valid(form)


class ProfileDetail(NonPublicOnlyViewMixin, DetailView):
    model = Profile

    @method_decorator(login_required)
    def dispatch(self, *args, **kwargs):
        # only allow the users to see their own profiles, or admins
        profile_user = get_object_or_404(Profile, pk=self.kwargs.get('pk')).user
        if profile_user == self.request.user or self.request.user.is_staff:
            return super().dispatch(*args, **kwargs)

        return redirect('quests:quests')

    def get_context_data(self, **kwargs):
        """Everything the profile page is written from, for the profile named in the URL.

        Granting any badges the student has newly earned is part of building it: the page is
        where a student looks to see what they have, so it is checked as the page is drawn.

        Args:
            **kwargs: passed through to DetailView, which puts the profile itself in as
                `object`.

        Returns:
            dict: the template context, adding their current and past registrations, the XP
            counting toward each current one, their submissions (in progress, completed, and
            completed in a past semester), their badges and their tags.
        """
        # Call the base implementation first to get a context
        profile = get_object_or_404(Profile, pk=self.kwargs.get('pk'))
        context = super().get_context_data(**kwargs)

        # in_progress_submissions = QuestSubmission.objects.all_not_completed(request.user)
        # completed_submissions = QuestSubmission.objects.all_completed(request.user)

        context['courses'] = list(CourseStudent.objects.all_for_user_active(profile.user, True))
        context['courses_old'] = CourseStudent.objects.all_for_user_active(profile.user, False)
        context['in_progress_submissions'] = QuestSubmission.objects.all_not_completed(profile.user, blocking=True)
        context['completed_submissions'] = QuestSubmission.objects.all_completed(profile.user)
        # get_by_type_for_user() was called only for its side effect of granting
        # any newly-earned badges; its returned list was never used in the
        # template. Call that side effect directly and skip building the list.
        BadgeAssertion.objects.check_for_new_assertions(profile.user)
        context['completed_past_submissions'] = QuestSubmission.objects.all_completed_past(profile.user)
        # a progress bar per course, each with the XP that counts toward that one: a student in
        # several courses has a different amount in each, since work can be assigned to one of
        # them (issue #2440). Divided once for all of their registrations rather than once per
        # bar, because the division is a single question about the student (issue #2459).
        context['course_xp'] = CourseStudent.objects.xp_across(profile.user, context['courses'], profile=profile)
        context['badge_assertions_dict_items'] = BadgeAssertion.objects.badge_assertions_dict_items(profile.user)

        tags_xp = get_user_tags_and_xp(profile.user)

        # add tags user didn't gain xp in
        if SiteConfig.get().show_all_tags_on_profiles and tags_xp:
            tags, _ = zip(*tags_xp)
            unrelated_tags = Tag.objects.exclude(name__in=tags).order_by('name')
            tags_xp += [(t, 0) for t in unrelated_tags]

        context['tags'] = tags_xp

        # earned_assertions = BadgeAssertion.objects.all_for_user_distinct(profile.user)
        # assertion_dict = defaultdict(list)
        # for assertion in earned_assertions:
        #     assertion_dict[assertion.badge.badge_type].append(assertion)
        # #
        # # # for key, value in ...
        # # # for badge_type, assertions in assertion_dict.items():
        # # #     print(badge_type.name)
        # # #     for assertion in assertions:
        # # #         print(assertion)

        # context['badge_assertions_dict_items'] = assertion_dict.items()

        return context


class ProfileOwnerOrIsStaffMixin:

    @method_decorator(login_required)
    def dispatch(self, *args, **kwargs):
        profile_user = self.get_object().user
        if profile_user == self.request.user or self.request.user.is_staff:
            return super().dispatch(*args, **kwargs)
        raise Http404("Sorry, this profile isn't yours!")


class ProfileDelete(NonPublicOnlyViewMixin, UserPassesTestMixin, DeleteView):
    """ This view deletes the entire User object, not just the Profile! """
    model = Profile  # Ensure you're using the custom User model
    template_name = "profile_manager/user_confirm_delete.html"  # Adjust the template path as needed
    success_url = reverse_lazy("profiles:profile_list")  # Redirect after deletion

    def test_func(self):
        return self.request.user.is_staff

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        profile = self.get_object()
        approved_submission_qs = QuestSubmission.objects.all_approved(user=profile.user, quest=None, up_to_date=None, active_semester_only=False)
        print(approved_submission_qs)
        context["approved_submission_count"] = approved_submission_qs.count()
        return context

    # Deliberately untested: users should be archived, not hard-deleted (see #2182), so this
    # delete flow is slated for removal/replacement rather than covered with a test.
    def delete(self, request, *args, **kwargs):  # pragma: no cover -- see comment above (#2182)
        """Delete the profile's user (cascading to the profile) and redirect on success.

        Args:
            request: The current HTTP request.
            *args: Positional URL arguments captured by the view.
            **kwargs: Keyword URL arguments captured by the view.

        Returns:
            HttpResponseRedirect: a redirect to ``success_url`` after deletion.
        """
        profile = self.get_object()
        user = profile.user
        user.delete()  # Delete the User (cascades to Profile)
        # Profile will already be deleted due to `on_delete=models.CASCADE`, so no need to call super
        # return super().delete(request, *args, **kwargs)

        # Add success message
        messages.success(
            self.request,
            format_html(
                "The user <b>{}</b> and all of their submissions and courses have been successfully deleted.",
                user.get_full_name(),
            )
        )

        return redirect(self.success_url)


class ProfileUpdate(NonPublicOnlyViewMixin, ProfileOwnerOrIsStaffMixin, UpdateView):
    model = Profile
    profile_form_class = ProfileForm
    user_form_class = UserForm
    template_name = 'profile_manager/form.html'

    def get_object(self):
        return get_object_or_404(self.model, pk=self.kwargs["pk"])

    # returns a list of existing form instances or new ones
    def get_forms(self):
        forms = [self.get_profile_form()]
        if self.request.user.is_staff:
            forms.append(self.get_user_form())

        return forms

    def post(self, request, *args, **kwargs):
        forms = self.get_forms()

        # check if all form instances are valid else ...
        if all(form.is_valid() for form in forms):
            return self.form_valid(forms)
        return self.form_invalid(forms)

    def get_context_data(self, **kwargs):
        profile = self.get_object()
        context = {}

        # return instance of form or new form instance
        context['forms'] = kwargs.get('form', self.get_forms())

        context['heading'] = "Editing " + profile.user.get_username() + "'s Profile"
        context['submit_btn_value'] = "Update"
        context['profile'] = profile

        return context

    # returns instance of ProfileForm
    def get_profile_form(self):
        form_kwargs = super().get_form_kwargs()
        form_kwargs['instance'] = self.get_object()
        form_kwargs['request'] = self.request

        return self.profile_form_class(**form_kwargs)

    # returns instance of UserForm
    def get_user_form(self):
        form_kwargs = super().get_form_kwargs()
        form_kwargs['instance'] = self.get_object().user

        return self.user_form_class(**form_kwargs)

    # runs if all forms are valid
    def form_valid(self, forms, *args, **kwargs):
        for form in forms:
            form.save()

        return HttpResponseRedirect(self.get_success_url())

    def form_invalid(self, forms, *args, **kwargs):
        response = super().form_invalid(forms)
        messages.error(self.request, 'There was an error processing the form. Fields reporting an error will have more information below.')
        return response

    def get_success_url(self):
        return reverse("profiles:profile_detail", args=[self.get_object().pk])


class ProfileUpdateOwn(ProfileUpdate):
    """ Provides a single url for users to edit only their own profile, so the link can be included in emails """

    def get_object(self):
        return self.request.user.profile


class PasswordReset(FormView):
    form_class = SetPasswordForm
    template_name = 'profile_manager/password_change_form.html'

    def get_instance(self):
        model_pk = self.kwargs['pk']
        return get_user_model().objects.get(pk=model_pk)

    @method_decorator(staff_member_required)
    def dispatch(self, *args, **kwargs):
        user = self.get_instance()
        if user.is_staff:
            return HttpResponseForbidden("Staff users are forbidden")
        return super().dispatch(*args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        profile = self.get_instance().profile

        context['heading'] = "Changing " + profile.user.get_username() + "'s Password"
        context['submit_btn_value'] = "Update"

        return context

    def get_form(self):
        return PasswordReset.form_class(user=self.get_instance(), **self.get_form_kwargs())

    def form_valid(self, form):
        form.save()
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('profiles:profile_update', args=[self.get_instance().profile.pk])


class ProfileResendEmailVerification(
    NonPublicOnlyViewMixin,
    ProfileOwnerOrIsStaffMixin,
    DetailView
):

    model = Profile

    def get(self, request, *args, **kwargs):

        profile = self.get_object()
        user = profile.user

        email_address = EmailAddress.objects.filter(email=user.email).first()

        # This is for handling a user that has previously added an email address but has no EmailAddress
        user_has_email = bool(user.email or email_address)

        # This condition exists in case a user with an empty User.email tries to access this URL
        if not user_has_email:
            messages.error(request, "User does not have an email")
            return redirect_to_previous_page(request)

        # This condition exists in case an already verified user tries to access this URL
        if email_address and email_address.verified:
            messages.info(request, "Your email address has already been verified.")
            return redirect_to_previous_page(request)

        send_email_confirmation(
            request=request,
            user=user,
            signup=False,
            email=user.email,
        )

        return redirect_to_previous_page(request)


class TagChart(NonPublicOnlyViewMixin, TemplateView):
    template_name = 'profile_manager/tag_chart.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["user"] = get_object_or_404(get_user_model(), pk=self.kwargs['pk'])
        return context


@non_public_only_view
def oauth_merge_account(request):

    merge_with_user_id = request.session.get('merge_with_user_id')
    user = get_object_or_404(User, id=merge_with_user_id)

    if request.method == "POST":

        merge_account = request.POST.get('submit') == 'yes'

        # Unreachable guard: get_object_or_404(User, id=merge_with_user_id) above already
        # 404s when merge_with_user_id is missing/falsy, so this can never be True here.
        # Kept as a defensive no-op; excluded from coverage (see
        # OAuthMergeAccountViewTests.test_oauth_merge_account__missing_session_user_returns_404).
        if not merge_with_user_id:  # pragma: no cover
            return redirect('account_login')

        if merge_account:
            # Remove the merge_with_user_id and socialaccount_sociallogin from the session object
            # since we don't want to pollute it

            request.session.pop('merge_with_user_id')
            socialaccount_data = request.session.pop('socialaccount_sociallogin', None)
            sociallogin = SocialLogin.deserialize(socialaccount_data)
            sociallogin.connect(request, user)

            # Automatically verify email during account merge
            try:
                email_address = EmailAddress.objects.get(email=user.email)
            except EmailAddress.DoesNotExist:
                email_address = EmailAddress(email=user.email)

            email_address.user = user
            email_address.verified = True
            email_address.primary = True
            email_address.save()

            # complete_social_login() asserts the sociallogin is NOT yet connected
            # (allauth >= 65), and connect() above already linked + logged the social
            # account, so all that's left is logging the user in
            return perform_login(request, user)
        else:
            # Remove the email from that user
            user.emailaddress_set.filter(email=user.email).delete()
            user.email = ''
            user.save()

            return redirect('socialaccount_signup')

    context = {
        'other_account_username': user.username,
        'email_address': user.email,
    }
    return render(request, 'socialaccount/merge.html', context)


@non_public_only_view
@staff_member_required
@require_POST
def recalculate_current_xp(request):
    # Recalculating XP for every current student invalidates and recomputes a cache per
    # profile; on a busy deck that is hundreds of profiles in one request, which has grown a
    # uwsgi worker large enough to get OOM-killed and time out the page (issue #2081). Hand it
    # to the existing background task instead -- it does the same all_in_open_semesters()
    # recompute (with per-profile error handling) and, dispatched from this request, runs in
    # this tenant's schema via tenant-schemas-celery.
    invalidate_profile_xp_cache_on_schema.apply_async(queue='default')
    messages.success(
        request,
        "Recalculating XP for all current students in the background. "
        "It may take a minute; refresh the page to see updated totals.",
    )
    return redirect_to_previous_page(request)


@non_public_only_view
@staff_member_required
@require_POST
def xp_toggle(request, profile_id):
    profile = get_object_or_404(Profile, id=profile_id)
    profile.not_earning_xp = not profile.not_earning_xp
    profile.save()
    return redirect_to_previous_page(request)


@non_public_only_view
@staff_member_required
@require_POST
def profile_archive(request, profile_id):
    """Archive a student by deactivating their account (``User.is_active = False``).

    Archiving is the safe, reversible replacement for deleting a student
    (issue #2182): the student can no longer log in and moves to the Inactive
    list, but all of their data is kept and staff can later restore or delete
    them from there. Staff-only; staff accounts can't be archived this way.
    """
    profile = get_object_or_404(Profile, id=profile_id)
    user = profile.user

    if user.is_staff:
        messages.error(request, "Staff accounts cannot be archived.")
        return redirect_to_previous_page(request)

    user.is_active = False
    user.save()

    messages.success(
        request,
        format_html(
            "<a href='{}'>{}</a> has been archived. You can restore or delete them from the Inactive list.",
            profile.get_absolute_url(),
            user.username,
        ),
    )
    return redirect_to_previous_page(request)


@non_public_only_view
@staff_member_required
@require_POST
def profile_restore(request, profile_id):
    """Restore an archived student by reactivating their account (``User.is_active = True``).

    The reverse of :func:`profile_archive`: the student can log in again and
    returns to the active student lists. Staff-only.
    """
    profile = get_object_or_404(Profile, id=profile_id)
    user = profile.user

    user.is_active = True
    user.save()

    messages.success(
        request,
        format_html("<a href='{}'>{}</a> has been restored.", profile.get_absolute_url(), user.username),
    )
    return redirect_to_previous_page(request)


@non_public_only_view
@staff_member_required
@require_POST
def comment_ban_toggle(request, profile_id):
    """Toggle whether a student is banned from commenting publicly.

    The toggling form of :func:`comment_ban`: where that view only applies a ban, this one
    lifts a ban that is already in place. Staff-only, and POST-only because it changes the
    student's account (#2383).

    Args:
        request: the HttpRequest; must be a POST from a staff user.
        profile_id: the id of the Profile to ban or unban.

    Returns:
        The HttpResponseRedirect from :func:`comment_ban`, back to the page the toggle was
        clicked from.
    """
    return comment_ban(request, profile_id, toggle=True)


@non_public_only_view
@staff_member_required
@require_POST
def comment_ban(request, profile_id, toggle=False):
    profile = get_object_or_404(Profile, id=profile_id)
    if toggle:
        profile.banned_from_comments = not profile.banned_from_comments
    else:
        profile.banned_from_comments = True
    profile.save()

    if profile.banned_from_comments:
        icon = "<span class='fa-stack'>" + \
               "<i class='fa fa-comment-o fa-flip-horizontal fa-stack-1x'></i>" + \
               "<i class='fa fa-ban fa-stack-2x text-danger'></i>" + \
               "</span>"

        notify.send(
            request.user,
            # action=profile.user,
            target=profile.user,
            recipient=request.user,
            affected_users=[profile.user, ],
            verb='banned you from making public comments',
            icon=icon,
        )

        messages.warning(
            request,
            format_html(
                "<a href='{}'>{}</a> banned from commenting publicly",
                profile.get_absolute_url(), profile.user.username,
            )
        )
    else:
        messages.success(
            request,
            format_html(
                "Commenting ban removed for <a href='{}'>{}</a>",
                profile.get_absolute_url(), profile.user.username,
            )
        )

    return redirect_to_previous_page(request)


def redirect_to_previous_page(request):
    # http://stackoverflow.com/questions/12758786/redirect-return-to-same-previous-page-in-django
    return redirect(request.META.get('HTTP_REFERER', '/'))
    #
    # if '/profiles/all/' in request.META['HTTP_REFERER']:
    #     return redirect('profiles:profile_list')
    # else:
    #     return redirect('profiles:profile_list_current')
