import os

from django.urls import reverse
from django.http import Http404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth import get_user_model
from django.contrib.messages.views import SuccessMessageMixin
from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import ListView, CreateView, DetailView, UpdateView, DeleteView

from comments.models import Document
from portfolios.models import Portfolio, Artwork
from questions.models import QuestionSubmission
from tenant.views import non_public_only_view, NonPublicOnlyViewMixin
from portfolios.forms import PortfolioForm, ArtworkForm

User = get_user_model()


class PortfolioList(NonPublicOnlyViewMixin, LoginRequiredMixin, ListView):
    model = Portfolio
    template_name = 'portfolios/list.html'


class PortfolioDetail(NonPublicOnlyViewMixin, LoginRequiredMixin, DetailView):
    model = Portfolio
    template_name = 'portfolios/detail.html'
    context_object_name = 'p'

    def get_object(self, queryset=None):
        """ If a user id (pk) wasn't provided in the url, then use the requesting user's id.
        If the user doesn't have a portfolio yet , create one."""
        pk = self.kwargs.get('pk')

        # If there is no pk, then the `portfolios:current_user` was probably used.
        # If the user doesn't have a portfolio yet, create one.
        if pk is None:
            user = self.request.user
        else:
            user = get_object_or_404(User, pk=pk)

        if hasattr(user, 'portfolio'):
            portfolio = user.portfolio
        else:
            portfolio, _ = Portfolio.objects.get_or_create(user=user)

        # insert the pk into kwargs before calling super().get_object()
        self.kwargs['pk'] = portfolio.pk

        return super().get_object(queryset=queryset)

    def dispatch(self, *args, **kwargs):
        if self.request.user.is_authenticated:
            portfolio = self.get_object()
            # only allow the portfolio owner or staff to view, unless it's shared
            if not portfolio.listed_locally and portfolio.user != self.request.user and not self.request.user.is_staff:
                raise Http404("Sorry, this portfolio isn't shared!")
        return super().dispatch(*args, **kwargs)


class PortfolioUpdate(NonPublicOnlyViewMixin, LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    model = Portfolio
    form_class = PortfolioForm
    template_name = 'portfolios/edit.html'
    context_object_name = 'p'
    success_message = "Portfolio updated."

    def get_success_url(self):
        return reverse('portfolios:detail', kwargs={'pk': self.object.pk})

    def dispatch(self, *args, **kwargs):
        if self.request.user.is_authenticated:
            portfolio = self.get_object()
            # only allow the portfolio owner or staff to edit, unless it's shared
            if portfolio.user != self.request.user and not self.request.user.is_staff:
                raise Http404("Sorry, this portfolio isn't yours.")
        return super().dispatch(*args, **kwargs)


def public_list(request):
    public_portfolios = Portfolio.objects.all().filter(listed_publicly=True)
    return render(request, 'portfolios/public_list.html', {"portfolios": public_portfolios})


def public(request, uuid):
    p = get_object_or_404(Portfolio, uuid=uuid)
    return render(request, 'portfolios/public.html', {"p": p})


######################################
#
#         ARTWORK VIEWS
#
######################################

class ArtworkCreate(NonPublicOnlyViewMixin, LoginRequiredMixin, SuccessMessageMixin, CreateView):
    model = Artwork
    form_class = ArtworkForm
    template_name = 'portfolios/art_form.html'
    success_message = "The art was added to the Portfolio"

    def get_success_url(self):
        return reverse('portfolios:edit', kwargs={'pk': self.object.portfolio.pk})

    def form_valid(self, form):
        data = form.save(commit=False)
        data.portfolio = get_object_or_404(Portfolio, pk=self.kwargs.get('pk'))
        data.save()
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        portfolio = get_object_or_404(Portfolio, pk=self.kwargs.get('pk'))
        context['heading'] = "Add Art to " + portfolio.user.get_username() + "'s Portfolio"
        context['submit_btn_value'] = "Create"
        context['portfolio'] = portfolio
        return context

    def dispatch(self, *args, **kwargs):
        if self.request.user.is_authenticated:
            portfolio = get_object_or_404(Portfolio, pk=self.kwargs.get('pk'))
            # only allow the portfolio owner or staff to modify
            if portfolio.user != self.request.user and not self.request.user.is_staff:
                raise Http404("Sorry, this isn't your art!")
        return super().dispatch(*args, **kwargs)


class ArtworkUpdate(NonPublicOnlyViewMixin, LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    model = Artwork
    form_class = ArtworkForm
    template_name = 'portfolios/art_form.html'
    success_message = "Art updated!"

    def get_success_url(self):
        return reverse('portfolios:edit', kwargs={'pk': self.object.portfolio.pk})

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super().get_context_data(**kwargs)
        context['heading'] = "Edit " + self.object.portfolio.user.get_username() + "'s Portfolio Art"
        context['submit_btn_value'] = "Update"
        context['portfolio'] = self.object.portfolio
        return context

    def dispatch(self, *args, **kwargs):
        if self.request.user.is_authenticated:
            art = self.get_object()
            # only allow the portfolio owner or staff to modify
            if art.portfolio.user != self.request.user and not self.request.user.is_staff:
                raise Http404("Sorry, this isn't your art!")
        return super().dispatch(*args, **kwargs)


class ArtworkDelete(NonPublicOnlyViewMixin, LoginRequiredMixin, DeleteView):
    model = Artwork

    def get_success_url(self):
        return reverse('portfolios:edit', kwargs={'pk': self.object.portfolio.pk})

    def dispatch(self, *args, **kwargs):
        if self.request.user.is_authenticated:
            art = self.get_object()
            # only allow the portfolio owner or staff to modify
            if art.portfolio.user != self.request.user and not self.request.user.is_staff:
                raise Http404("Sorry, this isn't your art!")
        return super().dispatch(*args, **kwargs)


def is_acceptable_image_type(filename):
    # Get extension from filename to determine filetype...very hacky...
    # TODO use MIMETYPES
    name, ext = os.path.splitext(filename)
    img_ext_list = [".png", ".gif", ".jpg"]
    return ext in img_ext_list


def is_acceptable_vid_type(filename):
    # Get extension from filename to determine filetype...very hacky...
    name, ext = os.path.splitext(filename)
    vid_ext_list = [".ogg", ".avi", ".mp4", ".mkv", ".webm", ".ogv"]
    return ext in vid_ext_list


def add_file_to_portfolio(request, owner, stored_file, date):
    """Put one of ``owner``'s image or video files into their portfolio, and go there.

    Shared by every route that turns a file a student already uploaded into a piece of
    artwork: a file attached to a quest comment (``art_add``) and a file answer to a
    submission question (``art_add_answer``, issue #2573). The artwork always lands in
    the owner's portfolio, so a teacher doing this adds it to the student's portfolio
    rather than their own.

    Args:
        request (HttpRequest): the request, for the user doing the adding.
        owner (User): whose work this is, and whose portfolio it goes into.
        stored_file (FieldFile): the file, already saved.
        date (datetime.date): the date to record on the artwork.

    Returns:
        HttpResponseRedirect: to the owner's portfolio.

    Raises:
        Http404: if the user is neither the owner nor staff, or the file is neither an
            acceptable image nor an acceptable video.
    """
    if not (request.user.is_staff or owner == request.user):
        raise Http404("I don't think you're supposed to be here....")

    filename = os.path.basename(stored_file.name)

    if is_acceptable_image_type(filename):
        image_file = stored_file
        video_file = None
    elif is_acceptable_vid_type(filename):
        image_file = None
        video_file = stored_file
    else:
        raise Http404("Unsupported image or video format.  See your teacher if"
                      " you think this format should be supported.")

    portfolio, created = Portfolio.objects.get_or_create(user=owner)

    Artwork.create(
        title=os.path.splitext(filename)[0][:50],
        image_file=image_file,
        video_file=video_file,
        portfolio=portfolio,
        date=date,
    )
    return redirect('portfolios:detail', pk=portfolio.pk)


@non_public_only_view
@login_required
def art_add(request, doc_id):
    """Add a file attached to a quest comment to its owner's portfolio.

    Args:
        request (HttpRequest): the request.
        doc_id (int): id of the ``comments.Document`` holding the file.

    Returns:
        HttpResponseRedirect: to the owner's portfolio.
    """
    doc = get_object_or_404(Document, id=doc_id)
    return add_file_to_portfolio(request, doc.comment.user, doc.docfile, doc.comment.timestamp.date())


@non_public_only_view
@login_required
def art_add_answer(request, answer_id):
    """Add a student's file answer to a submission question to their portfolio (#2573).

    A file_upload question is exactly where a teacher asks for the artwork or screencast
    a portfolio exists to show off, so an answer offers the same action a file attached
    to the comment box does.

    Args:
        request (HttpRequest): the request.
        answer_id (int): id of the ``questions.QuestionSubmission`` holding the file.

    Returns:
        HttpResponseRedirect: to the student's portfolio.

    Raises:
        Http404: if the answer has no file (nothing to add).
    """
    answer = get_object_or_404(QuestionSubmission, id=answer_id)
    if not answer.response_file:
        raise Http404("That answer doesn't have a file to add.")
    # A published answer carries the comment it was published with, and is dated from it the
    # way a comment's attachment is. A draft row has no comment yet, so fall back to its own
    # creation time rather than failing.
    stamped = answer.comment.timestamp if answer.comment else answer.datetime_created
    return add_file_to_portfolio(
        request, answer.quest_submission.user, answer.response_file, stamped.date())
