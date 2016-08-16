import os
from comments.models import Document
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.core.urlresolvers import reverse_lazy
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.models import User

from django.utils.decorators import method_decorator
from django.views.generic import ListView, CreateView, DetailView, UpdateView, DeleteView
from portfolios.forms import PortfolioForm, ArtworkForm
from portfolios.models import Portfolio, Artwork


class PortfolioList(ListView):
    model = Portfolio
    template_name = 'portfolios/list.html'

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super(PortfolioList, self).dispatch(request, *args, **kwargs)


class PortfolioCreate(CreateView):
    model = Portfolio
    form_class = PortfolioForm
    template_name = 'portfolios/form.html'

    @method_decorator(login_required)
    def form_valid(self, form):
        data = form.save(commit=False)
        data.user = self.request.user
        data.save()
        return super(PortfolioCreate, self).form_valid(form)

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(PortfolioCreate, self).get_context_data(**kwargs)
        context['heading'] = "Create " + self.request.user.get_username() + "'s Portfolio"
        context['action_value'] = ""
        context['submit_btn_value'] = "Create"
        return context


class PortfolioDetail(DetailView):
    model = Portfolio

    @method_decorator(login_required)
    def dispatch(self, *args, **kwargs):
        # only allow admins or the users to see their own portfolios, unless they are shared
        portfolio = get_object_or_404(Portfolio, pk=self.kwargs.get('pk'))
        if portfolio.shared or portfolio.user == self.request.user or self.request.user.is_staff:
            return super(PortfolioDetail, self).dispatch(*args, **kwargs)
        else:
            raise Http404("Sorry, this portfolio isn't shared!")


@login_required
def detail(request, user_id=None):

    if user_id is None:
        user_id = request.user.id

    user = get_object_or_404(User, id=user_id)

    p, created = Portfolio.objects.get_or_create(user=user)

    # only allow admins or the users to see their own portfolios, unless they are shared
    if request.user.is_staff or p.pk == request.user.id or p.shared:
        context = {
            "p": p,
        }
        return render(request, 'portfolios/detail.html', context)
    else:
        raise Http404("Sorry, this portfolio isn't shared!")


def public(request, uuid):
    return redirect("quests:quests")


class PortfolioUpdate(UpdateView):
    model = Portfolio
    form_class = PortfolioForm
    template_name = 'portfolios/form.html'

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(PortfolioUpdate, self).get_context_data(**kwargs)
        context['heading'] = "Edit " + self.request.user.get_username() + "'s Portfolio"
        context['action_value'] = ""
        context['submit_btn_value'] = "Update"
        return context

    # def get_object(self):
    #     return get_object_or_404(Portfolio, user_id=self.request.user)

    @method_decorator(login_required)
    def dispatch(self, *args, **kwargs):
        portfolio = get_object_or_404(Portfolio, pk=self.kwargs.get('pk'))
        # only allow the user or staff to edit
        if portfolio.user == self.request.user or self.request.user.is_staff:
            return super(PortfolioUpdate, self).dispatch(*args, **kwargs)
        else:
            raise Http404("Sorry, this isn't your portfolio!")


######################################
#
#         ARTWORK VIEWS
#
######################################

class ArtworkUpdate(UpdateView):
    model = Artwork
    form_class = ArtworkForm
    template_name = 'portfolios/art_form.html'

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(ArtworkUpdate, self).get_context_data(**kwargs)
        context['heading'] = "Edit " + self.request.user.get_username() + "'s Portfolio Art"
        context['action_value'] = ""
        context['submit_btn_value'] = "Update"
        return context

    # def get_object(self):
    #     return get_object_or_404(Artwork, campaign_user=self.request.user)

    @method_decorator(login_required)
    def dispatch(self, *args, **kwargs):
        art = get_object_or_404(Artwork, pk=self.kwargs.get('pk'))
        # only allow the user or staff to edit
        if art.portfolio.user == self.request.user or self.request.user.is_staff:
            return super(ArtworkUpdate, self).dispatch(*args, **kwargs)
        else:
            raise Http404("Sorry, this isn't your art!")


class ArtworkDelete(DeleteView):
    model = Artwork
    success_url = reverse_lazy('portfolios:current_user')

    @method_decorator(staff_member_required)
    def dispatch(self, *args, **kwargs):
        return super(ArtworkDelete, self).dispatch(*args, **kwargs)


@login_required
def art_detail(request, pk):
    art = get_object_or_404(Artwork, pk=pk)
    # only allow admins or the users to view
    if request.user.is_staff or art.portfolio.user == request.user:
        context = {
            "art": art,
        }
        return render(request, 'portfolios/art_detail.html', context)
    else:
        raise Http404("Sorry, this isn't your art!")


def art_create(request, doc_id):
    doc = get_object_or_404(Document, id=doc_id)
    if request.user.is_staff or doc.comment.user == request.user:
        art = Artwork(
            title=os.path.basename(doc.docfile.name),
            file=doc.docfile,
            portfolio=doc.comment.user.portfolio,
            datetime=doc.comment.timestamp,
        )
        art.save()
        return art_detail(request, art.pk)
    else:
        raise Http404("I don't think you're supposed to be here....")


