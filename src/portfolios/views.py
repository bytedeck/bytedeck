import os

from django.urls import reverse
from django.http import Http404
from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import ListView, CreateView, DetailView, UpdateView, DeleteView

from comments.models import Document
from portfolios.models import Portfolio, Artwork
from tenant.views import non_public_only_view, NonPublicOnlyViewMixin
from portfolios.forms import PortfolioForm, ArtworkForm


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
        if pk is None:
            portfolio, _ = Portfolio.objects.get_or_create(user=self.request.user)
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


def public_list(request):
    public_portfolios = Portfolio.objects.all().filter(listed_publicly=True)
    return render(request, 'portfolios/public_list.html', {"portfolios": public_portfolios})


def public(request, uuid):
    p = get_object_or_404(Portfolio, uuid=uuid)
    return render(request, 'portfolios/public.html', {"p": p})


@non_public_only_view
@login_required
def edit(request, pk=None):
    # portfolio pk is portfolio.user.id
    if pk is None:
        pk = request.user.id
    user = get_object_or_404(User, id=pk)
    p = get_object_or_404(Portfolio, user=user)

    # if user submitted the Portfolio form to make changes:
    form = PortfolioForm(request.POST or None, instance=p)
    if form.is_valid():
        form.save()
        messages.success(request, "Portfolio updated.")

    # only allow admins or the users to edit their own portfolios
    if request.user.is_staff or request.user == p.user:
        context = {
            "p": p,
            "form": form,
        }
        return render(request, 'portfolios/edit.html', context)
    else:
        raise Http404("Sorry, this portfolio isn't yours!")


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


# @login_required
# def art_detail(request, pk):
#     art = get_object_or_404(Artwork, pk=pk)
#     # only allow admins or the users to view
#     if request.user.is_staff or art.portfolio.user == request.user:
#         context = {
#             "art": art,
#         }
#         return render(request, 'portfolios/art_detail.html', context)
#     else:
#         raise Http404("Sorry, this isn't your art!")

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


@non_public_only_view
@login_required
def art_add(request, doc_id):
    doc = get_object_or_404(Document, id=doc_id)
    doc_user = doc.comment.user
    if request.user.is_staff or doc_user == request.user:
        filename = os.path.basename(doc.docfile.name)

        if is_acceptable_image_type(filename):
            image_file = doc.docfile
            video_file = None
        elif is_acceptable_vid_type(filename):
            image_file = None
            video_file = doc.docfile
        else:
            raise Http404("Unsupported image or video format.  See your teacher if"
                          " you think this format should be supported.")

        portfolio, created = Portfolio.objects.get_or_create(user=doc_user)

        Artwork.create(
            title=os.path.splitext(filename)[0][:50],
            image_file=image_file,
            video_file=video_file,
            portfolio=portfolio,
            date=doc.comment.timestamp.date(),
        )
        return redirect('portfolios:detail', pk=portfolio.pk)
    else:
        raise Http404("I don't think you're supposed to be here....")
