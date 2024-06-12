import names
import namegenerator
import random

from django.contrib.auth import get_user_model

from quest_manager.models import Quest, Category
from badges.models import Badge

User = get_user_model()


def generate_students(num=100, quiet=False):
    """ Generates 100 students for the current deck (is_staff=False)
    Run with:

    python src/manage.py tenant_command shell
    Enter Tenant Schema ('?' to list schemas): tenant_name

    In [1]: from hackerspace_online.shell_utils import generate_students

    In [2]: generate_students(100)
    """

    if not quiet:
        print(f"Generating {num} students:")
    for _i in range(num):
        # firstname.lastname
        first = names.get_first_name()
        last = names.get_last_name()
        username = f"{first.lower()}.{last.lower()}"
        email = f"{username}@example.com"
        user = User.objects.create(username=username, email=email, first_name=first, last_name=last)

        # print the first two and last two
        if not quiet:
            print(user)

    if not quiet:
        print(f"\n{num} students generated.")


def generate_quests(num_quest_per_campaign=10, num_campaigns=5, quiet=False):
    """ Generates new campaigns with additional quests for each campaign.

    Input:
        num_quest_per_campaign (int): amount of quests that are generated for each new campaign
        num_campaigns (int): how many new campaigns will be generated

        quiet (bool): silences console when generating quests and campaigns
    """

    start_badge = Badge.objects.get(import_id="fa3b0518-cf9c-443c-8fe4-f4a887b495a7")

    if not quiet:
        print("Generating content...")

    for _i in range(num_campaigns):

        # create campaign
        new_campaign = Category.objects.create(
            title=f'Campaign-{namegenerator.gen()}',
        )
        if not quiet:
            print(new_campaign)

        # create initial quest with a prerequisite
        initial_quest = Quest.objects.create(
            name=namegenerator.gen(),
            xp=random.randint(0, 20),
            campaign=new_campaign
        )
        initial_quest.add_simple_prereqs([start_badge])
        last_quest = initial_quest

        if not quiet:
            print('\t' + str(initial_quest))

        # create each subsequent quest using initial_quest as prereq
        for _j in range(num_quest_per_campaign - 1):
            quest = Quest.objects.create(
                name=namegenerator.gen(),
                xp=random.randint(0, 20),
                campaign=new_campaign
            )
            quest.add_simple_prereqs([last_quest])
            last_quest = quest

            if not quiet:
                print('\t' + str(quest))

    if not quiet:
        print(f"{num_quest_per_campaign*num_campaigns} Quests generated in {num_campaigns} campaigns.")


def generate_content(num_quest_per_campaign=10, num_campaigns=5, num_students=100, quiet=False):
    """ Generates quests and students for the current deck
    Run with:

    python src/manage.py tenant_command shell
    Enter Tenant Schema ('?' to list schemas): tenant_name

    In [1]: from hackerspace_online.shell_utils import generate_content

    In [2]: generate_content(10, 5, 100)
    """
    generate_quests(num_quest_per_campaign=num_quest_per_campaign, num_campaigns=num_campaigns, quiet=quiet)

    if not quiet:
        print('\n')

    generate_students(num=num_students, quiet=quiet)
