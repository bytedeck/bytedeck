from django.conf import settings
from django.shortcuts import render, get_object_or_404
from django.core.mail import send_mail
from django.template import RequestContext, loader
from .forms import QuestFormCustom, NewQuestForm
from .models import Quest
from django.http import HttpResponse

from django.contrib.auth.decorators import login_required

@login_required
def quests(request):
    title = "Quests"
    heading = "Quests"

    # quest_list = Quest.objects.order_by('name')
    quest_list = Quest.objects.get_active()
    output = ', '.join([p.name for p in quest_list])

    # return HttpResponse(output)
    print(quest_list[5].icon)

    context = {
        "title": title,
        "heading": heading,
        "quest_list": quest_list,
    }

    return render(request, "quest_manager/quests.html", context)

@login_required
def detail(request, quest_id):
    title = "Quests"
    heading = "Quest Detail"

    q = get_object_or_404(Quest, pk=quest_id)

    context = {
        "title": title,
        "heading": ("Quest: %s" % q.name),
        "q": q,
    }
    return render(request, 'quest_manager/detail.html', context)

## Demo of sending email
@login_required
def email_demo(request):
    subject = "Test email from Hackerspace Online"
    from_email = ("Timberline's Digital Hackerspace <" +
        settings.EMAIL_HOST_USER +
        ">")
    to_emails = [from_email]
    email_message = "from %s: %s via %s" %(
        "Dear Bloggins", "sup", from_email)

    html_email_message = "<h1> if this is showing you received an HTML messaage</h1>"

    send_mail(subject,
        email_message,
        from_email,
        to_emails,
        html_message = html_email_message,
        fail_silently=False)

    context = {
        "email_to" : to_emails,
        "email_from": from_email,
        "email_message":email_message,
        "html_email_message": html_email_message

    }

    return render(request, "email_demo.html", context)


##
