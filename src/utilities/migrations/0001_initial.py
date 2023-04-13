# Generated by Django 1.11.17 on 2018-12-28 03:51

from django.db import migrations, models
import url_or_relative_url_field.fields


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='ImageResource',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=50)),
                ('image', models.ImageField(height_field='height', upload_to='images/', width_field='width')),
                ('height', models.PositiveIntegerField(editable=False)),
                ('width', models.PositiveIntegerField(editable=False)),
                ('datetime_created', models.DateTimeField(auto_now_add=True)),
                ('datetime_last_edit', models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name='MenuItem',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('label', models.CharField(help_text='This is the text that will appear for the menu item.', max_length=25)),
                ('fa_icon', models.CharField(default='link', help_text="The Font Awesome icon to display beside the text. E.g. 'star-o'. Options from <a target='_blank'href='http://fontawesome.com/v4.7.0/icons/'>Font Awesome</a>.", max_length=50)),
                ('url', url_or_relative_url_field.fields.URLOrRelativeURLField(help_text="Relative URLs will work too.  E.g. '/courses/ranks/'")),
                ('open_link_in_new_tab', models.BooleanField()),
                ('sort_order', models.IntegerField(default=0, help_text='Lowest will be at the top.')),
                ('visible', models.BooleanField(default=True)),
            ],
            options={
                'ordering': ['sort_order'],
            },
        ),
        migrations.CreateModel(
            name='VideoResource',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=50)),
                ('video_file', models.FileField(upload_to='videos/')),
                ('datetime_created', models.DateTimeField(auto_now_add=True)),
                ('datetime_last_edit', models.DateTimeField(auto_now=True)),
            ],
        ),
    ]
