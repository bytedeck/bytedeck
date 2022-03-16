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

        # First let's take all users that have 0 duplicates
        users = User.objects.values('username').annotate(existing_count=models.Count(Lower('username')))

        unique_usernames = users.filter(existing_count=1).values_list('username', flat=True)

        # Update their usernaems to lowercase
        count = User.objects.filter(username__in=unique_usernames).update(username=Lower('username'))
        self.stdout.write(self.style.SUCCESS(f'Updated {count} users!'))

        # Display users that have multiple usernames e.g. Student vs studenT vs STudenT
        # Since we have to take action for those accounts that have different cases
        non_unique_users = User.objects.filter(~models.Q(username__in=unique_usernames))
        if non_unique_users:
            self.stdout.write(self.style.NOTICE('List of users with multiple usernames: \n'))
            for user in non_unique_users:
                self.stdout.write(f"{user}, {user.id}, {user.username}")
