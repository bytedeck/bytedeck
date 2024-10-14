# Generated by Django 3.2.25 on 2024-08-08 15:31

from django.db import migrations
import url_or_relative_url_field.fields


class Migration(migrations.Migration):

    dependencies = [
        ('djcytoscape', '0013_alter_cytoscape_options'),
    ]

    operations = [
        migrations.AlterField(
            model_name='cytoelement',
            name='href',
            field=url_or_relative_url_field.fields.URLOrRelativeURLField(blank=True, max_length=50, null=True),
        ),
    ]
