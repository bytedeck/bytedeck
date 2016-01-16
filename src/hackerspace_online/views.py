from django.shortcuts import render, redirect
from django.contrib.auth.decorators import user_passes_test
from django.contrib.admin.views.decorators import staff_member_required

from .forms import HackerspaceConfigForm

def home(request):

    if request.user.is_staff:
        return redirect('quests:approvals')

    if request.user.is_authenticated():
        return redirect('quests:quests')

    return render(request, "home.html", {})

@staff_member_required
def config_view(request):
    if not request.user.is_superuser:
        raise Http404

    if request.method == 'POST':
        form = HackerspaceConfigForm(data=request.POST)

        if form.is_valid():
            form.save()
            return redirect('/')
    else:
        form = HackerspaceConfigForm()

    return render(request, 'configuration.html', {'form': form, })
