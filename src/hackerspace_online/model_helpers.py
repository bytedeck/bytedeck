from django.db import models
from django.contrib.auth.models import User


def get_teachers_field(proxy_model_name: str, related_name: str = None):
    return models.ManyToManyField(User, related_name=related_name, through=proxy_model_name)


# class TeacherProxyMixin:
#     is_owner = models.BooleanField(default=False)
#     is_creator = models.BooleanField(default=False)
