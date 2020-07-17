from django.core.management.base import BaseCommand

from prerequisites.tasks import update_quest_conditions_all_users


class Command(BaseCommand):
    help = 'Update all conditons met'

    def handle(self, *args, **options):
        self.stdout.write('Creating conditions met for all users...')
        update_quest_conditions_all_users.apply_async(args=[1], queue='default')
