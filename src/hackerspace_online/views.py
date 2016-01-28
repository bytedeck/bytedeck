from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.contrib.admin.views.decorators import staff_member_required

from djconfig import config

from courses.models import Semester

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
            active_sem_id = form.cleaned_data['hs_active_semester']
            Semester.objects.set_active(active_sem_id)
            form.save()
            messages.success(request, "Settings saved")
            #return redirect('/')
    else:
        form = HackerspaceConfigForm()

    return render(request, 'configuration.html', {'form': form, })

@staff_member_required
def end_active_semester(request):
    if not request.user.is_superuser:
        raise Http404

    from courses.models import Semester
    sem = Semester.objects.complete_active_semester()
    messages.success(request, "Semester " + str(sem) + " has been closed")

    form = HackerspaceConfigForm()
    return render(request, 'configuration.html', {'form': form, })
