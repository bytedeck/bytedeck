from django.db import models

# Create your models here.
class Icon(models.Model):
    icon_name = models.CharField(max_length=50)
    icon_image = models.ImageField(upload_to='icons/', blank=True, null=True)