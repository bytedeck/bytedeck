from allauth.socialaccount.models import SocialLogin
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import UserPassesTestMixin
from django.http import Http404, HttpResponseForbidden, HttpResponseRedirect

from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.generic import DetailView, ListView, TemplateView
from django.views.generic.edit import UpdateView, FormView

from hackerspace_online.decorators import staff_member_required

from .models import Profile
from .forms import ProfileForm, UserForm
from badges.models import BadgeAssertion
from courses.models import CourseStudent
from notifications.signals import notify
from quest_manager.models import QuestSubmission
from tags.models import get_user_tags_and_xp
from tenant.views import NonPublicOnlyViewMixin, non_public_only_view

from django.contrib.auth.forms import SetPasswordForm

from allauth.account.utils import send_email_confirmation
from allauth.account.models import EmailAddress
from allauth.socialaccount.helpers import _complete_social_login

User = get_user_model()


class ViewTypes:
    """ enum for ProfileList and its descendants """
    LIST = 0
    CURRENT = 1
    STAFF = 2
    INACTIVE = 3


class ProfileList(NonPublicOnlyViewMixin, UserPassesTestMixin, ListView):
    model = Profile
    template_name = 'profile_manager/profile_list.html'

    # this will determine which button will be active in self.template_name
    # also if view_type=ViewTypes.STAFF will render a different partial template
    view_type = ViewTypes.LIST

    def test_func(self):
        return self.request.user.is_staff

    def queryset_append(self, profiles_qs):
        profiles_qs = profiles_qs.select_related('user__portfolio')

        for profile in profiles_qs:
            profile.blocks_value = profile.blocks()
            profile.courses = profile.current_courses().values_list('course__title', flat=True)
        return profiles_qs

    def get_queryset(self):
        profiles_qs = Profile.objects.all_students().get_active()
        return self.queryset_append(profiles_qs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['VIEW_TYPES'] = ViewTypes
        context['view_type'] = self.view_type
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
    view_type = ViewTypes.CURRENT

    # override the staff requirement for ProfileList
    def test_func(self):
        return self.request.user.is_authenticated

    def get_queryset(self):
        profiles_qs = Profile.objects.all_for_active_semester()
        return self.queryset_append(profiles_qs)


@method_decorator(staff_member_required, name='dispatch')
class ProfileListStaff(ProfileList):
    view_type = ViewTypes.STAFF

    def get_queryset(self):
        return Profile.objects.filter(user__is_staff=True)


@method_decorator(staff_member_required, name='dispatch')
class ProfileListInactive(ProfileList):
    view_type = ViewTypes.INACTIVE

    def get_queryset(self):
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
        # Call the base implementation first to get a context
        profile = get_object_or_404(Profile, pk=self.kwargs.get('pk'))
        context = super().get_context_data(**kwargs)

        # in_progress_submissions = QuestSubmission.objects.all_not_completed(request.user)
        # completed_submissions = QuestSubmission.objects.all_completed(request.user)

        context['courses'] = CourseStudent.objects.all_for_user_active(profile.user, True)
        context['courses_old'] = CourseStudent.objects.all_for_user_active(profile.user, False)
        context['in_progress_submissions'] = QuestSubmission.objects.all_not_completed(profile.user, blocking=True)
        context['completed_submissions'] = QuestSubmission.objects.all_completed(profile.user)
        context['badge_assertions_by_type'] = BadgeAssertion.objects.get_by_type_for_user(profile.user)
        context['completed_past_submissions'] = QuestSubmission.objects.all_completed_past(profile.user)
        context['xp_per_course'] = profile.xp_per_course()
        context['badge_assertions_dict_items'] = BadgeAssertion.objects.badge_assertions_dict_items(profile.user)
        context['tags'] = get_user_tags_and_xp(profile.user)

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

        # The socialaccount_sociallogin must've been removed from the session
        # or there is no user to merge with so we don't have anything else to do...
        if not merge_with_user_id:
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

            return _complete_social_login(request, sociallogin)
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
def recalculate_current_xp(request):
    profiles_qs = Profile.objects.all_for_active_semester()
    for profile in profiles_qs:
        profile.xp_invalidate_cache()
    return redirect_to_previous_page(request)


@login_required
def tour_complete(request):
    profile = request.user.profile
    profile.intro_tour_completed = True
    profile.save()
    # print("*********TOUR COMPLETED**********")
    # print("*********TOUR COMPLETED**********")
    # print("*********TOUR COMPLETED**********")
    # print("*********TOUR COMPLETED**********")
    return redirect('quests:quests')


@non_public_only_view
@staff_member_required
def xp_toggle(request, profile_id):
    profile = get_object_or_404(Profile, id=profile_id)
    profile.not_earning_xp = not profile.not_earning_xp
    profile.save()
    return redirect_to_previous_page(request)


@non_public_only_view
@staff_member_required
def comment_ban_toggle(request, profile_id):
    return comment_ban(request, profile_id, toggle=True)


@non_public_only_view
@staff_member_required
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

        messages.warning(request,
                         "<a href='" + profile.get_absolute_url() + "'>" +
                         profile.user.username + "</a> banned from commenting publicly")
    else:
        messages.success(
            request, "Commenting ban removed for <a href='" + profile.get_absolute_url() + "'>" +
                     profile.user.username + "</a>")

    return redirect_to_previous_page(request)


def redirect_to_previous_page(request):
    # http://stackoverflow.com/questions/12758786/redirect-return-to-same-previous-page-in-django
    return redirect(request.META.get('HTTP_REFERER', '/'))
    #
    # if '/profiles/all/' in request.META['HTTP_REFERER']:
    #     return redirect('profiles:profile_list')
    # else:
    #     return redirect('profiles:profile_list_current')
