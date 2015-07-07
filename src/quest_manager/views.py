from django.conf import settings
from django.shortcuts import render
from django.core.mail import send_mail

from .forms import QuestFormCustom, NewQuestForm

def home(request):
    title = "Timberline's Digital Hackerspace - Online"

    form = NewQuestForm(request.POST or None)

    context = {
        "title": title,
        "form": form,
    }

    if form.is_valid():
        ## If not doing additional validation, just save it.
        # form.save

        ## If validating data, don't commit the data yet
        instance = form.save(commit=False)

        title = form.cleaned_data.get("title")
        if not title:
            title = "You didn't enter a title! How is that even possible the form should have forced you to!"

        instance.title = title
        instance.save()

        context = {
            "title": "Quest Successfully Added"
        }


    return render(request, "home.html", context)

## Demo of how to create a form without using a model
def new_quest_custom(request):

    title = 'Creating a New Quest'
    form = NewQuestForm(request.POST or None)

    if form.is_valid():
        ## some ways of doin stuff:

        for key, value in form.cleaned_data.items(): #iteritems() in python 2
            print (key, value)

        # for key in form.cleaned_data:
        #     print (key)
        #     print (form.cleaned_data.get(key))


        # quest = form.cleaned_data.get("quest")
        # xp = form.cleaned_data.get("xp")
        # print (form.cleaned_data)

    context = {
        "form": form,
        "title": title,
    }

    return render(request, "forms.html", context)
##

## Demo of sending email
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
