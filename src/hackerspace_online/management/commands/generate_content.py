from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django_tenants.utils import schema_context
from tenant.models import Tenant

from hackerspace_online.shell_utils import generate_content

User = get_user_model()


class Command(BaseCommand):
    help = 'This command procedurally generates quests, campaigns, and students'

    def add_arguments(self, parser):
        # argument(s)
        parser.add_argument('schema_name', action='store', type=str, help='The name of the tenant/schema you want to add content to.')

        # optional arguments
        parser.add_argument(
            '--num_quests_per_campaign', action='store', type=int, help='Number of new quests per campaign created.\nIf left empty defaults to 10'
        )
        parser.add_argument('--num_campaigns', action='store', type=int, help='Number of new campaign created.\nIf left empty defaults to 5')
        parser.add_argument('--num_students', action='store', type=int, help='Number of new students created.\nIf left empty defaults to 100')
        parser.add_argument(
            '--quiet', action='store_true', help='This determines if command prints what it generates in the console. Defaults to False'
        )

    def handle(self, *args, **options):
        # grab variables
        schema_name = options.get('schema_name')
        num_quests_per_campaign = options.get('num_quests_per_campaign') or 10
        num_campaigns = options.get('num_campaigns') or 5
        num_students = options.get('num_students') or 100
        quiet = options.get('quiet') or False

        # error handling
        try:
            tenant = Tenant.objects.get(schema_name=schema_name)
        except Tenant.DoesNotExist:
            raise CommandError(f'Error: Schema name: "{schema_name}" does not exist!')

        # tenant exist, proceed
        with schema_context(tenant.schema_name):
            # proceed with generation
            generate_content(
                num_quests_per_campaign,
                num_campaigns,
                num_students,
                quiet,
            )
