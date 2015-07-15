from django.db import models
from django.contrib.auth.models import User

import datetime
YEAR_CHOICES = []
for r in range(datetime.datetime.now().year, datetime.datetime.now().year+4):
    YEAR_CHOICES.append((r,r)) #(actual value, human readable name) tuples

class Profile(models.Model):
    user = models.OneToOneField(User, related_name="profile_user", null=False, blank=False)
    alias = models.CharField(max_length=50, unique=True, null=True, blank=True)
    first_name = models.CharField(max_length=50, null=False, blank=False)
    last_name = models.CharField(max_length=50, null=False, blank=False)
    preferred_name = models.CharField(max_length=50, null=True, blank=True)
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)
    student_number = models.PositiveIntegerField(unique=True, blank=False, null=False)
    grad_year = models.PositiveIntegerField(choices=YEAR_CHOICES)
    datetime_created = models.DateTimeField(auto_now_add=True, auto_now=False)

    def __str__(self):
        return str(self.user)
