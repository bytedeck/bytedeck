from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse

from djconfig import config

from courses.models import Semester
from quest_manager.models import QuestSubmission

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

            #get semester before changed via save()
            past_sem = config.hs_active_semester

            form.save()

            # only do semester updates if semester changed
            if past_sem != config.hs_active_semester:
                messages.warning(request, "New sem: " + str(config.hs_active_semester) + " Old sem: " + str(past_sem))
                Semester.objects.set_active(config.hs_active_semester)
                QuestSubmission.objects.move_incomplete_to_active_semester()

            messages.success(request, "Settings saved")
            #return redirect('/')
    else:
        form = HackerspaceConfigForm()

    return render(request, 'configuration.html', {'form': form, })
