from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from prerequisites.models import Prereq, PrereqAllConditionsMet
from quest_manager.models import Quest, QuestSubmission

User = get_user_model()


class Command(BaseCommand):
    """Explain why a quest is, or is not, in a student's Available tab.

    The tab and "can I start this?" are two different code paths, which is why a quest can be
    missing from the list and still open from the quest map or its own URL:

    * starting goes through ``Quest.is_available()``, which works the prerequisites out live
    * the tab goes through ``Quest.objects.get_available()``, which reads the *cached*
      prerequisite result and then applies two more filters the other path never sees:
      repeats and cooldown, and the quests the student has hidden

    Blocking quests are read from one place by both (``QuestManager.get_blocking_quests``), so a
    quest a blocking quest holds out of the tab cannot be started either.

    So this walks the tab's filters in order, says which one dropped the quest, and compares
    the cached prerequisite answer against a live one so a stale cache is named as such
    rather than guessed at.

    It is a tenant app, so run it against one deck::

        python src/manage.py tenant_command quest_availability --schema=hackerspace <username>

    With no ``--quest`` it reports every quest that is startable but missing from the tab,
    which is the question a teacher actually arrives with.
    """

    help = (
        "Explain why a quest is or is not in a student's Available tab: which of the tab's "
        "filters dropped it, and whether the cached prerequisite answer still matches a live "
        "one. With no --quest, lists every quest the student can start but cannot see. "
        "Run per deck with tenant_command."
    )

    def add_arguments(self, parser):
        """Take the student to look at, and optionally one quest and a cache rebuild."""
        parser.add_argument('username', help="the student whose Available tab to explain")
        parser.add_argument(
            '--quest', dest='quest',
            help="one quest, by id or by a piece of its name, instead of the whole tab",
        )
        parser.add_argument(
            '--rebuild', action='store_true',
            help=(
                "recompute this student's cached prerequisite results here and now, without "
                "celery, and save them. Use when the report says the cache is stale."
            ),
        )

    def handle(self, *args, **options):
        """Print the report, and rebuild the student's cache first when asked to."""
        user = self.get_user(options['username'])

        if options['rebuild']:
            self.rebuild_cache(user)

        self.report_cache_health(user)

        if options['quest']:
            self.report_one_quest(user, self.get_quest(options['quest']))
        else:
            self.report_startable_but_unlisted(user)

    # Looking things up ###################################################

    def get_user(self, username):
        """Find the student to report on.

        Args:
            username (str): their username.

        Returns:
            User: the student.

        Raises:
            CommandError: when no such user is on this deck.
        """
        user = User.objects.filter(username=username).first()
        if user is None:
            raise CommandError(f"No user '{username}' on this deck. Check the --schema.")
        return user

    def get_quest(self, quest):
        """Find the quest to report on, by id or by name.

        Archived quests are included: one archived out from under a student is exactly the
        kind of thing this command is asked about.

        Args:
            quest (str): a quest id, or a piece of a quest name.

        Returns:
            Quest: the matching quest.

        Raises:
            CommandError: when nothing matches, or when a name matches more than one quest.
        """
        quests = Quest.objects.all_including_archived()
        if quest.isdigit():
            found = quests.filter(id=int(quest)).first()
            if found is None:
                raise CommandError(f"No quest with id {quest} on this deck.")
            return found

        matches = list(quests.filter(name__icontains=quest)[:10])
        if not matches:
            raise CommandError(f"No quest matching '{quest}' on this deck.")
        if len(matches) > 1:
            names = "\n  ".join(f"{q.id}: {q.name}" for q in matches)
            raise CommandError(f"'{quest}' matches several quests; use the id:\n  {names}")
        return matches[0]

    # The cache ###########################################################

    def live_met_ids(self, user):
        """Work out, live, which quests this student meets the prerequisites for.

        This is what the cache is a cache *of*: the same loop the celery task runs.

        Args:
            user (User): the student.

        Returns:
            set[int]: the ids of the quests whose prerequisites they meet.
        """
        return {quest.pk for quest in Quest.objects.all() if Prereq.objects.all_conditions_met(quest, user)}

    def cached_met_ids(self, user):
        """Read the student's stored prerequisite results, which the Available tab is built from.

        Args:
            user (User): the student.

        Returns:
            set[int] or None: the cached quest ids, or None when they have no cache row at all
            (in which case the tab computes one on the spot, so it cannot be stale).
        """
        row = PrereqAllConditionsMet.objects.filter(
            user=user, model_name=Quest.get_model_name(),
        ).first()
        return None if row is None else set(row.get_ids())

    def rebuild_cache(self, user):
        """Recompute and store this student's prerequisite results, synchronously.

        The `update_conditions` command hands this to celery, so it does nothing while a worker
        is down or its queue is backed up. This does the work in process, which is what makes it
        usable for getting one stuck student moving again.

        Args:
            user (User): the student whose cache to rebuild.
        """
        met = sorted(self.live_met_ids(user))
        PrereqAllConditionsMet.objects.update_or_create(
            user=user, model_name=Quest.get_model_name(), defaults={'ids': str(met)},
        )
        self.stdout.write(self.style.SUCCESS(f"Rebuilt the cache for {user.username}: {len(met)} quests.\n"))

    def report_cache_health(self, user):
        """Say whether the stored prerequisite results still match a live calculation.

        A stale cache is the reason a quest can be startable and invisible at once, and nothing
        repairs one by itself: the tab recomputes only when the row is missing entirely, and
        serves an existing row however old it is.

        Args:
            user (User): the student.
        """
        self.stdout.write(f"\nStudent: {user.username} (id {user.id}, xp {user.profile.xp_cached})")
        self.stdout.write(f"Rank:    {user.profile.rank()}")
        self.stdout.write(f"Course:  {'registered this semester' if user.profile.has_current_course else 'NOT registered in a current course'}")

        cached = self.cached_met_ids(user)
        if cached is None:
            self.stdout.write("\nPrerequisite cache: none stored, so the tab computes one on demand. Not stale.")
            return

        live = self.live_met_ids(user)
        missing = live - cached  # met now, but the cache still says locked
        extra = cached - live  # the cache still says met, but they no longer qualify
        if not missing and not extra:
            self.stdout.write(f"\nPrerequisite cache: up to date ({len(cached)} quests).")
            return

        self.stdout.write(self.style.WARNING(f"\nPrerequisite cache: STALE ({len(cached)} quests stored)"))
        if missing:
            self.stdout.write(self.style.WARNING(
                f"  {len(missing)} quest(s) they now qualify for are missing from it: {sorted(missing)}"
            ))
        if extra:
            self.stdout.write(self.style.WARNING(
                f"  {len(extra)} quest(s) they no longer qualify for are still in it: {sorted(extra)}"
            ))
        self.stdout.write(
            "  A stale cache is never repaired on its own. Either celery is not running its\n"
            "  queue, or nothing happened that would have asked for a rebuild. Re-run with\n"
            "  --rebuild to recompute it here and now."
        )

    # The report ##########################################################

    def stages(self, user):
        """The Available tab's filters, in the order get_available() applies them.

        Returns:
            list[tuple[str, QuestQuerySet]]: each filter's name and the quests still standing
            after it, so a quest's disappearance can be attributed to the first one that
            dropped it.
        """
        active = Quest.objects.get_active().select_related('campaign')
        conditions_met = active.get_conditions_met(user)
        repeats = conditions_met.not_in_progress_completed_or_cooldown(user)
        blocking = repeats.block_if_needed(user=user)
        return [
            ("published, in date, campaign published", active),
            ("prerequisites met (from the cache)", conditions_met),
            ("not in progress, completed or in cooldown", repeats),
            ("not crowded out by a blocking quest", blocking),
            ("not hidden by the student", blocking.exclude_hidden(user)),
        ]

    def why_unlisted(self, user, quest, stages=None):
        """Name the first Available-tab filter that drops this quest.

        Args:
            user (User): the student.
            quest (Quest): the quest to account for.
            stages (list): the output of stages(), to reuse across many quests.

        Returns:
            str or None: the filter that dropped it, or None when the quest is in the tab.
        """
        for name, queryset in (stages or self.stages(user)):
            if not queryset.filter(pk=quest.pk).exists():
                return name
        return None

    def report_one_quest(self, user, quest):
        """Print the full account of one quest: the tab's filters, and the prerequisites behind them.

        Args:
            user (User): the student.
            quest (Quest): the quest to explain.
        """
        self.stdout.write(f"\nQuest:   {quest.name} (id {quest.id})")
        self.stdout.write(f"Campaign: {quest.campaign or 'none'}")

        self.stdout.write("\nAvailable tab, filter by filter:")
        dropped_by = None
        for name, queryset in self.stages(user):
            if dropped_by:
                # The filters are cumulative, so everything after the one that dropped the quest
                # would report it missing too, and reading that as "the student hid it" would be
                # wrong. Only the first one accounts for anything.
                self.stdout.write(f"  [--]      {name} (not reached)")
            elif queryset.filter(pk=quest.pk).exists():
                self.stdout.write(f"  [ok]      {name}")
            else:
                self.stdout.write(self.style.WARNING(f"  [DROPPED] {name}"))
                dropped_by = name

        self.stdout.write("\nPrerequisites, worked out live:")
        prereqs = quest.prereqs()
        if not prereqs:
            self.stdout.write("  none")
        for prereq in prereqs:
            met = prereq.condition_met(user)
            self.stdout.write(f"  [{'met' if met else 'NOT MET'}] {prereq}")
        # The stages above read the cache, and reading it stores a fresh one when the student has
        # none, so there is always a stored answer to hold the live one against by this point.
        cached = self.cached_met_ids(user) or set()
        live_met = Prereq.objects.all_conditions_met(quest, user)
        in_cache = quest.pk in cached
        style = self.style.WARNING if in_cache != live_met else (lambda text: text)
        self.stdout.write(f"  live answer:   {'met' if live_met else 'not met'}")
        self.stdout.write(style(f"  cached answer: {'met' if in_cache else 'not met'}"))

        self.stdout.write("\nStarting it from the map or its own URL:")
        self.stdout.write(f"  Quest.is_available(): {quest.is_available(user)}")
        in_progress = QuestSubmission.objects.all_not_completed(user=user).filter(quest=quest).exists()
        self.stdout.write(f"  already in progress:  {in_progress}")

        self.stdout.write("")
        if dropped_by is None:
            self.stdout.write(self.style.SUCCESS("VERDICT: this quest is in the student's Available tab."))
        else:
            self.stdout.write(self.style.WARNING(f"VERDICT: dropped from the tab by: {dropped_by}"))
            self.stdout.write(self.explain(dropped_by, user))

    def explain(self, stage, user):
        """What to do about the filter that dropped a quest.

        Args:
            stage (str): the filter's name, as stages() gives it.
            user (User): the student, for the filters whose answer depends on them.

        Returns:
            str: a sentence or two naming the cause and the fix.
        """
        if stage == "prerequisites met (from the cache)":
            return (
                "  The tab reads the cache, not a live calculation. If the live answer above is\n"
                "  'met' while the cached one is 'not met', the cache is stale: re-run with\n"
                "  --rebuild, and check that celery is running, since nothing else repairs it."
            )
        if stage == "not crowded out by a blocking quest":
            in_progress_ids = set(
                QuestSubmission.objects.all_not_completed(user=user)
                .filter(quest__blocking=True).values_list('quest_id', flat=True)
            )
            open_to_them = [
                f'"{quest.name}" (id {quest.id}{", in progress" if quest.id in in_progress_ids else ""})'
                for quest in Quest.objects.get_blocking_quests(user)
            ]
            names = ", ".join(open_to_them) or "one of them"
            return (
                f"  A blocking quest is open to this student: {names}. While one is, the tab\n"
                "  shows only blocking quests and hides every other quest the student could\n"
                "  otherwise do. Starting one is refused for the same reason, so this quest is\n"
                "  out of their reach until the blocking quest is finished."
            )
        if stage == "not hidden by the student":
            return (
                "  The student hid this quest themselves (the Hide button on the quest). It stays\n"
                "  startable by URL. They can put it back from the Available tab's hidden list."
            )
        if stage == "not in progress, completed or in cooldown":
            return (
                "  Either they have it in progress, or they have used up its repeats, or its\n"
                "  cooldown since the last completion has not elapsed."
            )
        return (
            "  The quest is not published, is outside its available/expiry dates, or its campaign\n"
            "  is unpublished. None of those depend on the student."
        )

    def report_startable_but_unlisted(self, user):
        """List every quest the student can start but cannot see, with the reason for each.

        This is the shape the problem is usually reported in: a quest opens from the quest map
        and is nowhere in the tab.

        Args:
            user (User): the student.
        """
        stages = self.stages(user)
        listed = set(stages[-1][1].values_list('pk', flat=True))
        startable = [
            quest for quest in Quest.objects.get_active().select_related('campaign')
            if quest.pk not in listed and quest.is_available(user)
        ]

        self.stdout.write(f"\nIn the Available tab: {len(listed)} quest(s).")
        if not startable:
            self.stdout.write(self.style.SUCCESS("Nothing is startable but missing from the tab."))
            return

        self.stdout.write(self.style.WARNING(
            f"\nStartable but MISSING from the tab: {len(startable)} quest(s)"
        ))
        for quest in startable:
            reason = self.why_unlisted(user, quest, stages) or "unknown"
            self.stdout.write(f"  {quest.id:>6}  {quest.name[:48]:<50} dropped by: {reason}")
        self.stdout.write("\nRun again with --quest <id> for the full account of any one of them.")
