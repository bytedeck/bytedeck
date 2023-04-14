"""This module contains the methods to install initial data into a new fixture.
I found fixtures too difficult to update, and django-tenant-schemas doesn't load fixtures properly anyway
I found data migrations to cause too many problems, and they  got in the way squashing migrations and keeping them simple,
among other issues
"""

import os

from django.conf import settings

from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.core.files import File
from django.urls import reverse

from courses.models import Grade, Rank, Course, Block, MarkRange
from quest_manager.models import Quest, Category
from badges.models import Badge, BadgeType, BadgeRarity
from prerequisites.models import Prereq
from siteconfig.models import SiteConfig
from utilities.models import MenuItem

User = get_user_model()


def load_initial_tenant_data():
    create_users()
    create_site_config_object()
    create_initial_course()
    create_initial_blocks()
    create_initial_markranges()
    create_initial_ranks()
    create_initial_grades()
    create_initial_menu_items()
    create_initial_badge_types()
    create_initial_badge_rarities()
    create_initial_badges()
    create_orientation_campaign()

    from notifications.tasks import create_email_notification_tasks
    create_email_notification_tasks()


def set_initial_icons(object_list):
    """
    Sets the icons for a list of objects.  Each object's model must have `name` and `icon` fields.

    Assumes an icon exists at: `static/{app_name}/img/{object.name}.png` and saves it as the object's icon.

    Spaces in names are converted to underscores for the icon filename
    e.g if object_name="Red Team" then will look for an icon named "Red_team.png"
    """

    forbidden_characters = '\\/:*?"<>|'

    for object in object_list:
        icon_file = f"{object._meta.app_label}/img/{object.name.strip(forbidden_characters).replace(' ', '_')}.png"

        filepath = str(finders.find(icon_file))
        # `filepath` here is an absolute filepath, but if we try to open this Django will throw a
        # SuspiciousFileOperation exception because we are traversing outside of the project.
        # So, remove the cwd from the path and we will be left with a relative path to the file
        # E.g. if filepath = '/app/src/badges/static/badges/img/Dime.png' and pwd() = '/app'
        # Then removing the pwd() and a slash will result in the relative path 'src/badges/img/Dime.png'
        cwd = os.getcwd() + "/"  # add a slash to the end of the path cus cwd doesn't include it

        # convert absolute filepath to relative path
        filepath = filepath.replace(cwd, "")

        try:
            with open(filepath, 'rb') as f:
                object.icon.save(filepath, File(f), save=True)
                object.save()
        except OSError:
            # filepath will be None if the finder couldn't find it, so provide more useful feedback
            print(f"Couldn't open icon at {icon_file}")


def create_users():
    # BYTEDECK ADMIN
    User.objects.create_superuser(
        username=settings.TENANT_DEFAULT_ADMIN_USERNAME,
        email='admin@example.com',
        password=settings.TENANT_DEFAULT_ADMIN_PASSWORD
    )
    # OWNER OF THE DECK
    # update_or_create IS HERE BECAUSE siteconfig.models.get_default_deck_owner() will run before this file (initialization.py)
    # although siteconfig.models.get_default_deck_owner() will not run before this every time based on manual testing

    owner, _ = User.objects.update_or_create(
        username=settings.TENANT_DEFAULT_OWNER_USERNAME,
        defaults={
            "email": settings.TENANT_DEFAULT_OWNER_EMAIL,
            "is_superuser": False,
            "is_staff": True,
        },
    )
    owner.set_password(settings.TENANT_DEFAULT_OWNER_PASSWORD,)
    owner.save()

    profile = owner.profile
    profile.get_notifications_by_email = True
    profile.get_announcements_by_email = True
    profile.save()


def create_site_config_object():
    """ Create the single SiteConfig object for this tenant """
    SiteConfig.objects.create()


def create_initial_course():
    Course.objects.create(title="Default")


def create_initial_blocks():
    default_user = SiteConfig.get().deck_owner
    Block.objects.create(name="Default", current_teacher=default_user)


def create_initial_markranges():
    MarkRange.objects.create(name="A", minimum_mark=85.5, color_light="#FFECB3", color_dark="#FFFF00")
    MarkRange.objects.create(name="B", minimum_mark=72.5, color_light="#BEFFFA", color_dark="#337AB7")
    MarkRange.objects.create(name="Pass", minimum_mark=49.5, color_light="#FFB3B3", color_dark="#FF0000")


def create_initial_ranks():
    Rank.objects.create(name="Digital Noob", xp=0, fa_icon="fa fa-circle-o")
    Rank.objects.create(name="Digital Novice", xp=60, fa_icon="fa fa-angle-up")
    Rank.objects.create(name="Digital Novice II", xp=125, fa_icon="fa fa-angle-double-up")
    Rank.objects.create(name="Digital Amateur", xp=185, fa_icon="fa fa-forward fa-rotate-270")
    Rank.objects.create(name="Digital Amateur II", xp=250, fa_icon="fa fa-fast-forward fa-rotate-270")
    Rank.objects.create(name="Digital Apprentice", xp=310, fa_icon="fa fa-th-large")
    Rank.objects.create(name="Digital Apprentice II", xp=375, fa_icon="fa fa-th")
    Rank.objects.create(name="Digitcal Journeyman", xp=495, fa_icon="fa fa-pause fa-rotate-90")
    Rank.objects.create(name="Digitcal Journeyman II", xp=595, fa_icon="fa fa-align-center")
    Rank.objects.create(name="Digitcal Journeyman III", xp=665, fa_icon="fa fa-align-justify")
    Rank.objects.create(name="Digital Crafter", xp=725, fa_icon="fa fa-star-o")
    Rank.objects.create(name="Expert Digital Crafter", xp=855, fa_icon="fa fa-star")
    Rank.objects.create(name="Master Digital Crafter", xp=1000, fa_icon="fa fa-arrows-alt")


def create_initial_grades():
    Grade.objects.create(
        name="8",
        value=8
    )
    Grade.objects.create(
        name="9",
        value=9
    )
    Grade.objects.create(
        name="10",
        value=10
    )
    Grade.objects.create(
        name="11",
        value=11
    )
    Grade.objects.create(
        name="12",
        value=12
    )


def create_initial_badge_types():
    BadgeType.objects.create(
        name="Talent",
        sort_order=1,
        description="Talents are badges that are automatically granted by completing a specific set of prerequisites.",
        repeatable=True,
        fa_icon="fa-hand-spock-o"
    )
    BadgeType.objects.create(
        name="Award",
        sort_order=2,
        description="Awards are badges that are manually granted by teachers.",
        repeatable=True,
        fa_icon="fa-diamond"
    )
    BadgeType.objects.create(
        name="Team",
        sort_order=3,
        description="Teams categorize students into groups for collaboration on projects, access to special quests, etc.",
        repeatable=True,
        fa_icon="fa-handshake-o"
    )


def create_initial_badge_rarities():
    BadgeRarity.objects.create(
        name="Common",
        percentile=100.0,
        color="gray",
        fa_icon="fa-certificate"
    )
    BadgeRarity.objects.create(
        name="Uncommon",
        percentile=30.0,
        color="green",
        fa_icon="fa-certificate"
    )
    BadgeRarity.objects.create(
        name="Rare",
        percentile=16.0,
        color="royalblue",
        fa_icon="fa-certificate"
    )
    BadgeRarity.objects.create(
        name="Epic",
        percentile=4.0,
        color="purple",
        fa_icon="fa-certificate"
    )
    BadgeRarity.objects.create(
        name="Legendary",
        percentile=1.0,
        color="orangered",
        fa_icon="fa-certificate"
    )
    BadgeRarity.objects.create(
        name="Mythic",
        percentile=0.25,
        color="gold",
        fa_icon="fa-certificate"
    )


def create_initial_badges():
    # Talents
    badge_type = BadgeType.objects.get(name="Talent")  # created in previous data migration
    Badge.objects.create(
        name="ByteDeck Proficiency",
        xp=2,
        short_description="<p>You have demonstrated your proficiency with this online platform. I hope you enjoy using it for this course!</p>",
        badge_type=badge_type,
        sort_order=10,
        active=True,
        import_id='fa3b0518-cf9c-443c-8fe4-f4a887b495a7'
    )

    # Awards
    badge_type = BadgeType.objects.get(name="Award")  # created in previous data migration
    award_badges = Badge.objects.bulk_create([
        Badge(
            name="Penny",
            xp=1,
            short_description="<p>According to the Royal Canadian Mint, the official national term of the coin is the <i>one-cent piece</i>, but in practice the terms penny and cent predominate. Originally, \"penny\" referred to a two-cent coin. When the two-cent coin was discontinued, penny took over as the new one-cent coin's name. </p>\r\n\r\n<p>These cents were originally issued to bring some kind of order to the Canadian monetary system, which, until 1858, relied on British coinage, bank and commercial tokens, U.S. currency and Spanish milled dollars. Canada no longer uses the penny, but we still do!</p>",  # noqa
            badge_type=badge_type,
            sort_order=10,
            active=True,
            import_id='033afa34-bd34-4252-80f1-6542a4055f7e'
        ),
        Badge(
            name="Nickel",
            xp=5,
            short_description="<p>The nickel as we are familiar with it was introduced in 1922, originally made from 99.9% nickel metal. These coins were magnetic, due to the high nickel content. Versions during World War II were minted in copper-zinc, then chrome and nickel-plated steel, and finally returned again to nickel, at the end of the war. A plated steel version was again made 1951–54 during the Korean War. Rising nickel prices eventually caused another switch to cupronickel in 1982 (an alloy similar to the U.S. nickel), but more recently, Canadian nickels are minted in nickel-plated steel, containing a small amount of copper.</p>",  # noqa
            badge_type=badge_type,
            sort_order=20,
            active=True,
            import_id='82da2a3a-fb21-4d61-b997-b22978699a51'
        ),
        Badge(
            name="Dime",
            xp=10,
            short_description="<p>According to the Royal Canadian Mint, the official national term of the coin is the <i>10 cent piece</i>, but in practice, the term dime predominates in English-speaking Canada. It is nearly identical in size to the American dime, but unlike its counterpart, the Canadian dime is magnetic due to a distinct metal composition: from 1968 to 1999 it was composed entirely of nickel, and since 2000 it has had a high steel content.</p>",  # noqa
            badge_type=badge_type,
            sort_order=30,
            active=True,
            import_id='bb12b3d1-ce6e-40e3-a411-f43aadfe571a'
        ),
    ])

    # Teams
    badge_type = BadgeType.objects.get(name="Team")
    team_badges = Badge.objects.bulk_create([
        Badge(
            name="Red Team",
            xp=0,
            short_description="<p>You are a member of the Red team!</p>",
            badge_type=badge_type,
            sort_order=10,
            active=True,
            import_id='c71495cf-030e-4c2c-8dd9-8a977502cb9e'
        ),
        Badge(
            name="Green Team",
            xp=0,
            short_description="<p>You are a member of the Green team!</p>",
            badge_type=badge_type,
            sort_order=20,
            active=True,
            import_id='2ad30116-13e9-4ef8-a963-f87a4a2b3663'
        ),
        Badge(
            name="Blue Team",
            xp=0,
            short_description="<p>You are a member of the Blue team!</p>",
            badge_type=badge_type,
            sort_order=30,
            active=True,
            import_id='1f939945-5c02-45cc-ac44-6b8de4100dae'
        ),
    ])

    if not settings.TESTING:
        set_initial_icons(award_badges + team_badges)


def create_initial_menu_items():
    MenuItem.objects.create(
        label="Ranks List",
        fa_icon="star-o",
        url=reverse('courses:ranks'),
        open_link_in_new_tab=False,
        sort_order=0,
        visible=True,
    )


def create_orientation_campaign():
    """ Installs a campaign of several quests including all the prerequisites linking them together
    """

    # the initial quest
    welcome_quest = Quest.objects.create(
        name="Welcome to ByteDeck!",
        xp=3,
        short_description="An introduction to ByteDeck.",
        instructions="<h3>\n    Welcome!\n</h3>\n<p>\n    This is your first intro quest.\n</p>\n<p>\n    This is where you give students information about this quest. You can add images, video tutorials, step-by-step written instructions, links, and anything else students need, in this space.\n</p>\n<p>\n    For this quest, you will probably want to give them a bit of a tour, or explanation, about how you're using ByteDeck. Here's a written intro, in case you want to start with that.\n</p>\n<p>\n    -----\n</p>\n<p>\n</p>\n<p>\n    This website is designed to give you a chance to explore content at your own pace. The content is broken down into larger units (campaigns) and within those are smaller lessons and assignments (quests like this one). As you progress you will need to submit your quests for approval before moving on. This involves following submission instructions and then using the Submit button at the bottom of the quest.\n</p>\n<p>\n    Some quests will be automatically approved and others you will need to wait for an instructor to approve. Your teacher may give you feedback on your submission and/or ask you to fix something about your quest and re-submit it, so make sure you pay attention to any notifications (little numbers that appear next to the bell icon at the top right of your screen).\n</p>\n<p>\n    You can always look at the \"Maps\" (left menu) to see what future quests will be available, so you can continue working without waiting for your quests to be approved.\n</p>",  # noqa
        submission_details="<p>This is where you tell students what they need to do to submit this quest successfully. This quest is automatically approved, so:</p><p>Just submit this quest and the next ones will automatically become available to you.<br></p>",  # noqa
        instructor_notes="<p>This is your teacher cheat sheet - anything that would help you decide whether to approve or return a quest. This quest is automatically approved, so you wouldn't need any notes here, but you will probably find this section useful in future quests.</p>",  # noqa
        import_id="bee53060-c332-4f75-85e1-6a8f9503ebe1",
        hideable=False,
        verification_required=False,

    )

    orientation_campaign = Category.objects.create(
        title="Orientation",
    )

    # create the 4 orientation quests and the 1 message quest
    contract_quest = Quest.objects.create(
        name="ByteDeck Class Contract",
        xp=2,
        short_description="Each student that uses ByteDeck online has a responsibility to use the platform appropriately and respectfully.",
        instructions="<h3>\n    Online Responsibilities\n</h3>\n<p>\n    Even though ByteDeck is online, this is still part of our school. We expect students will behave appropriately and respectfully here, just as they would at school.\n</p>\n<p>\n    <b>Academic Honesty</b>\n</p>\n<p>\n    Students are expected to present their own work. One definition of plagiarism is “using another person’s work and presenting it as your own.” Plagiarism is a form of cheating, and it could be in the form of written, visual, audio, or other media. If another person’s ideas are used, credit must be given in the form of a citation.\n</p>\n<p>\n    <b>Acceptable Use</b>\n</p>\n<p>\n    It is expected that students will only share links and images online if they are considered \"school-appropriate.\" Please use good judgement.\n</p>",  # noqa
        submission_details="<p style=\"\">To complete this quest, copy/paste the paragraph below into your submission, and then type your first and last name to \"sign\" it.</p><p><span style=\"font-size: 1em;\" data-mce-style=\"font-size: 1em;\">\"I will abide by the rules described in this contract. I will ensure</span><span style=\"font-size: 1em;\" data-mce-style=\"font-size: 1em;\"> my online behaviour is appropriate and respectful. My creations will \nbe my own, and where I borrow from the work of others I will properly \nattribute them.\"  -Your first and last name</span></p>",  # noqa
        instructor_notes="<p>Keep an eye out for sneaky students adding \"not\" into the wording. (I've never actually caught anyone doing this, but I still look out for it )<br></p>",  # noqa
        import_id="13fa8c14-f473-4212-b7d0-377fc72f21fd",
        campaign=orientation_campaign,
        hideable=False,
    )
    avatar_quest = Quest.objects.create(
        name="Create an Avatar",
        xp=5,
        short_description="Create a small digital image of yourself to represent you online.",
        instructions="<blockquote>\n    In Hinduism, an <strong>avatar</strong> is a deliberate descent of a deity to Earth, or a descent of the Supreme Being (e.g., Vishnu for Vaishnavites), and is mostly translated into English as \"incarnation\", but more accurately as \"appearance\" or \"manifestation\" - <a href=\"https://en.wikipedia.org/wiki/Avatar\" target=\"_blank\">Wikipedia</a>\n</blockquote>\n<blockquote>\n    In computing, an <strong>avatar</strong> is the graphical representation of the user or the user's alter ego or character. It may take either a three-dimensional form, as in games or virtual worlds, or a two-dimensional form as an icon in Internet forums and other online communities. - <a href=\"https://en.wikipedia.org/wiki/Avatar_%28computing%29\" target=\"_blank\">Wikipedia</a>\n</blockquote>\n<h3>\n    Create your Avatar\n</h3>\n<p>\n    Your avatar should look like you, as much as possible.\n</p>\n<p>\n    Go to <a href=\"https://avatarmaker.com/\" target=\"_blank\"><b>avatarmaker.com</b></a><a href=\"https://avatarmaker.com/\"></a> and create your online manifestation!\n</p>\n<h3>\n    Saving your Avatar\n</h3>\n<p>\n    Click download when you are all done, and choose the 400x400 png file.\n</p>\n<h3>\n    Upload your Avatar\n</h3>\n<ol>\n    <li>\n        Click on your username at the top right of the screen to visit your Profile.\n    </li>\n    <li>\n        To edit your profile, click the blue button at the top beside your name that looks like a cog: <i class=\"fa fa-cog text-primary\"> </i>\n    </li>\n    <li>\n        Scroll down to where it says “Avatar” and click the \"Browse...\" button\n    </li>\n    <li>\n        Locate your avatar image where you saved it, click on it to highlight it, and click “Open”\n    </li>\n    <li>\n        Scroll down to the bottom of your Profile and click “Update”\n    </li>\n</ol>\n<p>\n    Your avatar should now appear next to your name at the top of your Profile.\n</p>",  # noqa
        submission_details="<p>Once you have taken a screenshot of your avatar, you need to do 2 things:<br></p>\n<ol>\n<li>Make sure your profile image shows an avatar that looks like you. </li>\n<li>Include the image in your submission by using the picture icon in your <i>Quest Submission Form</i>'s toolbar <img src=\"/media/django-summernote/2020-04-07/e877f064-2cb7-4cac-be21-4223bc33e0d3.png\" style=\"width: 30px;\"></li>\n</ol>",  # noqa
        instructor_notes="",
        import_id="364ba0d3-04cd-47dd-a83d-002f4bdc88f1",
        campaign=orientation_campaign,
        hideable=False,
    )
    screenshots_quest = Quest.objects.create(
        name="Screenshots",
        xp=2,
        short_description="In this quest, you will learn how to take a screenshot.",
        instructions="<h3>\n    How to take a screenshot\n</h3>\n<p>\n    Many quests require you to take a screenshot. How you do that will depend on what operating system you are using.\n</p>\n<ul>\n    <li>\n        Windows: <a href=\"https://www.cnet.com/how-to/8-ways-you-can-take-screenshots-in-windows-10/\" target=\"_blank\">Snipping Tool or other options</a> OR <a href=\"https://getgreenshot.org/\" target=\"_blank\">Greenshot</a>\n    </li>\n    <li>\n        Mac: <a href=\"https://support.apple.com/en-ca/HT201361\" target=\"_blank\">Shift-Command-4 or Shift-Command-5</a>\n    </li>\n    <li>\n        Ubuntu: use the Screenshot program\n    </li>\n</ul>",  # noqa
        submission_details="<p>Submit a screenshot of this quest!</p>",
        instructor_notes="",
        import_id="472cf428-2c52-4aa7-bc00-56400b04b980",
        campaign=orientation_campaign,
        hideable=False,
    )
    cc_quest = Quest.objects.create(
        name="Who owns your creations?",
        xp=3,
        short_description="Who owns your digital art? Who owns your code? Who owns your creations? This quest teaches you a bit about copyright and introduces you to Creative Commons.",  # noqa
        instructions="<h3>\n    Copyright and Creative Commons\n</h3>\n<p>\n    Every creator in Canada and the US has an automatic copyright on all their creations. There is no longer any requirement to mark your work with the copyright symbol © or to include the words \"All rights reserved\" on the creation.\n</p>\n<p>\n    This means that, except for a few specific exceptions, no one can copy or use your work without your permission, and that includes your teacher!\n</p>\n<p>\n    However, for creators who are interested in sharing their works more openly, or want to legally build on the creative works of others, this is possible through the tools provided by Creative Commons.\n</p>\n<h3>\n    <a href=\"https://creativecommons.org/\" style=\"line-height: 1.1; font-family: inherit; background-color: rgb(255, 255, 255);\"><img alt=\"Creative Commons logo\" height=\"46\" src=\"https://mirrors.creativecommons.org/presskit/logos/cc.logo.png\" style=\"vertical-align: baseline;\" width=\"189\"/></a>\n    <br/>\n</h3>\n<p>\n    <a href=\"https://creativecommons.org/\">Creative Commons</a> is a non-profit organization dedicated to allowing creators to easily and freely share their work with others through the use of six types of copyright licenses. With this system, they are able to release some of the rights to their work while retaining others.\n</p>\n<p>\n    This video provides an introduction to Creative Commons.\n</p>\n<!-- 16:9 aspect ratio -->\n<div class=\"embed-responsive embed-responsive-16by9\">\n    <iframe class=\"embed-responsive-item\" fullscreen=\"\" src=\"https://www.youtube.com/embed/1DKm96Ftfko?rel=0\">\n    </iframe>\n</div>\n<h3>\n    Creative Commons Licenses\n</h3>\n<p>\n    The next video provides an overview of the Creative Commons' license elements, and the resulting six types of copyright licenses. Think about which licenses you would use to share your creations.\n</p>\n<!-- 16:9 aspect ratio -->\n<div class=\"embed-responsive embed-responsive-16by9\">\n    <iframe class=\"embed-responsive-item\" fullscreen=\"\" src=\"https://www.youtube.com/embed/4ZvJGV6YF6Y?rel=0\">\n    </iframe>\n</div>\n<h3>\n    Licenses\n</h3>\n<p>\n    A summary of the six Creative Commons licenses is provided below for reference.\n</p>\n<p style=\"text-align: center; \">\n    <img class=\"img-responsive img-rounded\" src=\"/media/django-summernote/2016-09-08/b2eb86f6-2e3a-4639-87f2-f2a20a1f9cbe.jpg\" style=\"width: 60%;\"/>\n</p>\n<p style=\"text-align: left;\">\n    There is actually a seventh Creative Commons license, called CC0 Public Domain, that has NO restrictions at all when you want to use it, you don't even need to attribute the work to anybody! This symbol indicates the CC0 Public Domain license:\n    <img src=\"https://i.creativecommons.org/p/zero/1.0/88x31.png\" style=\"width: 88px;\"/>\n</p>\n<h3>\n    How to Find Creative Commons licensed media\n</h3>\n<p>\n    In your course you may need to use images, sounds, or other media you find online. You need to ensure that you are using these resources legally and not stealing from other artists.\n</p>\n<p>\n    The easy way to do this is by using the <a href=\"https://search.creativecommons.org/\">Creative Commons search page</a>. There are millions of free resources licensed through the Creative Commons.\n</p>\n<p>\n    Practice finding a Creative Commons licensed image:\n    <br/>\n</p>\n<ol>\n    <li>\n        Go to the <a href=\"https://search.creativecommons.org/\">Creative Commons search page</a>\n    </li>\n    <li>\n        Type in your search query\n    </li>\n    <li>\n        Click on the image you are interested in\n    </li>\n    <li>\n        Find the Creative Commons license information for that image. It should be one of the six licenses in the chart above, or CC0 Public Domain.\n    </li>\n</ol>\n<p>\n    <img class=\"img-responsive img-rounded\" src=\"/media/django-summernote/2018-02-27/7f8233f1-0b0f-4b38-a3b0-023c9305e234.gif\" style=\"width: 826px;\"/>\n    <br/>\n</p>\n<p>\n    For example, this <a href=\"https://www.flickr.com/photos/21518596@N00/3945617179/in/photolist-71Ejwp-epnyjv-71Jkh1-82wsZc-4PAt1p-4PAt1x-7UeAq1-5bv4kp-6udc2i-2dhCQ-4Lwmrg-6udc4T-cJ8vT1-81ksGS-81ktew-81hiQ2-81ksQU-81hiX2-4TA6WN-eBotih-eZ6v9-82wsVr-5NvWdV-7TJsCr-69yk4c-6qwYEh-e6q5iY-bBDH7m-bQyoBV-5NAoyN-7uKfr3-7uFpS8-7Qspp1-4S9Hps-85g4Z5-28TVp-4uELup-6ZiiET-4Vygck-8c5ys5-7UyYuT-bdTTwn-7SM21k-9ChaY1-b8UWP-8EdUCP-71B2DV-8c55xu-2BXhso-3JST2z-9zhVHr\">beautiful picture of an asparagi</a> has an \"Attribution Share Alike\" license. On Flickr, You can see the Creative Commons license icons if you look below the image on the right side.\n</p>",  # noqa
        submission_details="<p>For the last part of the quest you found a free-to-use image with a Creative Commons license. </p>\n<ol><li>Paste a link to the page that includes the image you chose (<a href=\"https://www.flickr.com/photos/21518596@N00/3945617179/in/photolist-71Ejwp-epnyjv-71Jkh1-82wsZc-4PAt1p-4PAt1x-7UeAq1-5bv4kp-6udc2i-2dhCQ-4Lwmrg-6udc4T-cJ8vT1-81ksGS-81ktew-81hiQ2-81ksQU-81hiX2-4TA6WN-eBotih-eZ6v9-82wsVr-5NvWdV-7TJsCr-69yk4c-6qwYEh-e6q5iY-bBDH7m-bQyoBV-5NAoyN-7uKfr3-7uFpS8-7Qspp1-4S9Hps-85g4Z5-28TVp-4uELup-6ZiiET-4Vygck-8c5ys5-7UyYuT-bdTTwn-7SM21k-9ChaY1-b8UWP-8EdUCP-71B2DV-8c55xu-2BXhso-3JST2z-9zhVHr\">like this</a>, do not link directly to the image <a href=\"https://farm4.staticflickr.com/3447/3945617179_c74601a423_z.jpg\">like this</a>).</li><li>Tell me which Creative Commons license the image uses.</li></ol>\n<p> </p>",  # noqa
        instructor_notes="",
        import_id="d8616c21-f7ae-49ae-86c2-b2e1605fe417",
        campaign=orientation_campaign,
        hideable=False,
    )
    message_quest = Quest.objects.create(
        name="Send your teacher a Message",
        xp=0,
        short_description="Use this quest to communicate with your teacher. Send a file, link, message, question, reminder, suggestion, etc.",
        specific_teacher_to_notify=SiteConfig.get().deck_owner,
        instructions="<h3>\n    How this quest works\n</h3>\n<p>\n    You can use this quest however you want. Its main purpose is to allow you to communicate with your teacher. Here are some examples of how you might use it:\n</p>\n<p style=\"padding-left: 30px;\">\n    - Just to say hi\n    <br/>\n    - Send a file (using add attachment)\n    <br/>\n    - Send an interesting link you want your teacher to check out\n    <br/>\n    - Report a problem with the website or a quest etc.\n    <br/>\n    - As a reminder to your teacher of something you told them, that you don't want them to forget\n    <br/>\n    - Send your teacher suggestions, ideas, tips, tricks, etc.\n</p>\n<p>\n    This quest will always be available to you, either in your In Progress or in your Available quest list.\n</p>",  # noqa
        submission_details="<p>Send me your message.</p>",
        instructor_notes="",
        import_id="92c5f839-3523-4d37-a3a9-bf20364bf22e",
        max_repeats=-1,
        available_outside_course=1,
        hideable=False,
    )

    # quests with icons need to have them uploaded programmatically from static files to be displayed properly in development, same as badges.
    if not settings.TESTING:
        set_initial_icons([message_quest, cc_quest, avatar_quest, contract_quest, screenshots_quest])

    # now link them to the welcome quest with pre-requisites:
    Prereq.add_simple_prereq(avatar_quest, welcome_quest)
    Prereq.add_simple_prereq(screenshots_quest, welcome_quest)
    Prereq.add_simple_prereq(contract_quest, welcome_quest)
    Prereq.add_simple_prereq(cc_quest, welcome_quest)

    # add the orientation campaign's quests as a prereq to the ByteDeck Proficiency badge
    proficiency_badge = Badge.objects.get(name='ByteDeck Proficiency')

    proficiency_badge.add_simple_prereqs([avatar_quest, screenshots_quest, cc_quest, contract_quest])

    # Message quest prereq is proficiency badge
    Prereq.add_simple_prereq(message_quest, proficiency_badge)
