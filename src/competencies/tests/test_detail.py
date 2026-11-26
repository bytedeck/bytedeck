from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from model_bakery import baker

from competencies.links import competency_link
from competencies.models import Competency, CompetencyAssessment, CompetencyOverride, ProficiencyLevel, QuestCompetency
from competencies.tests.test_approval import set_competencies_flag
from competencies.tests.test_profile_views import own_query_count
from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from quest_manager.models import Category, Quest

User = get_user_model()

DEV, PRF, EXT = ProficiencyLevel.DEVELOPING, ProficiencyLevel.PROFICIENT, ProficiencyLevel.EXTENDING


class CompetencyLinkTest(ByteDeckTenantTestCase):
    """ Tests for Competency.get_absolute_url and competencies.links.competency_link, how every list of
    competencies links one to its page. """

    def setUp(self):
        """ A competency with a course and a category. """
        self.competency = baker.make(Competency, course="ADST 9", category="Defining", name="Choose a design opportunity")

    def test_get_absolute_url__the_competency_page(self):
        """ A competency's own URL is its page """
        self.assertEqual(self.competency.get_absolute_url(), reverse('competencies:detail', args=[self.competency.pk]))

    def test_competency_link__the_name_linked_with_the_full_name_as_title(self):
        """ The link says the name and gives the qualified name (course, category and the whole name) as its
        title; a length cuts the name short, a new tab adds target and rel, and text replaces the name """
        url = self.competency.get_absolute_url()
        title = "ADST 9: Defining: Choose a design opportunity"

        self.assertEqual(competency_link(self.competency), f'<a href="{url}" title="{title}">Choose a design opportunity</a>')
        self.assertEqual(competency_link(self.competency, length=10), f'<a href="{url}" title="{title}">Choose a …</a>')
        self.assertEqual(
            competency_link(self.competency, new_tab=True),
            f'<a href="{url}" title="{title}" target="_blank" rel="noopener">Choose a design opportunity</a>',
        )
        self.assertEqual(competency_link(self.competency, text=title), f'<a href="{url}" title="{title}">{title}</a>')

    def test_competency_link__escapes_the_name(self):
        """ A name with markup in it is shown as text, in the link and in its title """
        self.competency.name = 'Use <b>bold</b> & "quotes"'

        html = competency_link(self.competency)

        self.assertIn('>Use &lt;b&gt;bold&lt;/b&gt; &amp; &quot;quotes&quot;</a>', html)
        self.assertIn('title="ADST 9: Defining: Use &lt;b&gt;bold&lt;/b&gt; &amp; &quot;quotes&quot;"', html)


class CompetencyDetailViewTest(ByteDeckTenantTestCase):
    """ Tests for CompetencyDetailView, the page every list of competencies links to. """

    def setUp(self):
        """ A teacher and a student on a deck with competencies on ("Got It" for level 3), and a competency
        that an open quest, a draft quest and an archived quest give evidence of. """
        set_competencies_flag(True, competency_label_level_3="Got It")
        self.teacher = User.objects.create_user('detail_teacher', is_staff=True)
        self.student = User.objects.create_user('detail_student')
        self.competency = baker.make(
            Competency, course="ADST 9", category="Applied Design - Defining", name="Choose a design opportunity",
            description="Identify a need.\nFrame it as a problem to solve.",
        )
        self.open_quest = baker.make(Quest, name="Brainstorm", published=True)
        self.draft_quest = baker.make(Quest, name="Unfinished Draft", published=False)
        self.archived_quest = baker.make(Quest, name="Old Archived", published=True, archived=True)
        QuestCompetency.objects.create(quest=self.open_quest, competency=self.competency, default_level=EXT)
        QuestCompetency.objects.create(quest=self.draft_quest, competency=self.competency, default_level=DEV)
        QuestCompetency.objects.create(quest=self.archived_quest, competency=self.competency)
        self.url = reverse('competencies:detail', args=[self.competency.pk])

    def test_detail__flag_off_is_404(self):
        """ With competencies off, the page doesn't exist, for staff too """
        set_competencies_flag(False)
        self.client.force_login(self.teacher)
        self.assert404URL(self.url)

    def test_detail__anonymous_must_sign_in(self):
        """ An anonymous visitor is sent to sign in """
        self.assertRedirectsLogin('competencies:detail', args=[self.competency.pk])

    def test_detail__no_such_competency_is_404(self):
        """ A competency that doesn't exist is a 404 """
        self.client.force_login(self.teacher)
        self.assert404('competencies:detail', args=[self.competency.pk + 100])

    def test_detail__staff_see_every_quest(self):
        """ Staff see the full name, course, category and description, and every quest that gives evidence
        of it, with its default level, the ones not open to students marked """
        self.client.force_login(self.teacher)

        response = self.client.get(self.url)

        self.assertContains(response, '<h3 class="competency-detail-name">\n  Choose a design opportunity')
        self.assertContains(response, '<p class="text-muted">ADST 9: Applied Design - Defining</p>')
        self.assertContains(response, '<p>Identify a need.<br>Frame it as a problem to solve.</p>')
        self.assertContains(response, f'<a href="{self.open_quest.get_absolute_url()}">Brainstorm</a>')
        self.assertContains(response, '<small class="text-muted">(default level: Extending)</small>')
        self.assertContains(response, f'<a href="{self.draft_quest.get_absolute_url()}">Unfinished Draft</a>')
        self.assertContains(response, '<small class="text-muted">(default level: Developing; not open to students)</small>')
        self.assertContains(response, f'<a href="{self.archived_quest.get_absolute_url()}">Old Archived</a>')
        self.assertContains(response, '<small class="text-muted">(default level: Got It; not open to students)</small>')
        self.assertContains(response, f'<a href="{reverse("competencies:list")}">All competencies</a>')
        self.assertNotContains(response, "Your current level")
        self.assertNotContains(response, "Inactive")

    def test_detail__staff_with_nothing_linked(self):
        """ A competency no quest gives evidence of says so, and an inactive one is marked """
        self.client.force_login(self.teacher)
        lone = baker.make(Competency, name="Lone competency", active=False)

        response = self.client.get(reverse('competencies:detail', args=[lone.pk]))

        self.assertContains(response, '<p class="text-muted">None yet.</p>')
        self.assertContains(response, 'title="Deactivated: hidden from new use, its evidence kept">Inactive</span>')

    def test_detail__students_see_open_quests_and_their_level(self):
        """ A student sees the quests open to students, without their default levels, and their current
        level in it, linking to their competencies page """
        self.client.force_login(self.student)
        summary = reverse('competencies:summary', args=[self.student.pk])

        response = self.client.get(self.url)

        self.assertContains(response, f'<a href="{self.open_quest.get_absolute_url()}">Brainstorm</a>')
        self.assertNotContains(response, "Unfinished Draft")
        self.assertNotContains(response, "Old Archived")
        self.assertNotContains(response, "default level")
        self.assertNotContains(response, "All competencies")
        self.assertContains(response, '<span class="label label-default" title="Not yet assessed">n/a</span>')
        self.assertContains(response, f'<a href="{summary}">See all your competencies</a>')

        CompetencyAssessment.objects.create(user=self.student, competency=self.competency, level=DEV, assessed_by=self.teacher)
        response = self.client.get(self.url)
        self.assertContains(response, '<span class="label competency-level competency-level-2">Developing</span>.')

        CompetencyOverride.objects.create(user=self.student, competency=self.competency, level=PRF, set_by=self.teacher)
        response = self.client.get(self.url)
        self.assertContains(
            response, '<span class="label competency-level competency-level-3">Got It</span> '
            '<small class="text-muted">(set by your teacher)</small>.',
        )

    def test_detail__queries_dont_grow_with_the_quests(self):
        """ The quests come with their links, not one query each """
        self.client.force_login(self.teacher)
        self.client.get(self.url)  # the first request after signing in also saves the session and profile
        before = self.count_queries()

        for index in range(5):
            QuestCompetency.objects.create(quest=baker.make(Quest, name=f"More {index}", published=True), competency=self.competency)

        self.assertEqual(self.count_queries(), before)

    def count_queries(self):
        """ How many queries the page takes, leaving out the tenant's search_path settings.

        Returns:
            int: the count.
        """
        with CaptureQueriesContext(connection) as queries:
            self.assertEqual(self.client.get(self.url).status_code, 200)
        return own_query_count(queries)


class CompetencyListingsLinkTest(ByteDeckTenantTestCase):
    """ The lists of competencies not covered by their own pages' tests link each competency to its page. """

    def setUp(self):
        """ Competencies on, and a teacher signed in. """
        set_competencies_flag(True)
        self.teacher = User.objects.create_user('listing_teacher', is_staff=True)
        self.client.force_login(self.teacher)
        self.competency = baker.make(Competency, course="ADST 9", category="Defining", name="Choose a design opportunity")
        self.title = "ADST 9: Defining: Choose a design opportunity"

    def test_list__each_competency_linked(self):
        """ The staff list of competencies links each name to its page """
        response = self.client.get(reverse('competencies:list'))

        self.assertContains(
            response, f'<td><a href="{self.competency.get_absolute_url()}" title="{self.title}">Choose a design opportunity</a></td>',
        )

    def test_list__sorts_and_searches_on_the_plain_name(self):
        """ The list's Competency column sorts and searches on a hidden column holding the plain name: bootstrap-table
        sorts and searches a cell by its markup, which for a link is its address and title """
        response = self.client.get(reverse('competencies:list'))

        self.assertContains(response, "data-field='name' data-sort-name='name_sort' data-searchable='false'")
        self.assertContains(response, "<th data-field='name_sort' data-visible='false' data-switchable='false'></th>")
        self.assertContains(response, '<td>Choose a design opportunity</td>')

    def test_campaign_quest_list__each_competency_linked(self):
        """ A campaign's quest list links each quest's competencies to their pages """
        campaign = baker.make(Category, title="Linked Campaign")
        quest = baker.make(Quest, name="Campaign Quest", published=True, campaign=campaign)
        QuestCompetency.objects.create(quest=quest, competency=self.competency)

        response = self.client.get(reverse('quests:category_detail', kwargs={'pk': campaign.pk}))

        self.assertContains(response, f'<a href="{self.competency.get_absolute_url()}" title="{self.title}">Choose a design opportunity</a>')

    def test_quest_form__each_default_level_row_linked_in_a_new_tab(self):
        """ The quest form's default-level rows link each competency to its page in a new tab, so following
        it doesn't lose the form """
        quest = baker.make(Quest, name="Linked Quest")
        QuestCompetency.objects.create(quest=quest, competency=self.competency)

        response = self.client.get(reverse('quests:quest_update', args=[quest.pk]))

        self.assertContains(response, (
            f'<a href="{self.competency.get_absolute_url()}" title="{self.title}" target="_blank" rel="noopener">'
            'Choose a design opportunity</a></label>'
        ))
