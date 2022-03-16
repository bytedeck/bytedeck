from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from django.db import models
from django.db.models.functions import Lower

User = get_user_model()


class Command(BaseCommand):

    help = 'Used to lowercase usernames'

    @transaction.atomic
    def handle(self, *args, **options):

        # Let's take a list of users that have duplicate usernames
        users = User.objects.values(lowercase_username=Lower('username')).annotate(existing_count=models.Count('lowercase_username'))
        duplicate_usernames = users.filter(existing_count__gt=1).values_list('lowercase_username', flat=True)

        duplicate_users_qs = models.Q()
        for username in duplicate_usernames:
            duplicate_users_qs |= models.Q(username__icontains=username)

        count = User.objects.exclude(duplicate_users_qs).update(username=Lower('username'))

        self.stdout.write(self.style.SUCCESS(f'Updated {count} users!'))

        # Display users that have multiple usernames e.g. Student vs studenT vs STudenT
        # Since we have to take action for those accounts that have different cases
        duplicate_users = User.objects.filter(duplicate_users_qs)
        if duplicate_users.exists():
            self.stdout.write(self.style.NOTICE('List of users with multiple usernames:'))
            for user in duplicate_users:
                self.stdout.write(f"user_id: {user.id}, username: {user.username}")
