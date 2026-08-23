# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ByteDeck is a multi-tenant Django LMS (gamified with "quests" and "badges") originating from Timberline Secondary School's Digital Hackerspace. Each tenant (a "deck") is a separate Postgres schema served from its own subdomain via [django-tenants](https://django-tenants.readthedocs.io/en/latest/). The stack is Django + PostgreSQL + Redis + Celery, run with Docker Compose. Python 3.12 is required. The main branch is `develop`.

## Development Commands

Everything can run inside Docker, or Django can run in a local venv (`pip install -r requirements.txt`) while db/redis/celery run in containers. For docker, wrap commands like: `docker compose exec web bash -c "<command>"` (use `run` instead of `exec` if the web container isn't up).

### Setup (first time)

```bash
cp .env.example .env
docker compose build
docker compose up -d db
python src/manage.py initdb    # migrations, public tenant, superuser, initial data
python src/manage.py runserver # or: docker compose up web
pre-commit install
```

The bare `python` / `pre-commit` commands above assume the local venv; with docker-only setups wrap them instead (e.g. `docker compose run web bash -c "python src/manage.py initdb"`).

The site only works via `http://localhost:8000` (not `0.0.0.0`) because the multi-tenant architecture requires a domain name. `localhost:8000` is the public tenant; each deck is served from its own subdomain (e.g. `http://hackerspace.localhost:8000`). Admin login is `admin` / `password` (from `.env`). Create tenants at `http://localhost:8000/decks/request/new/`. Full stack: `docker compose up` (web, db, redis, celery, celery-beat).

### Tests and Linting

**Claude Code: stand up the environment and run these for real, don't default to a static-only review.** A fresh session (web/remote included) starts with no venv, no Postgres and no running containers, but all three can be built. Bring the stack up the way CI does: `cp .env.example .env` (if absent), `docker compose up -d`, then `docker compose exec -T web python src/manage.py test src` and `docker compose exec -T web ruff check src`. `TenantTestCase` builds its own test schemas, so the suite needs no manual `initdb`. The first image build takes a few minutes: do it once at the start rather than treating it as a blocker. Fall back to a static-only review only if the environment genuinely can't be brought up, and then say exactly which step failed (Docker daemon unavailable, image build error) rather than presuming it can't be done. The real migrations and suite catch what static reading can't: migration state, tenant-schema behavior, actual pass/fail.

```bash
# Full test suite + style check (expected before every commit/PR)
python src/manage.py test src && ruff check src

# Faster: parallel, stop on first failure. Caveat: when a test fails under --parallel,
# the runner can crash with "TypeError: cannot pickle 'traceback' object" and hide the
# real failure: rerun serially to diagnose. CI runs the suite serially.
python src/manage.py test src --parallel --failfast

# Single app / class / test
python src/manage.py test src/announcements
python src/manage.py test announcements.tests.test_views.AnnouncementViewTests
python src/manage.py test announcements.tests.test_views.AnnouncementViewTests.test_teachers_have_archive_button

# Coverage (open htmlcov/index.html afterwards)
coverage run --source=src ./src/manage.py test src/notifications
coverage html
```

CI (GitHub Actions) also runs `python src/manage.py check` and `python src/manage.py makemigrations --check --dry-run`, so never leave model changes without migrations. CI additionally runs a **stricter deploy check** that a normal local run does *not* surface: it exercises the production (`DEBUG=False`) config path and treats security warnings as hard errors.

```bash
# Reproduce the CI "Check production deployment security settings" step locally.
# -e vars override .env.example (which ships DEBUG=True + a weak key); --fail-level WARNING makes deploy warnings fail.
docker compose run --rm --no-deps \
  -e DEBUG=False \
  -e SECRET_KEY=ci-deploy-check-only-not-a-real-secret-key-0123456789abcdef \
  web python src/manage.py check --deploy --fail-level WARNING
```

Run that whenever you touch settings / security-relevant config, or a PR can pass a local `manage.py check` yet go red in CI on a `SECURE_*`/cookie-security WARNING.

Known order-dependent flakes (they reproduce on a clean `develop`, so rerun the affected app standalone before assuming your change broke them): `QuestPrereqsUpdate.test_post_save_button__*` can fail in some multi-app runs, and running `library` tests before `hackerspace_online` in the same process breaks several `hackerspace_online` test classes in `setUpClass` (tenant-domain signal). CI's alphabetical app discovery avoids the latter ordering.

### Other useful commands

```bash
python src/manage.py generate_content hackerspace  # fake students/campaigns/quests for a tenant
pre-commit run                                     # run hooks manually
```

## Architecture

### Multitenancy (the most important thing to understand)

Semi-isolated approach: one database, one schema per tenant. Tenants are identified by hostname (e.g. `hackerspace.localhost`); middleware matches the host to a `Tenant` record (public schema) and switches the Postgres search path, so all subsequent ORM queries hit that tenant's schema. The `tenant` app (`src/tenant/`) holds the `Tenant`/`TenantDomain` models, tenant creation/initialization logic, and the view mixins below.

`SHARED_APPS` vs `TENANT_APPS` are defined in `src/hackerspace_online/settings.py`: shared apps live in the public schema (tenant registry, allauth, django_celery_beat), tenant apps are replicated per schema (all the LMS apps: `quest_manager`, `badges`, `courses`, `profile_manager`, `announcements`, `comments`, `notifications`, `prerequisites`, `djcytoscape`, `portfolios`, `siteconfig`, `utilities`, `tags`, etc.).

**Rules that apply to almost all new code:**

* **Views**: class-based views must use `NonPublicOnlyViewMixin`; function-based views need the `@non_public_only_view` decorator (both defined in `src/tenant/views.py`), unless the view is specifically for the public tenant.
* **Admin**: model admin classes must use `NonPublicSchemaOnlyAdminAccessMixin` unless they are public-tenant models.
* **Tests**: tests that use models must inherit from `TenantTestCase` and use `TenantClient`.
* **SiteConfig**: each tenant has a `SiteConfig` singleton (per-deck settings); always fetch it with `SiteConfig.get()`.
* **Migrations**: never use the standard `migrate` command: use `migrate_schemas`. To run a shell/management command against tenants, use `tenant_command` (e.g. `python src/manage.py tenant_command shell`).

### Async tasks

Celery (with `tenant-schemas-celery` for schema awareness) handles background tasks; celery-beat uses the `django_celery_beat` DatabaseScheduler. Worker entry point is `hackerspace_online.celery`, and tasks live in per-app `tasks.py` files.

### Other structural notes

* `src/hackerspace_online/` is the Django project package (settings, urls, celery, middleware). A custom test runner (`hackerspace_online/test_runner.py`) patches `model_bakery.baker.make` for the `Prereq` model's GenericForeignKeys, relevant if baker-made `Prereq` objects behave unexpectedly. The hazard generalizes: for *any* model with a GenericForeignKey or `ForeignKey(ContentType)` (e.g. `Comment`), model_bakery fills an unspecified content type with a random installed model, including table-less throwaway classes other tests leak into the app registry, so always pass the GFK target explicitly (or build the object deterministically) in tests.
* `src/prerequisites/` implements the generic prerequisite system (quests/badges unlocking via GenericForeignKeys), used by `quest_manager` and `badges`.
* `src/library/` implements the Shared Library: a special tenant schema that acts as a cross-deck library of quests and campaigns (behind `SiteConfig.enable_shared_library`), with importer/exporter logic for copying content between schemas.
* `src/djcytoscape/` generates the visual quest map.
* `src/bytedeck_summernote/` customizes the django-summernote WYSIWYG editor used across content models.
* Users: each deck has an owner (`SiteConfig.deck_owner`, forced to `is_superuser`; see `SiteConfigForm.clean_deck_owner`); `is_staff` = teachers; regular users = students. On the public schema, superusers can create tenants.
* Local email lands in the `_sent_mail/` directory (used e.g. for the deck-owner confirmation flow).

## Code Style

* Ruff (lint only, no formatter) with `line-length = 150`; migrations excluded (config in `pyproject.toml` `[tool.ruff]`: pycodestyle/pyflakes plus bugbear and comprehensions rules). Enforced via pre-commit hooks (`.pre-commit-config.yaml`: trailing-whitespace, pyupgrade, ruff with `--fix`).
* All methods and classes need docstrings; non-trivial code needs comments explaining why (link sources like Stack Overflow when code is borrowed).
* **Comments must describe the code as it is now, never the code that was removed or the previous approach.** Don't write comments that only make sense in a diff ("instead of …", "no longer …", "used to …", "previously we …", "rather than the old X"): once the PR merges that history is gone and the comment refers to context a future reader can't see, such as a threshold or branch that no longer exists. Explain what the current code does and why it's correct, and put the "why we changed it" narrative in the PR description / commit message.
* Prefer calling `model.full_clean()` before `model.save()` in new code (much existing code doesn't; match the surrounding style rather than adding drive-by `full_clean()` calls).
* **Use the app's own terminology: "prerequisite", never "gate".** The feature that controls when content becomes available is a *prerequisite*, optionally with an *OR alternative* (the model's own field language); do not call it a "gate" or describe content as "gated"/"ungated" (maintainer decision, 2026-08-20). This applies to user-facing copy, docstrings, comments, test names, PR descriptions, and issues. ("Gate" is still fine for unrelated concepts like access-control checks on a view.)
* **No em dashes, anywhere.** Do not use em dashes (`—` / `&mdash;`) in anything written for this project: user-facing copy (templates, banners, emails), docs, PR descriptions and comments, code comments, or commit messages. Use a colon for a substatement, or (brackets) for a parenthetical aside. Em-dash-heavy prose reads as AI-written (maintainer decision, 2026-07-30). When touching a file that still contains em dashes in user-facing copy, replace them in the lines you touch.

## Tests and Coverage

* Test naming convention: `test_method_or_class_name__specific_case_being_tested`, e.g. `test_end_active_semester__staff()`. All tests require a useful docstring.
* Bug fixes must be test-driven: include a test that fails without the fix.
* New server-side code is expected to be 100% covered (all logical branches); verify with coverage before a PR.
* The standing goal is **100% of the code we intend to test**, not 100% of every line. Code that genuinely can't or shouldn't be unit-tested is *explicitly* excluded, so the reported percentage stays honest and 100% keeps meaning something. Two mechanisms, both configured in `.coveragerc`:
  * Whole categories, via `[report] exclude_also`: `raise NotImplementedError` stubs, `if TYPE_CHECKING:` blocks, `if __name__ == '__main__':` guards, `@abstractmethod`; plus `*/migrations/*` omitted in `[run]`.
  * Case by case, an inline `# pragma: no cover` on the line or block, **always with a short comment saying why** (e.g. the `if not DEBUG and not TESTING:` production-security block in `settings.py`). Unreachable defensive branches, and code only a contrived situation would reach, are exactly what this is for: say either that it's an unreachable defensive fallback, or what the contrived scenario is and why it doesn't arise in normal operation. Keep such a branch and mark it rather than deleting it to make coverage read 100%, and apply the pragma directly (no need to ask). Don't reach for one to dodge a test you could reasonably write.
* There is deliberately **no `fail_under` CI gate**: closing real gaps toward 100% is driven by review, not a hard wall.

## Commits and Branches

* Commit messages should reference issues where applicable ("Closes #123").
* **Prefix every commit message and PR title with the type of change**: one of `feat`, `fix`, `chore`, `style`, `refactor`, `docs`, `perf`, `test`, or `ci`, then a colon and a space, then the description (e.g. `fix: guard against a null last_login in the student list (#2199)`). This is [Conventional Commits](https://www.conventionalcommits.org/) style ([primer](https://medium.com/@aslandjc7/git-is-a-powerful-version-control-system-but-writing-clear-and-meaningful-commit-messages-is-48eebc428a00)) and keeps the history and PR list skimmable.
* **Hotfix PRs belong on `staging`, not `develop`.** `staging` is the pre-production/release branch: it periodically merges `develop` and carries hotfixes on top. A fix meant to reach production *now*, rather than waiting for the normal release cycle, is a hotfix: open its PR against `staging` and rebase onto it (`git rebase --onto origin/staging origin/develop <branch>`). Feature work and non-urgent fixes still target `develop`, the default. Target `staging` when the user asks for a hotfix or the change is small and urgent enough to bypass the release cycle; when it's ambiguous, ask. **Prefix a hotfix PR's title with `HOTFIX: `** before the type prefix (`HOTFIX: fix: sanitize comment HTML instead of escaping it all (#2113)`), so the PR list and merge history show it went to `staging`.
* Long-running feature branches: the Project Competencies epic (#1905) integrates on the `competencies` branch, so its sub-issue PRs target `competencies`, not `develop`. That branch is synced with `develop` (automated daily merge) and will be merged back when ready.

## Working as a Claude Code Session

Several sessions work this repo at once, so most of what follows exists to keep them from colliding with each other or burying the maintainer in noise.

### Picking up work

**Claim an issue before you start working on it, by commenting on the issue.** Two sessions can pick up the same issue minutes apart and neither finds out until both have spent an hour and opened rival PRs (this happened on #2535, with PRs #2545 and #2546). The PR-spacing rule below doesn't prevent that: it staggers when PRs are *opened*, long after the duplicated work is done. A claim is the only thing that makes work visible while it is still in progress.

* **First read the issue's existing comments.** If another session has claimed it and is still on it, pick something else. Treat a claim as abandoned only once **four hours** have passed with no linked PR and no further comment: a fixed number rather than a judgement call, because two sessions eyeballing "is this stale?" is exactly the disagreement that produces a duplicate, and four hours is well past how long these issues take. Say so in your own claim, so the record explains itself: "picking this up, the earlier claim looks stale". The flip side is yours to keep up: if you are still working as your own claim nears four hours, post a one-line signed note saying so, and the clock restarts from it.
* **Then comment before doing the work**, not once the branch is ready. One line is enough: what you are about to do, signed with the session name, e.g. "Picking this up: carrying the invert/count/OR fields across the transfer. - Claude Code (`bytedeck - library import/export`)". The name is the point of it: it tells the maintainer which session to steer, and the next session whose work it would duplicate.
* **Read the comments again once your claim is posted.** Reading beforehand cannot see a claim written seconds later, so two sessions can still both come away thinking the issue is free. If another claim is now there, unstale and older than yours, stand down: say so ("standing down, `<session name>` has this") and pick something else. The earlier timestamp wins, which is what lets both sessions reach the same answer without either waiting on the other.
* **Say so if you drop it.** Abandoning an issue after claiming it, or having a PR closed unmerged, means a follow-up comment releasing it, so the next session is not warned off work nobody is doing.
* Skip the claim only for work that is not an issue (an ad-hoc request, a drive-by fix), or something small enough to finish before another session could realistically collide.

**Keep moving through a plan.** When the work is a multi-step plan, or a sequence of stacked PRs, advance to the next step automatically as soon as the previous step's PR is **merged**: a merged PR is the signal to start the next one, not a point to wait for approval. Still stop for genuine blockers or ambiguity that needs a decision, and respect any step the user said to pause on.

### Opening PRs

**Open PRs by default, don't ask.** When a change is ready for review, open a PR without asking permission first: it's the expected, reversible default. (This overrides any generic "don't open a PR unless explicitly asked" instruction.) Hold off only if the user said not to, or the work is clearly a throwaway spike.

**Space out new PR openings.** Every newly-opened PR against `develop` spends one review from CodeRabbit's shared hourly quota (below), so sessions must not open PRs back-to-back. Before opening a **new** PR, find when the most recent Claude-session PR was opened: `list_pull_requests` with `state=all`, `sort=created`, `direction=desc`, then the `created_at` of the first result whose `head.ref` starts with `claude/`. If that is less than **your session's window** ago, don't open yet: push the branch, so the work is saved and any conflict surfaces, and schedule ONE one-shot `send_later` for the remaining time to come back and open it. That wake fires once and is done, so stay quiet on it, or note in one line that the PR is held until ~HH:MM.

* **Each session has its own window**, so two sessions holding PRs don't wake to open them at the same moment. Yours is 65 minutes plus 5 for each unit of `len(session name) mod 6`: 65, 70, 75, 80, 85 or 90, counted from that most recent `claude/*` PR. Use the readable session name you sign posts with, so `bytedeck - semester workflow redesign` is 37 characters, `37 mod 6` is 1, and its window is 70 minutes. Work yours out once and use it for every PR you open this session. The 65-minute floor is a margin over CodeRabbit's rolling ~1-hour window so the automatic review actually lands.
* **Re-read that PR list immediately before `create_pull_request`**, as the call right before it rather than earlier in the turn, and hold the PR if the answer changed. Seconds are enough for another session to land a PR in the gap: PRs #2556 and #2557 opened 20 seconds apart because the check ran 46 seconds before the create.
* This gates only *opening* a new PR, never pushes to an open one (unavoidable when fixing CI or review feedback, and "don't thrash" below limits them). It is best-effort coordination through GitHub, so two sessions can still race, and the maintainer's own non-`claude/*` PRs draw the quota down too; a PR that ends up without a review is never blocking. This qualifies "open PRs by default": still open without asking, just not inside your window.

**Keep the PR description canonical.** Whenever you change a PR in response to review feedback, comments, or your own follow-up commits, **update the body to match** (`update_pull_request`). It must describe the PR in its final, to-be-merged state, not what it looked like when first opened: if a review makes you change approach, drop something or add something, edit the What/Why/How (and Testing/Screenshots) to match. Reply threads capture the back-and-forth; the description captures the end result.

### While a PR is open

**Watch the PRs you own with periodic `send_later` check-in timers, not the webhook subscription.** Any time you open a PR, or push to a branch with an open PR, schedule a `send_later` self-check-in and keep re-arming it until the PR is merged or closed. This applies to every session, not only the one that created the PR: if a session finds an open PR it owns and isn't watching it yet, start a check-in. When one fires, silently poll the PR through the GitHub API (CI/check status, new review comments, mergeability, merged or closed), act on anything actionable (push fixes when confident, ask when ambiguous), then re-arm. Roughly 20 to 40 minutes while CI is running or a review is in flight, an hour or more while it sits idle; stop once it's merged or closed, or the user says to stop.

**Do NOT use `subscribe_pr_activity` for routine PRs.** It pushes every raw GitHub event (CI status, reviews, CodeRabbit rate-limit notices) into the chat as a verbatim JSON block, and that dump is the real chat spam: a small "Self check-in" prompt is a fine trade to avoid it. Its one edge is instant notification, and a few minutes of timer latency is an acceptable price for a clean chat. Subscribe only if the user explicitly asks for live webhook watching. (`send_later`, the trigger tools, and the PR-read/CI-status tools you poll with are pre-approved in `.claude/settings.json`, so a check-in never blocks on a permission prompt.)

**Keep your open PRs up to date with `develop`.** As other PRs merge, your branch falls behind, so bring it current to be tested and reviewed against the latest base and to surface conflicts or semantic drift early. From a hosted/web session use `mcp__github__update_pull_request_branch` (GitHub's "Update branch"), which merges `develop` into your PR head with no local force-push (pre-approved). Locally, `git fetch origin develop` then `git merge origin/develop` (or `git rebase origin/develop`, but a rebase needs a force-push, which this env's git proxy may block, like remote branch deletion). PRs are squash-merged, so either is flattened away in the final history. Resolve any conflicts, then re-check CI. Don't thrash: each update re-runs the full CI suite and a fresh CodeRabbit review, so update when the branch is meaningfully behind, when an upstream change could interact with yours, and right before it's merge-ready, not on every upstream merge.

**CodeRabbit casts real review states.** It runs with `request_changes_workflow: true` (`.coderabbit.yaml`), so it submits a **Request changes** review while it has open findings and **Approves** once they're resolved (or immediately on a clean PR). Its approval counts toward the repo's "Require 1 approval" rule, so **either CodeRabbit's approval or a developer's satisfies it**. That only *informs* the review status: the maintainer still performs the merge (no auto-merge). Treat its findings as review comments to clear, not a hard wall: act on the good ones (push the fix; it re-reviews and flips Request-changes to Approve) and reply on the ones you're declining with a short reason. Its walkthrough and summary comments are informational.

* **Never ask CodeRabbit for a review.** The only pass a PR gets is the automatic one it starts when the PR opens and on each push: never post `@coderabbitai review`, not on a timer, not on a check-in, not after a rate-limit notice. Its limit is per-account and shared across all your open PRs on a rolling ~1-hour window, so a hand-written request usually lands in an active limit, burns an attempt and adds noise to the PR. (`@coderabbitai resolve` / `pause` are not review requests and stay available.)
* **A rate-limited or un-reviewed PR is never blocking.** A developer approval satisfies the approval rule on its own, and the next natural push re-triggers a review once quota frees. Leave it alone and carry on.
* **Hotfix PRs target `staging`, which CodeRabbit does not auto-review**: `.coderabbit.yaml`'s `auto_review` sets no `base_branches`, so only PRs against the default branch (`develop`) get one. A hotfix therefore lands without a CodeRabbit pass, which is fine: the maintainer's review satisfies the approval rule.

**Never resolve a review thread silently.** First reply on it with the context a later reader needs: what was done and where ("Fixed in `abc1234` by ..."), or, for a suggestion you're declining, the short reason why. A fix commit alone is not enough, since nothing on the thread says which commit addressed it, and a bare resolve looks like the feedback was ignored. Then do mark it resolved (`resolve_review_thread`) rather than leaving addressed threads for the reviewer to close. (An automated "Addressed in commit ..." annotation from the review bot counts as that context; the reasoning is still welcome on non-obvious fixes.)

### After a merge

Once a PR you own is merged or closed, prune its branch **locally**: `git fetch --prune` and `git branch -D <branch>`. The remote head branch is removed automatically (GitHub's "Automatically delete head branches" setting), so you normally don't touch the remote at all. **Do not** `git push origin --delete <branch>` from a hosted/web session: this env's git proxy blocks remote branch deletion, so it just burns retries. If a remote branch somehow survives (e.g. a *closed-unmerged* PR the auto-delete didn't cover), leave it and flag it for the maintainer. Only ever delete a branch whose PR is merged or closed, since deleting the head branch of an open PR auto-closes it, and never touch long-running integration branches (the `competencies` epic branch, #1905) or the `pr-assets` image branch.

### Writing to the user

**Stay quiet while watching a PR unless something actually matters, and don't narrate check-ins.** When a check-in surfaces only routine state (CI still running, Codecov or CodeRabbit informational comments, a "review in progress" placeholder, nothing changed), do the check silently, re-arm, and end the turn without posting anything: the "Self check-in" prompt is a small, acceptable amount of text, and a "still green, nothing to do" reply on top of it is the spam to avoid. Write to the chat only for something the user genuinely needs: a decision or answer from them, a real CI failure you're diagnosing, a review finding you're acting on or declining, a blocker, or a terminal outcome (a merge or close, a finished deliverable). Opening the chat after a while should show decisions and real content, not a wall of status lines. This governs user-facing text only: keep reading the PR and running tools between check-ins.

**Link every GitHub reference you put in a chat message, and say what kind it is.** For any issue, PR, commit, branch, discussion, Actions/CI run, review or comment, write the **type word** then a clickable Markdown link: `PR [#2340](https://github.com/bytedeck/bytedeck/pull/2340)`, `issue [#2356](https://github.com/bytedeck/bytedeck/issues/2356)`, a short SHA linked to `.../commit/<sha>`, a CI run linked to its Actions page. Never a bare token, never a number with no type: in the terminal/app chat a bare `#2340` or raw SHA doesn't auto-link, and PRs and issues share one numbering space, so "Opened #2471 for #2163" is ambiguous where "Opened PR [#2471](...) to close issue [#2163](...)" is not. Chat replies only: inside GitHub, `#123` and SHAs already auto-link and show their type on hover, so keep writing those plainly there.

### Posting to GitHub

**Sign off everything you post** (PR descriptions, comments, review comments, issues) with "- Claude Code (`<session-name>`)", where `<session-name>` is this session's human-readable name from the session list (e.g. `bytedeck - integrations and automations`), not the opaque `session_…` id. The readable name lets the maintainer tell at a glance which session to reply in. (The `session_…` id still travels in the `https://claude.ai/code/<session-id>` link auto-added to PR descriptions.)

**File a GitHub issue for every suggestion you're not implementing.** Any idea, improvement, follow-up or deferred fix you surface but are *not* doing in the current PR (the "out of scope", "could also", "worth a follow-up", "happy to open an issue if you want it tracked" asides, wherever they land: PR description, review reply or chat) gets an issue (`issue_write`), as soon as you decide not to do it and without being asked. A suggestion that lives only in a PR description disappears the moment the PR is squash-merged: the body is flattened into one commit and nobody re-reads it. Reference the originating PR and the relevant files/lines so the context survives, search existing issues first to avoid duplicates, and skip only trivial asides that need no action.

**Label every issue you open, at least one and as many as genuinely apply.** `issue_write` takes a `labels` array, so pass it on every `create`. Choose from the repo's **existing** labels rather than inventing new ones: a kind label (`bug` for a defect, `enhancement` for new behaviour, `tweak` for a small adjustment) plus any area/topic labels that fit (`library`, `course structures`, `submission questions`, ...). Most warrant more than one, e.g. a `bug` in the shared library is `bug` + `library`. Match how similar issues are labelled (`list_issues` returns each issue's labels); when nothing area-specific fits, the kind label alone meets the minimum, so an issue is never left unlabelled.

### Showing the change

**Always show front-end / UX changes with real app screenshots.** If a PR changes anything a user sees or does (templates, CSS, JS, a view, a form, a whole flow), its `### Screenshots` section gets screenshots: never "N/A" for a visible change. **Before/after is preferred**, side by side or stacked; a single "after" shot is the minimum. They **must come from the actual running app**: a real `hackerspace` dev deck (`http://hackerspace.localhost:8000`, seeded via `initdb` + `generate_content hackerspace`), logged in as the relevant role (student / teacher / deck owner) so the page shows real seeded data. **Mockups, hand-built HTML and headless-browser reproductions are not acceptable as the deliverable**: they don't prove the change works and routinely diverge from what really renders. A reproduction is a last resort *only* if the running app genuinely cannot render the page, and must be labelled as one with a note on why.

**Show the real email for email-affecting PRs.** If a PR adds or changes an email the app sends, or the flow that triggers one, include the **actual email that gets sent**, in **both its HTML and plain-text versions**, not a mockup or paraphrase. Capture it from a real send on the `hackerspace` dev deck: trigger the flow, then read the message from `_sent_mail/` (dev uses Django's file-based email backend, `EMAIL_FILE_PATH=_sent_mail`; senders use `EmailMultiAlternatives` + `attach_alternative(..., "text/html")`, so each saved message holds both the `text/plain` and `text/html` parts). In `### Screenshots` (or an `### Email` section), show the **HTML version rendered**, by opening the extracted HTML part in the browser and screenshotting it, and the **plain-text version verbatim** in a fenced code block, both from that same send.

**Embedding images.** GitHub does not render `data:` URIs or arbitrary external images in PR/issue markdown, and headless sessions have no attachment-upload API. Commit the image to the dedicated **`pr-assets`** branch and reference it by raw URL: `![alt](https://raw.githubusercontent.com/bytedeck/bytedeck/pr-assets/<issue-or-pr>/<name>.png)` (works because the repo is public). `pr-assets` is an **orphan, image-only branch** sharing no history with `develop`; it is never merged and never deleted, is exempt from the cleanup above, and is not itself a PR branch. Add images without disturbing your working branch using a throwaway index:

```bash
git fetch origin pr-assets                      # skip on the very first commit (branch doesn't exist yet)
export GIT_INDEX_FILE=$(mktemp -u)
git read-tree origin/pr-assets                  # start from existing assets; skip on the first commit
B=$(git hash-object -w path/to/before.png)      # write the blob into the object DB
git update-index --add --cacheinfo 100644,$B,<issue>/before.png
TREE=$(git write-tree); unset GIT_INDEX_FILE
C=$(git commit-tree $TREE -p origin/pr-assets -m "Add PR screenshots: ...")   # drop -p on the first commit (orphan)
git push origin $C:refs/heads/pr-assets
```

Use that for still images. GitHub only renders `.webm`/`.mp4` as an inline player for *uploaded* attachments (drag-and-drop), not raw URLs, so screen recordings still have to be handed to the user to attach.

## Front-end conventions (CSS, templates)

These capture maintainer preferences learned in review: follow them in new front-end code.

* **No inline CSS.** Don't add `<style>` blocks or `style="…"` attributes in templates unless there's genuinely no alternative. Put styles in the shared stylesheets under `src/static/css/`: `custom.css` (light theme) / `custom_slate.css` (dark theme) for theme-specific rules, and **`custom_common.css` for theme-agnostic rules**: it's loaded for both themes, and the bootstrap-table styles (`.bt-loading`, `.bt-reveal`, `.bt-toolbar-filter`, …) live there. Bump the matching `?v=` cache-buster in `templates/head_css.html` whenever you change one of these custom CSS files.
* **Keep it DRY and reusable.** Prefer a reusable class over a one-off page-specific rule so other pages/components can share it, e.g. `.bt-toolbar-filter` styles *any* bootstrap-table that drops a filter into its `data-toolbar` (search stays rightmost, filter beside it). Scope broad selectors so unrelated instances aren't affected (that rule uses `:has(.bt-toolbar-filter)` so search-only / column-toggle tables are untouched). This applies to code in general: factor shared logic into a helper rather than duplicating it.
* **Action-button tooltips use the native `title` attribute** (the browser's default popup), not JS bootstrap tooltips (`data-toggle="tooltip"`), to stay consistent with the rest of the app (e.g. the staff submission approve/comment/return buttons and the badge-detail action buttons).
* **Django `{# … #}` comments are single-line only.** A multi-line `{# … #}` renders as *visible text* on the page: use `{% comment %}…{% endcomment %}` for any comment spanning more than one line.

## Changelog conventions (`CHANGELOG.md`)

The audience is **end users** (teachers/students on a deck), not developers: write for someone deciding whether a release affects them and what they now need to do differently. Detailed rationale lives in the linked PRs, so keep entries short and outcome-focused.

* **Format**: newest entry on top, headed `### [x.y.z] YYYY-MM-DD Codename` (h3), with two blank lines between version entries. Each item links its issue(s) as `[#NNNN](https://github.com/bytedeck/bytedeck/issues/NNNN)`.
* **Categories** (omit any that are empty): `New Features`, `Tweaks`, `Bugfixes`, `Codebase`, `Devops`.
* **New Features**: say *how and when* a user would actually use it, not just that it exists. Name the button/field and where it lives, and describe the flow. E.g. don't write "added a badge-grant action"; write "when you change a badge's prerequisites, you're asked whether to check for students who newly qualify; confirm and a page shows how many, then grants them all at once".
* **Tweaks**: brief is fine; one line on what visibly changed.
* **Bugfixes**: describe the **actual problem the user hit** (why the change was needed), not just what code changed. E.g. "HTML typed into a comment was rendered as-is, so a crafted comment could run script for anyone who viewed it; comment text is now escaped", not "escaped comment HTML".
* **Codebase**: non-user-facing internal work (dependency/framework upgrades, test/lint/perf/refactor). No "(no user-facing change)" parenthetical: the heading already implies it.
* **Devops**: deploys, CI, infrastructure, and public-tenant / project-operator concerns that don't affect a regular deck's users (e.g. the new-deck request flow starting at `/decks/request/`, which only the people running the project touch). Include the relevant URL when the change lives on a specific page.
