from django.db import models
from django.contrib.auth.models import User

import datetime
YEAR_CHOICES = []
for r in range((datetime.datetime.now().year, (datetime.datetime.now().year+4)):
    YEAR_CHOICES.append((r,r))

year = models.IntegerField(_('year'), max_length=4, choices=YEAR_CHOICES, default=datetime.datetime.now().year)

class profile(models.Model):
    user = models.OneToOneField(User, related_name="profile", null=True, blank=True)
    alias = models.CharField(max_length=50, unique=True, null=True, blank=True)
    first_name = models.CharField(max_length=50, unique=False, null=True, blank=True)
    last_name = models.CharField(max_length=50, unique=False, null=True, blank=True)
    preferred_name = models.CharField(max_length=50, unique=True, null=True, blank=True)
    avatar = icon = models.ImageField(upload_to='avatars/', null=True, blank=True)
    student_number = models.PositiveIntegerField(max_length=7 blank=False, null=False)
    grad_year = models.IntegerField(_('year'), max_length=4, choices=YEAR_CHOICES)
    datetime_created = models.DateTimeField(auto_now_add=True, auto_now=False)

    def __str__(self):
        return str(self.user)
