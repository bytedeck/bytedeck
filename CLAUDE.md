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

```bash
# Full test suite + style check (expected before every commit/PR)
python src/manage.py test src && ruff check src

# Faster: parallel, stop on first failure. Caveat: when a test fails under --parallel,
# the runner can crash with "TypeError: cannot pickle 'traceback' object" and hide the
# real failure — rerun serially to diagnose. CI runs the suite serially.
python src/manage.py test src --parallel --failfast

# Single app / class / test
python src/manage.py test src/announcements
python src/manage.py test announcements.tests.test_views.AnnouncementViewTests
python src/manage.py test announcements.tests.test_views.AnnouncementViewTests.test_teachers_have_archive_button

# Coverage (open htmlcov/index.html afterwards)
coverage run --source=src ./src/manage.py test src/notifications
coverage html
```

CI (GitHub Actions) also runs `python src/manage.py check` and `python src/manage.py makemigrations --check --dry-run`, so never leave model changes without migrations.

Known order-dependent flakes (they reproduce on a clean `develop`, so rerun the affected app standalone before assuming your change broke them): `QuestPrereqsUpdate.test_post_save_button__*` can fail in some multi-app runs, and running `library` tests before `hackerspace_online` in the same process breaks several `hackerspace_online` test classes in `setUpClass` (tenant-domain signal). CI's alphabetical app discovery avoids the latter ordering.

### Other useful commands

```bash
python src/manage.py generate_content hackerspace  # fake students/campaigns/quests for a tenant
pre-commit run                                     # run hooks manually
```

## Architecture

### Multitenancy (the most important thing to understand)

Semi-isolated approach: one database, one schema per tenant. Tenants are identified by hostname (e.g. `hackerspace.localhost`); middleware matches the host to a `Tenant` record (public schema) and switches the Postgres search path, so all subsequent ORM queries hit that tenant's schema. The `tenant` app (`src/tenant/`) holds the `Tenant`/`TenantDomain` models, tenant creation/initialization logic, and the view mixins below.

`SHARED_APPS` vs `TENANT_APPS` are defined in `src/hackerspace_online/settings.py` — shared apps live in the public schema (tenant registry, allauth, django_celery_beat), tenant apps are replicated per schema (all the LMS apps: `quest_manager`, `badges`, `courses`, `profile_manager`, `announcements`, `comments`, `notifications`, `prerequisites`, `djcytoscape`, `portfolios`, `siteconfig`, `utilities`, `tags`, etc.).

**Rules that apply to almost all new code:**

* **Views**: class-based views must use `NonPublicOnlyViewMixin`; function-based views need the `@non_public_only_view` decorator (both defined in `src/tenant/views.py`) — unless the view is specifically for the public tenant.
* **Admin**: model admin classes must use `NonPublicSchemaOnlyAdminAccessMixin` unless they are public-tenant models.
* **Tests**: tests that use models must inherit from `TenantTestCase` and use `TenantClient`.
* **SiteConfig**: each tenant has a `SiteConfig` singleton (per-deck settings); always fetch it with `SiteConfig.get()`.
* **Migrations**: never use the standard `migrate` command — use `migrate_schemas`. To run a shell/management command against tenants, use `tenant_command` (e.g. `python src/manage.py tenant_command shell`).

### Async tasks

Celery (with `tenant-schemas-celery` for schema awareness) handles background tasks; celery-beat uses the `django_celery_beat` DatabaseScheduler. Worker entry point is `hackerspace_online.celery`, and tasks live in per-app `tasks.py` files.

### Other structural notes

* `src/hackerspace_online/` is the Django project package (settings, urls, celery, middleware). A custom test runner (`hackerspace_online/test_runner.py`) patches `model_bakery.baker.make` for the `Prereq` model's GenericForeignKeys — relevant if baker-made `Prereq` objects behave unexpectedly in tests. The hazard generalizes: for *any* model with a GenericForeignKey or `ForeignKey(ContentType)` (e.g. `Comment`), model_bakery fills an unspecified content type with a random installed model — including table-less throwaway classes leaked into the app registry by other tests — so always pass the GFK target explicitly (or build the object deterministically) in tests.
* `src/prerequisites/` implements the generic prerequisite system (quests/badges unlocking via GenericForeignKeys), used by `quest_manager` and `badges`.
* `src/library/` implements the Shared Library: a special tenant schema that acts as a cross-deck library of quests and campaigns (gated by `SiteConfig.enable_shared_library`), with importer/exporter logic for copying content between schemas.
* `src/djcytoscape/` generates the visual quest map.
* `src/bytedeck_summernote/` customizes the django-summernote WYSIWYG editor used across content models.
* Users: each deck has an owner (`SiteConfig.deck_owner`, forced to `is_superuser` — see `SiteConfigForm.clean_deck_owner`); `is_staff` = teachers; regular users = students. On the public schema, superusers can create tenants.
* Local email lands in the `_sent_mail/` directory (used e.g. for the deck-owner confirmation flow).

## Code Style & PR Conventions

* Ruff (lint only, no formatter) with `line-length = 150`; migrations excluded (config in `pyproject.toml` `[tool.ruff]`: pycodestyle/pyflakes plus bugbear and comprehensions rules). Enforced via pre-commit hooks (`.pre-commit-config.yaml`: trailing-whitespace, pyupgrade, ruff with `--fix`).
* Test naming convention: `test_method_or_class_name__specific_case_being_tested`, e.g. `test_end_active_semester__staff()`. All tests require a useful docstring.
* Bug fixes must be test-driven: include a test that fails without the fix.
* New server-side code is expected to be 100% covered (all logical branches); verify with coverage before a PR.
* Test coverage: the standing goal is **100% of the code we intend to test** — not 100% of every line. Code that genuinely can't/shouldn't be unit-tested is *explicitly* excluded so the reported percentage stays honest and 100% remains meaningful. Two mechanisms (configured in `.coveragerc`): (1) whole categories excluded via `[report] exclude_also` — `raise NotImplementedError` stubs, `if TYPE_CHECKING:` blocks, `if __name__ == '__main__':` guards, `@abstractmethod`; plus `*/migrations/*` omitted in `[run]`. (2) Case-by-case, an inline `# pragma: no cover` on the specific line/block — **always with a short comment saying why** (e.g. the `if not DEBUG and not TESTING:` production-security block in `settings.py`). Don't reach for a pragma to dodge a test you could reasonably write; use it only for code that legitimately never runs under the test harness. There is deliberately **no `fail_under` CI gate** — closing real gaps toward 100% is driven by review, not a hard wall.
* All methods and classes need docstrings; non-trivial code needs comments explaining why (link sources like Stack Overflow when code is borrowed).
* Prefer calling `model.full_clean()` before `model.save()` in new code (much existing code doesn't — match the surrounding style rather than adding drive-by `full_clean()` calls).
* Commit messages should reference issues where applicable ("Closes #123").
* Long-running feature branches: the Project Competencies epic (#1905) integrates on the `competencies` branch — sub-issue PRs target `competencies`, not `develop`. The feature branch is synced with `develop` (automated daily merge) and will be merged back when ready.
* Claude Code — always watch the PRs you own: any time you open a PR, or push to a branch that has an open PR, immediately subscribe to that PR's activity with `subscribe_pr_activity`, and stay subscribed until the PR is merged or closed. This applies to every Claude session (web, CLI, or otherwise), not only the session that created the PR — if a session finds an open PR it owns and isn't yet watching, it should subscribe. While subscribed, follow up on CI failures and review comments (investigate, push fixes when confident, ask when ambiguous). Because webhook events don't cover everything (CI success, new pushes, merge-conflict transitions), schedule a periodic self check-in (e.g. via `send_later`) to re-check state until the PR is merged or closed. Stop watching only when the PR is merged/closed or the user says to stop (`unsubscribe_pr_activity`). The PR-activity subscribe/unsubscribe tools are pre-approved in `.claude/settings.json` so no session is blocked by a permission prompt.
* Claude Code (web sessions): after pushing a branch with an open PR, subscribe to the PR's activity (`subscribe_pr_activity`) and follow up on CI failures and review comments until the PR is merged or closed.
* Claude Code: after addressing a PR review comment (pushing the fix and/or answering the question in a reply), mark that review thread as resolved (`resolve_review_thread`) so the PR reflects its true state — don't leave addressed threads dangling for the reviewer to close.
* Claude Code: sign off everything you post to GitHub (PR descriptions, comments, review comments, issues) with "- Claude Code (`<session-name>`)", where `<session-name>` is this session's human-readable name as shown in the Claude Code session list (e.g. `bytedeck - integrations and automations`) — not the opaque `session_…` id. The readable name lets the maintainer tell at a glance which session to reply in. (The precise `session_…` id still travels in the `https://claude.ai/code/<session-id>` link auto-added to PR descriptions, for machine reference.)
* Claude Code — clean up after merges: once a PR you own is merged (or closed), delete its branch. The remote usually auto-deletes the head branch on merge, so this is mostly about pruning: run `git fetch --prune` and `git branch -D <branch>` to drop the stale local branch and remote-tracking ref, and if the remote branch somehow survived (didn't auto-delete), remove it with `git push origin --delete <branch>`. Only ever delete a branch whose PR is **merged or closed** — deleting the head branch of an *open* PR auto-closes it. Never touch long-running integration branches (e.g. the `competencies` epic branch, #1905) or the `pr-assets` image branch (below).
* Claude Code — always show front-end changes: when a PR affects the front end (templates, CSS, JS, or anything that changes rendered output), **always include screenshots** in the PR's `### Screenshots` section — never leave it "N/A" for a visible change. **Before/after screenshots are preferred** (side by side, or one under the other) so the reviewer can see exactly what changed; a single "after" shot is the minimum. Capture them from the running app when possible, or from a headless browser reproduction (label it as a reproduction, not the live app). Embed them via the `pr-assets` mechanism below.
* Claude Code — PR screenshots / images: GitHub does **not** render `data:` URIs or arbitrary external images in PR/issue markdown, and headless sessions have no attachment-upload API. To embed an image (e.g. a before/after screenshot captured from the headless browser), commit it to the dedicated **`pr-assets`** branch and reference it by raw URL: `![alt](https://raw.githubusercontent.com/bytedeck/bytedeck/pr-assets/<issue-or-pr>/<name>.png)` (works because the repo is public). `pr-assets` is an **orphan, image-only branch** with no shared history with `develop`; it is **never merged into `develop` and never deleted** — it's exempt from the post-merge cleanup rule above, and is not itself a PR branch (don't open a PR for it). Add images without disturbing your working branch using a throwaway index (git plumbing):
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
  Prefer this for still images; note GitHub only renders `.webm`/`.mp4` as an inline player for *uploaded* attachments (drag-and-drop), not for raw URLs, so screen recordings still have to be handed to the user to attach.

### Changelog conventions (`CHANGELOG.md`)

The audience is **end users** (teachers/students on a deck), not developers — write for someone deciding whether a release affects them and what they now need to do differently. Detailed rationale lives in the linked PRs, so keep entries short and outcome-focused.

* **Format**: newest entry on top, headed `### [x.y.z] YYYY-MM-DD Codename` (h3), with two blank lines between version entries. Each item links its issue(s) as `[#NNNN](https://github.com/bytedeck/bytedeck/issues/NNNN)`.
* **Categories** (omit any that are empty): `New Features`, `Tweaks`, `Bugfixes`, `Codebase`, `Devops`.
* **New Features** — say *how and when* a user would actually use it, not just that it exists. Name the button/field and where it lives, and describe the flow. E.g. don't write "added a badge-grant action"; write "when you change a badge's prerequisites, you're asked whether to check for students who newly qualify; confirm and a page shows how many, then grants them all at once".
* **Tweaks** — brief is fine; one line on what visibly changed.
* **Bugfixes** — describe the **actual problem the user hit** (why the change was needed), not just what code changed. E.g. "HTML typed into a comment was rendered as-is, so a crafted comment could run script for anyone who viewed it; comment text is now escaped" — not "escaped comment HTML".
* **Codebase** — non-user-facing internal work (dependency/framework upgrades, test/lint/perf/refactor). No "(no user-facing change)" parenthetical — the heading already implies it.
* **Devops** — deploys, CI, infrastructure, and public-tenant / project-operator concerns that don't affect a regular deck's users (e.g. the new-deck request flow starting at `/decks/request/`, which only the people running the project touch). Include the relevant URL when the change lives on a specific page.
