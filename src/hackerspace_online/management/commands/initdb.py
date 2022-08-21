from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sites.models import Site
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connections, transaction
from django.db.models.signals import post_save
from django.db.utils import OperationalError
from django.urls import reverse

from django_tenants.models import TenantMixin
from django_tenants.signals import post_schema_sync

from tenant.models import Tenant
from tenant.signals import initialize_tenant_with_data, tenant_save_callback

User = get_user_model()


class Command(BaseCommand):

    help = ('Used to initialize the database, creates a Sites object, creates the public Tenant object, '
            'and creates a superuser for the public schema/tenant.'
            '\nThis should only be run on a fresh db')

    @transaction.atomic
    def handle(self, *args, **options):

        # Check if we are connected to the database
        try:
            connections['default'].cursor()
        except OperationalError:
            self.stdout.write("I can't connect to the database.  Are you sure it's running?")
            self.stdout.write("Try `docker-compose up -d db` then give it a few seconds to boot up")
            self.stdout.write(self.style.NOTICE("Bailing..."))
            return

        self.stdout.write('\n** Running initial migrations on the public schema...')
        call_command("migrate_schemas", "--shared")

        # Create super user on the public schema ###############################################
        self.stdout.write('\n** Creating superuser...')
        if User.objects.filter(username=settings.DEFAULT_SUPERUSER_USERNAME).exists():
            self.stdout.write(self.style.NOTICE(f'A superuser with username `{settings.DEFAULT_SUPERUSER_USERNAME}` already exists'))
            self.stdout.write(self.style.NOTICE("Bailing..."))
            return

        User.objects.create_superuser(
            username=settings.DEFAULT_SUPERUSER_USERNAME,
            email=settings.DEFAULT_SUPERUSER_EMAIL,
            password=settings.DEFAULT_SUPERUSER_PASSWORD
        )

        self.stdout.write("Superuser")
        self.stdout.write(f" username: {settings.DEFAULT_SUPERUSER_USERNAME}")
        self.stdout.write(f" password: {settings.DEFAULT_SUPERUSER_PASSWORD}")
        self.stdout.write(f" email: {settings.DEFAULT_SUPERUSER_EMAIL}")

        # Create the `public` Tenant object ###############################################

        # Disconnect from the post_schema_sync when creating public tenant since this will
        # be the `public` schema and we don't want to initialize tenant specific data
        post_schema_sync.disconnect(initialize_tenant_with_data, sender=TenantMixin)

        # Also disconnect from the tenant_save_callback so it wont create unnecessary domains
        post_save.disconnect(tenant_save_callback, sender=Tenant)

        self.stdout.write(self.style.SUCCESS('\n** Creating `public` Tenant object...'))
        public_tenant, created = Tenant.objects.get_or_create(
            schema_name='public',
            name='public'
        )

        public_tenant.domains.create(
            domain=settings.ROOT_DOMAIN,
            is_primary=True
        )

        if not created:
            self.stdout.write(self.style.NOTICE('\nA schema with the name `public` already existed.  A new one was not created.'))

        self.stdout.write(self.style.SUCCESS('\nPublic Tenant object'))
        self.stdout.write(f" tenant.domain_url: {public_tenant.get_primary_domain().domain}")
        self.stdout.write(f" tenant.schema_name: {public_tenant.schema_name}")
        self.stdout.write(f" tenant.name: {public_tenant.name}")

        self.stdout.write(self.style.SUCCESS('\n** Updating Sites object...'))
        site = Site.objects.first()
        site.domain = settings.ROOT_DOMAIN
        site.name = settings.ROOT_DOMAIN[:45]  # Can be too long if using an AWS public DNS
        site.save()

        self.stdout.write("\nSites object")
        self.stdout.write(f" site.domain: {site.domain}")
        self.stdout.write(f" site.name: {site.name}")
        self.stdout.write(f" site.id: {site.id}")

        # Create the homepage, which is a flatpage object for easier
        self.stdout.write(self.style.SUCCESS('\n** Creating homepage...'))
        from django.contrib.flatpages.models import FlatPage

        homepage = FlatPage.objects.create(
            url='/home/',
            title='Home',
            content=get_homepage_content(),
            template_name='public/flatpage-wide.html',
        )
        homepage.sites.add(site)
        absolute_url = reverse('django.contrib.flatpages.views.flatpage', args=['home'])
        self.stdout.write(f" homepage: {public_tenant.get_root_url()}{absolute_url}\n")

        # Connect again
        post_schema_sync.connect(initialize_tenant_with_data, sender=TenantMixin)
        post_save.connect(tenant_save_callback, sender=Tenant)


def get_homepage_content():
    return """
<!-- Heading Row-->
    
<div class="BG-BD-White" id="top">
    <div class="row justify-content-center">
      <!-- <div class="col-lg-1"></div> -->
      <div class="col-lg-6 col-xl-5 BD-content1 ">
        <div class="BD-title BD-title-pixels">
          <img class="bd-wordmark img-fluid" src="https://d10ge8y4vx8iud.cloudfront.net/static/public/images/wordmark-v2.png">
        </div>
        <p class="lead">ByteDeck is a learning management system created BY teachers and students FOR teachers and students.</p>
        <p class="lead">ByteDeck is different than other learning management systems. It's flexible in how teachers deliver content, 
        and supports teachers who take a less traditional approach to education.</p>
        <p class="lead">ByteDeck is easy for both teachers and students to use. Teachers and students can use it in any setting, 
        whether you are working in a classroom, remotely, or both. </p>
        <div class="row">
          <div class="col-md-4">
            <a class="btn btn-block BD-btn BD-bg-LightBlue BD-btn-LightBlue-1" href="#how" role="button">HOW IT WORKS</a>
          </div>
          <div class="col-md-4">
            <a class="btn btn-block BD-btn BD-bg-LightBlue BD-btn-LightBlue-1" href="#teachers" role="button">TEACHERS</a>
          </div>
          <div class="col-md-4">
            <a class="btn btn-block BD-btn BD-bg-LightBlue BD-btn-LightBlue-1" href="#contact" role="button">TRY IT</a>
          </div>
        </div>
        <!-- /row -->
      </div>
      <div class="col-lg-5 d-flex justify-content-center align-items-center">
        <img class="BD-main-img img-fluid" src="https://d10ge8y4vx8iud.cloudfront.net/static/public/images/undraw_press_play_revised2.png" alt="">
      </div>
      <!-- <div class="col-lg-1"></div> -->
    </div>

      <!-- /row -->
  </div>
    <!-- /Heading Row-->

    <!-- What is BD row -->
    
<div class="BD-bg-DarkBlue" id="WhatisByteDeck">

    <div class="row BD-content2 text-center">
      <div class="col-12">
        <h1-bd>WHY CHOOSE BYTEDECK?</h1-bd>
      </div>
    </div>

    <div class="row justify-content-center mx-5 mx-md-0 mx-lg-5 mx-xl-0">
      <!-- <div class="col-lg-1 col-xl-2"></div> -->

      <div class="col-md-3 col-xl-2 text-center BD-content3">
        <img class="img-center console-img-size-1 " src="https://d10ge8y4vx8iud.cloudfront.net/static/public/images/laptop-code-solid%201.png">
        <h2 style="font-size:23px">Easy to Use</h2>
        <p style="font-size:16px">The interface is intuitive, responsive, and mobile-friendly. Students can use ByteDeck on any device, 
        anywhere they have access to the internet.</p>
      </div>

      <div class="col-md-3 col-xl-2 offset-md-1 text-center BD-content3">
        <img class="img-center gamepad-img-size-1 " src="https://d10ge8y4vx8iud.cloudfront.net/static/public/images/gamepad-solid%201.png">
        <h2 style="font-size:23px">Quest-Based Learning</h2>
        <p style="font-size:16px">The quest format makes it easy for teachers to break learning into small chunks. Students are motivated 
        to "level up" as they work through quests.</p>
      </div>

      <div class="col-md-3 col-xl-2 offset-md-1 text-center BD-content3">
        <img class="img-center  apple-img-size-1" src="https://d10ge8y4vx8iud.cloudfront.net/static/public/images/apple-alt-solid%201.png">
        <h2 style="font-size:23px">Flexibility and Choice</h2>
        <p style="font-size:16px">Students work through quests at their own pace. Create one learning path for all students, or multiple 
        paths to provide students with more choice.</p>
      </div>

      <!-- <div class="col-lg-1 col-xl-2"></div> -->

    </div>
    <!-- /.row -->
  </div>
    <!-- /What is BD row-->

    <!-- How it Works row -->
    
  <div id="how">
    <div class="row">
      <div class="col-lg-7 BD-bg-LightBlue">
        <div class="row">
          <div class="col-lg-10 offset-lg-1 BD-content1">
            <div class="BD-title BD-title-pixels ">
              <h1-bd>HOW IT WORKS</h1-bd>
              <div>
                <img class="BD-img-pixels-topright BD-img-pixels" src="https://d10ge8y4vx8iud.cloudfront.net/static/public/images/pixels%203.png">
              </div>
            </div>
            <p class="lead">ByteDeck uses quest-based learning, an instructional design theory that leverages game mechanics to support 
            student engagement and motivation.
            </p><ul class="lead">
              <li>Your lessons become "quests."</li>
              <li>Units of study become "campaigns."</li>
              <li>Marks become experience points, "XP."</li>
            </ul>
            <p class="lead">Quests are a great way to scaffold student learning. Break down your lessons into small chunks, and support students 
            as they "level up" and move from basic to more complex concepts.</p>
            <p class="lead">Learning is continuous. Students work through quests at their own pace.</p>
            <p class="lead">Quests can vary. Some may be short, prescribed activities that show students' understanding. Others may be 
            open-ended, self-directed activities, where students can showcase their learning and creativity.</p>
            <div class="row">
              <div class="col-lg-4 BD-title-pixels">
                <a class="btn btn-block BD-btn BD-bg-DarkBlue" href="#contact" role="button">TRY IT!</a>
                <!-- <div>
                  <img class="students-pixels BD-img-pixels" src="https://d10ge8y4vx8iud.cloudfront.net/static/public/images/pixels%203.png">
                </div> -->
              </div>
            </div> <!-- /button row -->
          </div> <!-- /col-10 -->
        </div> <!-- /content row -->
      </div> <!-- /content col -->
      <div class="col-lg-5 d-flex justify-content-center align-items-center order-xl-last order-lg-last order-first order-sm-first 
      order-md-first BD-bg-White">
        <img class="img-fluid BD-undraw-img BD-undraw-img-right" 
        src="https://d10ge8y4vx8iud.cloudfront.net/static/public/images/undraw_video_game_night_rev.png" alt="">
      </div>
    </div>

  </div>
    <!-- /How BD Works row-->

    <!-- Teachers row -->
    
<div id="teachers">
    <div class="row">
      <div class="col-lg-5 d-flex justify-content-center align-items-center BD-bg-White">
        <img class="img-fluid BD-undraw-img BD-undraw-img-left" 
        src="https://d10ge8y4vx8iud.cloudfront.net/static/public/images/undraw_teaching_revised2.png" alt="">
      </div>
      <div class="col-lg-7 BD-bg-Yellow">
        <div class="row">
          <div class="col-lg-10  offset-lg-1 BD-content1">
            <div class="BD-title BD-title-pixels">
              <h1-bd>TEACHERS</h1-bd>
              <div>
                <img class="BD-img-pixels-topright BD-img-pixels" src="https://d10ge8y4vx8iud.cloudfront.net/static/public/images/pixels%202.png">
              </div>
            </div>
            <p class="lead">As a teacher, you decide whether students will all follow a single learning pathway, or have access 
            to a range of pathways they can choose from. Either way, students can always see what their options are, and what comes next.</p>
            <p class="lead">Students can submit quests regularly, whether their work is complete or in-progress. Teachers can 
            provide feedback as needed, and assessment is ongoing.</p>
            <p class="lead">Students' progress through campaigns is continuously tracked, so both students and teachers know exactly 
            where they're at.</p>
            <div class="row">
              <div class="col-lg-4">
                <a class="btn btn-block BD-btn BD-bg-LightBlue BD-bg-LightBlue BD-btn-LightBlue-2" href="#contact" role="button">TRY IT!!</a>
              </div>
            </div>
          </div>
        </div> <!-- /content row -->
      </div> <!-- /content col -->
    </div><!-- /row -->

  </div>
    <!-- /Teachers row-->
    """
