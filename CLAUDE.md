# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ByteDeck is a multi-tenant Django LMS (gamified with "quests" and "badges") originating from Timberline Secondary School's Digital Hackerspace. Each tenant (a "deck") is a separate Postgres schema served from its own subdomain via [django-tenants](https://django-tenants.readthedocs.io/en/latest/). The stack is Django + PostgreSQL + Redis + Celery, run with Docker Compose. Python 3.10 is required. The main branch is `develop`.

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

The site only works via `http://localhost:8000` (not `0.0.0.0`) because the multi-tenant architecture requires a domain name. Admin login is `admin` / `password` (from `.env`). Create tenants at `http://localhost:8000/decks/new/`. Full stack: `docker compose up` (web, db, redis, celery, celery-beat).

### Tests and Linting

```bash
# Full test suite + style check (expected before every commit/PR)
python src/manage.py test src && flake8 src

# Faster: parallel, stop on first failure
python src/manage.py test src --parallel --failfast

# Single app / class / test
python src/manage.py test src/announcements
python src/manage.py test src.announcements.tests.test_views.AnnouncementViewTests
python src/manage.py test src.announcements.tests.test_views.AnnouncementViewTests.test_teachers_have_archive_button

# Coverage (open htmlcov/index.html afterwards)
coverage run --source=src ./src/manage.py test src/notifications
coverage html
```

CI (GitHub Actions) also runs `python src/manage.py check` and `python src/manage.py makemigrations --check --dry-run`, so never leave model changes without migrations.

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

* `src/hackerspace_online/` is the Django project package (settings, urls, celery, middleware). A custom test runner (`hackerspace_online/test_runner.py`) patches `model_bakery.baker.make` for the `Prereq` model's GenericForeignKeys — relevant if baker-made `Prereq` objects behave unexpectedly in tests.
* `src/prerequisites/` implements the generic prerequisite system (quests/badges unlocking via GenericForeignKeys), used by `quest_manager` and `badges`.
* `src/djcytoscape/` generates the visual quest map.
* `src/bytedeck_summernote/` customizes the django-summernote WYSIWYG editor used across content models.
* Users: `is_superadmin`-type users exist in all schemas (owner of a tenant; on the public schema they can create tenants), `is_staff` = teachers, regular users = students.
* Local email lands in the `_sent_mail/` directory (used e.g. for the deck-owner confirmation flow).

## Code Style & PR Conventions

* Flake8 with `max-line-length = 150`; migrations excluded (config in `.flake8`). Enforced via pre-commit hooks (`.pre-commit-config.yaml`: trailing-whitespace, pyupgrade, autoflake, flake8 with bugbear/comprehensions/mutable plugins).
* Test naming convention: `test_method_or_class_name__specific_case_being_tested`, e.g. `test_end_active_semester__staff()`. All tests require a useful docstring.
* Bug fixes must be test-driven: include a test that fails without the fix.
* New server-side code is expected to be 100% covered (all logical branches); verify with coverage before a PR.
* All methods and classes need docstrings; non-trivial code needs comments explaining why (link sources like Stack Overflow when code is borrowed).
* Call `model.full_clean()` before `model.save()`.
* Commit messages should reference issues where applicable ("Closes #123").
* Claude Code (web sessions): after pushing a branch with an open PR, subscribe to the PR's activity (`subscribe_pr_activity`) and follow up on CI failures and review comments until the PR is merged or closed.
