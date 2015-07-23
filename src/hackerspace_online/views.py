from django.shortcuts import render
from django.contrib.auth.decorators import user_passes_test

@user_passes_test(lambda user: not user.username, login_url='/quests', redirect_field_name=None)
def home(request):
     return render(request, "home.html", {})
