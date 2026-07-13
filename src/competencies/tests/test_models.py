from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError

from django_tenants.test.cases import TenantTestCase
from model_bakery import baker

from competencies.models import Competency, CompetencyAssessment, ProficiencyLevel, QuestCompetency
from quest_manager.models import Quest, QuestSubmission

User = get_user_model()


class ProficiencyLevelTest(TenantTestCase):

    def test_level_values(self):
        """ Levels are stored as ints on the BC 4-point scale so aggregation/comparison is trivial """
        self.assertEqual(ProficiencyLevel.EMERGING, 1)
        self.assertEqual(ProficiencyLevel.DEVELOPING, 2)
        self.assertEqual(ProficiencyLevel.PROFICIENT, 3)
        self.assertEqual(ProficiencyLevel.EXTENDING, 4)


class CompetencyModelTest(TenantTestCase):

    def setUp(self):
        self.competency = baker.make(Competency, name="Communicating")

    def make_assessment(self, competency):
        """ baker.make(CompetencyAssessment) would fill the generic FK's content type with a
        random model — any installed model, even table-less throwaway classes leaked into the
        app registry by other tests — making the suite randomly flaky.
        Build a deterministic assessment instead. """
        return CompetencyAssessment.objects.create(
            user=baker.make(User),
            competency=competency,
            level=ProficiencyLevel.PROFICIENT,
        )

    def test_object_creation(self):
        self.assertIsInstance(self.competency, Competency)
        self.assertEqual(str(self.competency), "Communicating")
        self.assertTrue(self.competency.active)

    def test_active_queryset(self):
        inactive_competency = baker.make(Competency, active=False)
        active_qs = Competency.objects.active()
        self.assertIn(self.competency, active_qs)
        self.assertNotIn(inactive_competency, active_qs)

    def test_soft_delete_via_active_flag(self):
        """ Deactivating a competency doesn't remove it or its related objects """
        assessment = self.make_assessment(self.competency)
        self.competency.active = False
        self.competency.save()

        self.assertTrue(Competency.objects.filter(pk=self.competency.pk).exists())
        self.assertTrue(CompetencyAssessment.objects.filter(pk=assessment.pk).exists())

    def test_delete_protected_when_evidence_exists(self):
        """ A competency referenced by assessment evidence can never be hard-deleted """
        self.make_assessment(self.competency)
        with self.assertRaises(ProtectedError):
            self.competency.delete()

    def test_delete_allowed_without_evidence(self):
        """ A competency with no assessment evidence can be hard-deleted,
        even if it is linked to quests (the links are just authoring config) """
        baker.make(QuestCompetency, competency=self.competency)
        self.competency.delete()
        self.assertFalse(Competency.objects.filter(name="Communicating").exists())
        self.assertFalse(QuestCompetency.objects.exists())


class QuestCompetencyModelTest(TenantTestCase):

    def setUp(self):
        self.quest = baker.make(Quest, name="Test Quest")
        self.competency = baker.make(Competency, name="Creative Thinking")
        self.quest_competency = QuestCompetency.objects.create(quest=self.quest, competency=self.competency)

    def test_object_creation(self):
        self.assertIsInstance(self.quest_competency, QuestCompetency)
        self.assertEqual(str(self.quest_competency), "Test Quest - Creative Thinking")

    def test_default_level_is_proficient(self):
        """ Completing a quest generally demonstrates Proficient, so that's the default """
        self.assertEqual(self.quest_competency.default_level, ProficiencyLevel.PROFICIENT)

    def test_unique_together_quest_competency(self):
        """ A competency can only be attached to a quest once """
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                QuestCompetency.objects.create(quest=self.quest, competency=self.competency)

        # but the same competency can be attached to a different quest
        other_quest = baker.make(Quest)
        QuestCompetency.objects.create(quest=other_quest, competency=self.competency)
        self.assertEqual(QuestCompetency.objects.count(), 2)

    def test_quest_delete_removes_link_but_not_competency(self):
        self.quest.delete()
        self.assertFalse(QuestCompetency.objects.exists())
        self.assertTrue(Competency.objects.filter(pk=self.competency.pk).exists())


class CompetencyAssessmentModelTest(TenantTestCase):

    def setUp(self):
        self.student = baker.make(User)
        self.teacher = baker.make(User, is_staff=True)
        self.competency = baker.make(Competency)
        self.quest = baker.make(Quest)
        self.submission = baker.make(QuestSubmission, quest=self.quest, user=self.student)

    def make_assessment(self, **kwargs):
        kwargs.setdefault('user', self.student)
        kwargs.setdefault('competency', self.competency)
        kwargs.setdefault('level', ProficiencyLevel.PROFICIENT)
        kwargs.setdefault('assessed_by', self.teacher)
        kwargs.setdefault('source_object', self.submission)
        return CompetencyAssessment.objects.create(**kwargs)

    def test_object_creation(self):
        assessment = self.make_assessment()
        self.assertIsInstance(assessment, CompetencyAssessment)
        self.assertIsNotNone(assessment.timestamp)
        self.assertEqual(
            str(assessment),
            f"{self.student}: {self.competency} = Proficient"
        )

    def test_level_choices_validation(self):
        """ Only levels 1-4 are valid """
        for level in ProficiencyLevel.values:
            self.make_assessment(level=level).full_clean()

        assessment = self.make_assessment()
        assessment.level = 5
        with self.assertRaises(ValidationError):
            assessment.full_clean()

    def test_generic_fk_round_trip(self):
        """ The source of the evidence can be saved and retrieved via the generic FK """
        assessment = self.make_assessment()

        assessment.refresh_from_db()
        self.assertEqual(assessment.source_object, self.submission)
        self.assertEqual(assessment.source_content_type, ContentType.objects.get_for_model(QuestSubmission))
        self.assertEqual(assessment.source_object_id, self.submission.id)

        # and evidence can be queried by its source
        qs = CompetencyAssessment.objects.filter(
            source_content_type=ContentType.objects.get_for_model(QuestSubmission),
            source_object_id=self.submission.id,
        )
        self.assertEqual(list(qs), [assessment])

    def test_quest_deletion_does_not_delete_assessments(self):
        """ Evidence outlives the quest: deleting a Quest cascades to its submissions,
        but assessments sourced from those submissions must survive (with a dangling,
        None-resolving source_object) """
        assessment = self.make_assessment()

        self.quest.delete()
        self.assertFalse(QuestSubmission.objects.filter(pk=self.submission.pk).exists())

        assessment.refresh_from_db()
        self.assertIsNone(assessment.source_object)
        self.assertEqual(assessment.competency, self.competency)
        self.assertEqual(assessment.level, ProficiencyLevel.PROFICIENT)

    def test_assessed_by_set_null_on_teacher_deletion(self):
        """ Evidence also outlives the assessing teacher's account """
        assessment = self.make_assessment()
        self.teacher.delete()
        assessment.refresh_from_db()
        self.assertIsNone(assessment.assessed_by)

    def test_assessed_by_nullable_for_self_or_system_assessment(self):
        assessment = self.make_assessment(assessed_by=None)
        assessment.full_clean()
        self.assertIsNone(assessment.assessed_by)

    def test_student_deletion_cascades_assessments(self):
        """ Evidence is meaningless without its student """
        self.make_assessment()
        self.student.delete()
        self.assertFalse(CompetencyAssessment.objects.exists())

    def test_ordering_most_recent_first(self):
        first = self.make_assessment(level=ProficiencyLevel.DEVELOPING)
        second = self.make_assessment(level=ProficiencyLevel.PROFICIENT)
        self.assertEqual(list(CompetencyAssessment.objects.all()), [second, first])
