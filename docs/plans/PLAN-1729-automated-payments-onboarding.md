# Implementation Plan — Automated Payments & Onboarding via Stripe (Epic #1729)

Status: **in rollout** · Branch: `claude/feature-1729-plan-tb1zqe` · Date: 2026-07-21, status updated 2026-07-30 (see §0)

This plan covers the remainder of epic #1729 and its sub-issues (statuses as of 2026-07-30):

* #1730 (new user form and response): **done** (trial-mode enforcement #2077, trial banner #2074)
* #1731 (subscription via Stripe API): checkout half merged (#2089); webhook half open as #2110
* #1733 (in-app messages/notifications when limits are approached): merged (#2083), report-only until `DECK_NOTICES_ENABLED` is flipped on
* #1734 (deck suspended if not renewed): design settled 2026-07-30 (owner-only model, §0.2); landing as steps B1-B5, B1 = #2210
* #2043 (link existing manually-subscribed decks to their Stripe subscriptions): backfill command ships with #2110; run at rollout (§10.3)
* #2044 (retire unpaid/unused decks): admin deletion guard merged (#2146); deletion clock rework lands with step B3 (see §10.5)

---

## 0. Rollout status (updated 2026-07-30)

This section is the live ledger for the epic. Everything below it (§1 onward) is the original 2026-07-21 proposal, kept for the design rationale; where the two disagree, this section wins. The biggest change since the proposal: the suspension-semantics question (§6.3, §11 Q1/Q2) was settled on 2026-07-30 with a redesign that replaces both of the original options (§0.2).

### 0.1 Shipped

Phases 1 through 6 of the §8 breakdown are merged into `develop`:

| §8 phase | PR | What landed |
|---|---|---|
| 1. Status groundwork | #2047 | Derived status properties, count fixes, `deck_status_report` command |
| 2. Nightly refresh task | #2070 | `daily-deck-status-check` beat fan-out; removed the `TenantAdmin` N+1 |
| 3. Status banner | #2074 | Trial/expiring/over-limit/suspended banner variants |
| 4. Active-user cap | #2077 | Cap enforced at course registration; archive-students help |
| 5. Reminder engine | #2083 | `DeckNotice` cadence, limit warnings, suspension notice (report-only behind `DECK_NOTICES_ENABLED`) |
| 6. Stripe checkout | #2089 | `stripe` dep, Checkout/Portal, staff Subscription details page |

Follow-up hardening and copy work (mostly staging ops finds): #2111 (comped decks keep their cap), #2132/#2133, #2134, #2135, #2137, #2138, #2140, #2142 (banner and subscription-page copy), #2146 (admin deletion guard for #2044), #2178 (admin cap authoritative; its once-per-suspension reset is removed again by step B1 below), #2184 (nightly task bails on non-deck schemas), #2186 (notice emails carry full dates, seat usage, the logo), and #2200 (the suspension-lifecycle copy hotfix on `staging`: owner-only sign-in copy, deletion countdown, Maintenance pitch, Bytedeck-signed emails with the non-profit Society footer).

Process conventions that now bind this epic's PRs: conventional-commit type prefixes (#2206) and the no-em-dash rule (#2208).

### 0.2 The suspension redesign (decided 2026-07-30; supersedes §6.3 and §11 Q1/Q2)

Suspended decks do not "revert to trial mode". The decided model:

1. **Owner-only sign-in**: while a deck is suspended, only the deck owner (and the ByteDeck `admin` support account) can use it; everyone else is signed out at request time, and visitors see the suspended notice.
2. **The open semester auto-closes at suspension** (once per suspension episode, after the grace period): awaiting-approval quest submissions are returned first, negative XP is clamped to zero, and current students drop to zero.
3. **The Maintenance subscription is the trial-equivalent tier**: 5-student reference cap, and it pauses the deletion timer.
4. **The deletion clock runs from the suspension date**: a suspended deck becomes deletable 365 days after suspension began (not keyed on last staff login).
5. **Trials get the same 30-day grace period as paid subscriptions** before suspension: a trial is treated as just another kind of subscription.
6. **Suspension never touches the admin-set cap** (`max_active_users`): the #2178 cap reset is removed; the trial cap stays a reference number for copy and Stripe price metadata only.

The lifecycle copy for this model already shipped to production via hotfix #2200; the enforcement lands on `develop` as small sequential PRs, each starting when the previous one merges:

| Step | Scope | Status |
|---|---|---|
| B1 | Owner-only sign-in middleware (`OwnerOnlyWhenSuspendedMiddleware`); remove the #2178 cap reset | **#2210 open** (fills §8's Phase 8 slot) |
| B2 | Semester auto-close at suspension: once per episode in `deck_status_check`, return awaiting-approval submissions first, clamp negative XP to 0; fix `get_active_user_count` to count only `active=True` registrations | next (starts when B1 merges) |
| B3 | Deletion clock from suspension: `suspended_since` / `deletion_date` properties; rework `is_deletable` to key on 365 days suspended | queued |
| B4 | Unified grace deadline: trials get the same 30-day grace as paid subscriptions (single latest-clock deadline) | queued |
| B5 | Copy-alignment pass: re-check banners, subscription page, and every notice email against the now-real behavior | queued |

### 0.3 In flight and remaining

* **#2110 (§8 Phase 7: webhook + sync)**: open, checks green, awaiting review. Its `deck_status_check` branch still calls the #2178 cap reset that B1 deletes; the next `develop` sync resolves that by dropping the call and keeping the nightly Stripe reconcile step.
* **Deploy-time ops after Phase 7 merges** (§10.4): set the `STRIPE_*` keys, register `decks/stripe/webhook/` for the five handled event types, create the Stripe Prices with `metadata.max_active_users` (including the Maintenance tier with a cap of 5), run the #2043 legacy backfill, then flip `DECK_NOTICES_ENABLED` on after a report-only cycle (§10.2).
* **§8 Phase 9 (optional guards)**: still unscheduled polish; unchanged.

---

## 1. Where things stand today

**Already merged (mostly via #1903 and follow-ups #1928, #1938, #1939, #1948, #1955, #1963):**

* The public deck-request flow: `RequestNewDeck` (name/email + invisible reCAPTCHA) → single-use cache-backed nonce (`DeckRequestService`, `src/tenant/utils.py`) → verification email → `verify_deck_request` → `TenantCreate` gated by `EmailVerificationRequiredMixin` (staff bypass) → schema creation + owner provisioning with a random password → welcome email → login redirect. Admin `/decks/new` still works unchanged.
* The billing substrate on `Tenant` (`src/tenant/models.py:75-129`): `max_active_users` (default 5), `max_quests` (default 100), `trial_end_date` (default today+60d), `paid_until`, and cached counters `active_user_count`, `total_user_count`, `quest_count`, `owner_email_cached`, `owner_full_name_cached`, `last_staff_login`.

**What does NOT exist yet (confirmed by full-tree search):**

* No enforcement anywhere: nothing reads `max_active_users`, `max_quests`, `trial_end_date`, or `paid_until` to gate anything. The only surface is jQuery cell-coloring in the public admin changelist (`src/tenant/templates/admin/tenant/tenant/change_list.html`, from #1494 — note its 0–30-day "gold band" implies a 30-day grace convention).
* No Stripe code or dependency. The `/pages/subscribe/` page is a production-DB flatpage pointing at a manually managed Stripe checkout (#587/#1506).
* No scheduled refresh of the cached counters — they refresh only via an acknowledged N+1 loop in `TenantAdmin.get_queryset` (`src/tenant/admin.py:217-226`, `FIX` comment).
* No trial banner, no suspension state, no reminder machinery.

**Pre-existing defects this epic must fix first (they'd corrupt enforcement):**

1. `Tenant.get_active_user_count()` (`src/tenant/models.py:194-201`) double-counts staff who are enrolled in a course: it adds `is_staff` count + `CourseStudent.objects.all_users_for_active_semester()` *without* `students_only=True`.
2. `Tenant.update_cached_fields()` saves the whole row (no `update_fields`), racing concurrent admin edits.
3. The `TenantAdmin.get_queryset` N+1 refresh loop (the `FIX` comment) — replaced by the nightly task below.

**Related artifact:** PR #1765 ("Automated Payments", yujinyuz, stale since 2025-03) sketched Checkout + webhook + `stripe_customer_id`/`stripe_subscription_id` fields. Its migration base predates #1903, it uses the old guessable-password owner setup, and it hardcodes a price ID. **Disposition: closed as superseded on 2026-07-21** (its event list and metadata idea are mined below; nothing is rebased). Its recorded TODO — "price IDs in env or a db model?" — is answered below (neither: Stripe Price metadata).

---

## 2. Design summary

**Architecture: lean "Stripe as source of truth".** No new Django app, no dj-stripe. Stripe holds subscription truth; the public-schema `Tenant` row caches exactly four scalars (`stripe_customer_id`, `stripe_subscription_id`, `paid_until`, `max_active_users`). All lifecycle logic derives from properties computed from fields that already exist. One nightly beat task refreshes counts, evaluates the #1733 reminder cadence, and sends notices. Enforcement sits at the two places a user *becomes active* (course registration), plus an optional suspension gate pending the #1734 decision.

Key decisions and rationale:

| Decision | Choice | Why |
|---|---|---|
| Stripe library | Raw `stripe` SDK (`stripe>=15.3.1,<16`, per the repo's floor-at-current/cap-next-major pin policy), not dj-stripe | With the repo now on Python 3.12 / Django 5.2, dj-stripe 2.11.0 *is* installable — so this is a genuine architectural choice, not a compatibility necessity. The raw SDK still wins for this epic: dj-stripe lands ~30 public-schema tables through `migrate_schemas --shared` to obtain 4 scalars; its recent minors (2.10, 2.11) each fully **reset their migrations**, forcing stepwise upgrades — an unwelcome property for a multi-tenant shared-schema deploy; and its 2.10+ restructuring moved most mirrored data out of concrete columns into a `stripe_data` JSONField, shrinking the queryable-mirror value that was dj-stripe's main draw. The epic body itself asks only that subscription info be "cached in Django or easily retrievable via Stripe API". Revisit dj-stripe if in-app invoice history or broader billing UX ever lands on the roadmap. |
| Billing state | **Derived properties**, no stored status enum | A stored `status` field duplicates state derivable from `trial_end_date`/`paid_until`, drifts when admins edit dates, and forces a risky production data migration classifying every live deck. Properties can't drift and need no backfill. |
| Payment UX | Stripe-hosted Checkout + Customer Portal | No card handling, no plan-change UI, no PCI surface. Upgrades/downgrades/cancellation are Portal features. |
| Tier configuration | Metadata on Stripe Prices (`metadata.max_active_users` = 40/80/120), mirrored nowhere | Adding/re-pricing tiers requires a dashboard edit, not a deploy. Resolves #1765's TODO. Fallback map in settings if metadata is absent. |
| Suspension (#1734) | Cap reverts to trial limits via `effective_max_active_users`; **student lockout is a maintainer decision** (§6.3) | "Back to trial mode" falls out of one property. Whether over-cap students are also blocked needs sign-off — the `paid_until` help text ("inaccessable to students after this date") and #1734's "only allow 5 to log in?" suggest yes; the plan specs both options. |
| Where code lives | Existing `tenant` app (SHARED_APPS) | It already owns the registry, onboarding, admin, and email task. A `payments` app extraction is a future option once billing code has real mass. |
| Reminder idempotence | `DeckNotice` ledger keyed by `(tenant, kind, threshold, period_key)` | `period_key` = the deadline the notice was about, so a renewal that advances `paid_until` re-arms the cadence automatically — no bespoke reset logic. |
| Webhook idempotence | `StripeEventLog` with unique `event_id` | Duplicate deliveries return 200 immediately; the log doubles as an audit trail for the repo's first `csrf_exempt` endpoint. |
| Missed webhooks | 30-day grace + nightly reconcile + admin "Sync from Stripe" action | Webhooks are an optimization, not a single point of truth. |

---

## 3. Data model changes (all in `tenant` app, public schema, via `migrate_schemas --shared`)

**Migration 1 (PR 6):** two new fields on `Tenant`:

```python
stripe_customer_id = models.CharField(max_length=255, blank=True, default="", db_index=True)
stripe_subscription_id = models.CharField(max_length=255, blank=True, default="")
```

Both editable in `TenantAdminForm` so admins can hand-link existing manually subscribed decks (§10.3). Cut fresh from the current migration head — **not** #1765's stale migration 0015.

**Migration 2 (PR 5):** notice ledger:

```python
class DeckNotice(models.Model):
    """Idempotence/audit log for deck status notices (one row per sent notice)."""
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="notices")
    kind = models.CharField(max_length=20, choices=...)   # expiry / limit / suspended / payment_failed
    threshold = models.CharField(max_length=20)           # 'd30','d14','d7','daily-2026-08-01','pct80','pct100'
    period_key = models.CharField(max_length=32)          # str(governing deadline) or 'YYYY-MM' for limit notices
    sent_on = models.DateField(auto_now_add=True)
    class Meta:
        unique_together = ("tenant", "kind", "threshold", "period_key")
```

**Migration 3 (PR 7):** webhook audit:

```python
class StripeEventLog(models.Model):
    """Idempotency + audit for received Stripe webhook events."""
    event_id = models.CharField(max_length=255, unique=True)
    event_type = models.CharField(max_length=100)
    schema_name = models.CharField(max_length=63, blank=True, default="")
    received_at = models.DateTimeField(auto_now_add=True)
    processed = models.BooleanField(default=False)
    error = models.TextField(blank=True, default="")
```

**No changes** to `trial_end_date`, `paid_until`, `max_active_users`, `max_quests` — they keep their meaning and stay admin-editable (the manual override path for comped/legacy decks).

---

## 4. The status model (derived properties on `Tenant`, no schema change)

Constants in `tenant/models.py`: `TRIAL_MAX_ACTIVE_USERS = 5`, `GRACE_PERIOD_DAYS = 30` (codifies the #1494 admin-colorization convention).

```python
@property
def subscription_active(self):   # paid, or within grace
    return self.paid_until is not None and date.today() <= self.paid_until + timedelta(days=GRACE_PERIOD_DAYS)

@property
def in_grace_period(self):
    return self.subscription_active and date.today() > self.paid_until

@property
def is_on_trial(self):
    return (not self.subscription_active
            and self.trial_end_date is not None and date.today() <= self.trial_end_date)

@property
def is_suspended(self):
    """Both clocks (whichever were ever set) have lapsed. A deck with BOTH dates blank is
    'unmanaged' (comped/legacy) and is never suspended — an explicit admin state."""
    if self.subscription_active or self.is_on_trial:
        return False
    return self.paid_until is not None or self.trial_end_date is not None

@property
def effective_max_active_users(self):
    if self.max_active_users == -1:          # unlimited, admin-set
        return -1
    return self.max_active_users if self.subscription_active else TRIAL_MAX_ACTIVE_USERS

@property
def days_until_expiry(self):     # governing deadline: paid_until if subscribed else trial_end_date
    ...
```

Note the `is_suspended` predicate deliberately handles the deck whose admin cleared `trial_end_date` (legal per its help text) but whose `paid_until` lapsed — that deck **is** suspended. Only a deck with *both* dates blank escapes suspension, and that state is reachable only by explicit admin edit (documented as the "comped" mechanism).

A cached accessor `tenant.utils.get_current_deck()` returns the `Tenant` row for `connection.schema_name` (per-schema cache key, 1 h TTL, mirroring the `SiteConfig.get()` pattern), invalidated on `Tenant.post_save` **and explicitly by the webhook sync** so un-suspension after payment is prompt, not up-to-1h stale.

---

## 5. Stripe integration (#1731)

### 5.1 Checkout & Portal (tenant-side, staff-only)

*(As built in PR 6: view `tenant.views.SubscriptionDetail` at URL name `decks:subscription` — the maintainer asked for this page to double as a "Subscription details" page in the admin menu, visible to all staff.)*

New view (`NonPublicOnlyViewMixin` + staff required, mounted in `tenant/urls.py`):

* GET — the **Subscription details** page (maintainer request, 2026-07-22): billing status (trial/subscribed/grace/suspended/managed-manually), trial/paid dates with days remaining, seat usage (**live** current-student count vs cap, "Unlimited" for -1), at-limit warning, archive-help link, and the upgrade/renew action. Linked from the admin dropdown ("ByteDeck" section) for all staff.
* POST (no `stripe_customer_id` yet): creates `stripe.checkout.Session(mode='subscription', client_reference_id=tenant.schema_name, customer_email=owner email, metadata={'schema_name': ...}, success_url=..., cancel_url=...)` with an idempotency key, then redirects.
* POST (already a customer): creates a `stripe.billing_portal.Session` instead — upgrades, downgrades, card changes, and cancellation are all Portal-hosted; we build no plan-change UI.
* Success page shows "Activating your subscription…" and **polls** a status endpoint rather than assuming the webhook already landed (closes the redirect-beats-webhook race). In PR 6 the poll target itself reconciles the checkout session against Stripe (linking ids + advancing `paid_until`), so checkout works before the webhook exists.
* Degrades to a "billing not configured" notice when Stripe keys are absent (the action then falls back to the public subscribe flatpage), so dev boots clean.
* **All subscribe links point here** (maintainer request): the status banner, the at-capacity refusal page, and every reminder email now link to `decks:subscription` instead of the public flatpage — `get_public_subscribe_url` survives only as this page's own not-configured fallback.

### 5.2 Webhook (public-only)

`tenant.views.stripe_webhook` at `decks/stripe/webhook/` — the repo's first `@csrf_exempt` view, wrapped `@public_only_view` (under the single `ROOT_URLCONF` it resolves on every host but 404s on tenant schemas; note `SHOW_PUBLIC_IF_NO_TENANT_FOUND=True` means unknown-host probes also reach it, so signature failure must 400 fast without DB work). Every request is verified with `stripe.Webhook.construct_event` against `STRIPE_WEBHOOK_SECRET`.

Events handled — each handler is a thin translator that resolves the `Tenant` (via `client_reference_id`/metadata `schema_name`, falling back to `stripe_customer_id`) and calls **one named method**; handlers never write limit fields directly:

| Event | Action |
|---|---|
| `checkout.session.completed` | Link `stripe_customer_id`/`stripe_subscription_id`; then sync |
| `customer.subscription.created` / `updated` / `deleted` | `tenant.sync_from_stripe_subscription(sub)` |
| `invoice.paid` | Same sync (extends `paid_until`) |
| `invoice.payment_failed` | Owner email + in-app notice (no state change; grace covers it) |
| anything else | Log + 200 |

`Tenant.sync_from_stripe_subscription(sub)` is the **single write path**: sets `paid_until = current_period_end.date()`, `max_active_users = int(price.metadata['max_active_users'])` (fallback `STRIPE_PRICE_TIER_MAP` in settings), saves with `update_fields=[...]`, and invalidates the deck's cache entry. It never *lowers* `paid_until` from an event older than the last-processed one (monotonic guard using `StripeEventLog`).

Idempotence: `StripeEventLog.event_id` unique — duplicates return 200 before any handler runs.

### 5.3 Recovery & reconciliation

* **Admin action** "Sync selected decks from Stripe" on `TenantAdmin`: `stripe.Subscription.retrieve` + the same sync method. This is both the missed-webhook recovery path and the linkage path for legacy manual subscribers.
* **Nightly reconcile** (part of the daily task, §7): for every tenant with a `stripe_subscription_id` whose local dates disagree with expectation, re-fetch and re-sync. A webhook outage shorter than the 30-day grace can never suspend a paying deck.

### 5.4 Configuration

`STRIPE_PUBLISHABLE_KEY` / `STRIPE_SECRET_KEY` / `STRIPE_WEBHOOK_SECRET` / `STRIPE_PRICE_ID` (the recurring Price checkout subscribes decks to; the tier list can replace it later) via `env(..., default=None)` following the RECAPTCHA presence-check pattern (`settings.py:609-627`); placeholders in `.env.example` and `.env.example.aws`. Extend `_validate_deployment_settings` to require the webhook secret in production once billing is enabled. Stripe dashboard ops (documented in the PR): create Products/Prices for the 40/80/120 tiers (monthly + annual) with `lookup_key`s and `metadata.max_active_users`; register the webhook endpoint for the five event types.

---

## 6. Enforcement (#1730 remainder + #1734)

### 6.1 The choke points (the cap on *becoming* active)

Deck student-state vocabulary (maintainer definitions, post-#2077): **current** = registered in a course in the active semester — *only current students count toward deck limits*; **active** = every other non-archived student (can sign in, doesn't count); **inactive/archived** = `is_active=False`, can't sign in, listed in their own tab. Staff and superusers never count (maintainer decision, PR #2047). The model fields (`max_active_users`, `active_user_count`) keep their legacy "active" naming but meter **current** students. The cap belongs where a student *becomes current* — course registration — not at login:

* `courses.views.CourseStudentCreate` — both the form path and the `simplified_course_registration` auto-create path (`courses/views.py:327`).
* Staff-side `courses.views.CourseAddStudent`.

Shared `ActiveUserLimitMixin` (or `tenant/limits.py` helper `can_add_active_user()`) compares a **live** recount (not the nightly cached field) against `effective_max_active_users`; skips when `-1` or the user is already active. Refusal messages: students see "This deck has reached its active-student limit — ask your teacher"; staff see the limit with links to the archive-students help page and `decks:subscribe`.

Existing active students are **never** auto-deactivated by a cap — it only stops new activations.

Optional follow-ups (last PR): `max_quests` guard in `QuestCreate`/`QuestCopy` dispatch; `CustomAccountAdapter.is_open_for_signup` block for at-cap decks with simplified registration on (signup there leads straight to auto-enrollment).

### 6.2 Trial mode (closes #1730's first open checkbox)

Nothing extra to build: a new deck has `paid_until=None`, `trial_end_date=today+60`, `max_active_users=5`, so `effective_max_active_users` is 5 the moment the choke-point PR lands.

### 6.3 Suspension semantics (RESOLVED 2026-07-30: owner-only suspension, see §0.2)

The original question here offered two options: Option A (soft: the cap reverts to the trial default, no lockout) and Option B (a middleware gate that blocks non-staff requests while the deck is over the trial cap). The 2026-07-30 decision supersedes both: a suspended deck is **owner-only** (only the deck owner and the ByteDeck `admin` support account can use it; everyone else is signed out at request time), the open semester auto-closes, and the admin-set cap is never touched. §0.2 has the full model and the B1-B5 implementation steps; B1 (#2210) ships the request-time middleware (request-time rather than login-time because the 8-week session cookie outlives a suspension, and it also covers Google sign-ins). The original options' text is preserved in this file's git history.

---

## 7. Notifications, reminders, banner (#1733 + #1730's banner checkbox)

### 7.1 Daily beat task

**One** new beat entry in `hackerspace_online/celery.py`, named once and never renamed (removed/renamed entries keep firing from the DatabaseScheduler DB until manually deleted — see the warning comment above `beat_schedule`): `daily-deck-status-check` → `tenant.tasks.daily_deck_status_check_for_all_tenants`, 06:00 (after the 05:00 digest; the schedule now has four daily entries, the newest being session cleanup at 02:00). It follows the established dispatcher/fan-out pattern — `tenant/tasks.py` itself now contains one to copy (`clear_expired_sessions_in_all_schemas`, added with the ops-reliability work in #2003), alongside `notifications/tasks.py:21-28`. A bonus from #2003: Celery task failures now email `ADMINS` (throttled), so a broken status task can no longer fail silently for weeks. The dispatcher iterates `get_tenant_model().objects.exclude(schema_name__in=[public, library])` (library via `library.utils.get_library_schema_name` — easy to forget, and emailing/suspending the shared library would be a bug) and `apply_async`s a per-schema `deck_status_check` under `tenant_context`.

In its **first** shipped version (PR 2) the per-schema task only calls `tenant.update_cached_fields()` — replacing the `TenantAdmin.get_queryset` N+1 loop. Later PRs extend the same task body (never the beat entry name) with:

1. **Expiry cadence** against `days_until_expiry` (governing deadline: `paid_until` if subscribed else `trial_end_date`): thresholds `d30`, `d14`, `d7`, then `daily-YYYY-MM-DD` inside the final week **and through the grace window**. Exactly-once via `DeckNotice` `(tenant, kind, threshold, period_key)`; a renewal advances `paid_until` → new `period_key` → cadence re-arms with no reset code. Date-based predicates (not tick-based) make multi-day beat outages catch-up-safe: late, never duplicated.
2. **Limit warnings** at ≥80 % and ≥100 % of `effective_max_active_users` (`pct80`/`pct100`, `period_key='YYYY-MM'` so they re-arm monthly rather than firing once forever or daily).
3. **Suspension notice** once, the day `is_suspended` flips true.
4. **Stripe reconcile** (§5.3) for linked tenants.

### 7.2 Channels

* **Email** to the deck owner via the existing `tenant.tasks.send_email_message` async task (BCC convention), templates under `tenant/templates/tenant/email/` — every limit/suspension email includes the archive-students instructions link (#1733 requirement) and the deck's subscribe URL built from `tenant.get_root_url()`.
* **In-app**: `notify.send(sender=SiteConfig.get().deck_ai, recipient=deck_owner, affected_users=<staff>)` inside `tenant_context` — the established deck-AI convention. Transient by design (90-day purge); persistence comes from the banner.
* **Banner**: a `deck_status` context processor (registered next to the existing `config` processor; returns `None` on the public schema) exposes the cached `Tenant` row; a new include in `src/templates/base.html` beside the messages snippet renders, in priority order: suspended (staff + students) → over-limit (staff) → expiring ≤14 d (staff) → **Trial Mode info bar with subscribe link** (staff; closes #1730's second checkbox). Until `decks:subscribe` exists (PR 6), the subscribe link must be an **absolute URL to the public host** (`https://{ROOT_DOMAIN}/pages/subscribe/`) — flatpages are per-schema, so a schema-relative `/pages/subscribe/` 404s on every deck.

### 7.3 Archiving instructions (#1733)

A short staff-only help page (courses app) explaining the two existing mechanisms — end the active semester (`end_active_semester` sets `CourseStudent.active=False`) and the per-user `is_active` toggle (`ProfileListInactive` tab) — linked from banners and emails. Optional quality-of-life: a bulk "archive selected students" action on the profile list.

---

## 8. Phased PR breakdown

Each PR is independently shippable, TenantTestCase-covered, and maps to sub-issue checkboxes. PRs 1–5 require **zero Stripe code** — the epic's UX value lands even if the Stripe half stalls (as #1765 did).

| PR | Scope | Closes |
|---|---|---|
| **1. Status groundwork** | Constants; the derived properties (§4); fix `get_active_user_count` staff double-count; `update_cached_fields(update_fields=...)`; a read-only `deck_status_report` command (dry-run by design) showing per-deck before/after counts (the fix changes real numbers for every deck — see §10.2). Pure model layer + tests (freezegun). | foundation |
| **2. Nightly refresh task** | `daily-deck-status-check` beat entry + fan-out task (counts-refresh only); delete the `TenantAdmin.get_queryset` N+1 loop. | the `FIX` comment |
| **3. Status banner** | `get_current_deck()` cached helper + invalidation; `deck_status` context processor; banner include (trial/expiring/over-limit/suspended variants); absolute-URL subscribe link. | #1730 banner ☑ |
| **4. Active-user cap** | `can_add_active_user()` live check; guards in `CourseStudentCreate` (incl. simplified path) + `CourseAddStudent`; refusal UX; archive-students help page. | #1730 trial mode ☑, #1734 mechanics |
| **5. Reminder engine** | `DeckNotice` model; extend the daily task with cadence + limit warnings + suspension notice; email templates; deck-AI in-app notices. Report-only mode for the first cycle (§10.2). | #1733 |
| **6. Stripe checkout** | `stripe` dep; `STRIPE_*` env plumbing; `stripe_customer_id`/`stripe_subscription_id` migration; **Subscription details page** (`decks:subscription`, admin-menu entry for all staff) with Checkout/Portal actions + polling success page that reconciles against Stripe; ALL subscribe links (banner, refusal page, reminder emails) switch to it. | #1731 (half) |
| **7. Webhook + sync** | `stripe_webhook` (csrf_exempt, public-only, signature-verified); `StripeEventLog`; `sync_from_stripe_subscription`; admin "Sync from Stripe" action; nightly reconcile step; legacy-subscriber backfill command + report (§10.3). | #1731 |
| **8. Suspension finish** | Superseded by the §0.2 redesign: this slot is realized by steps B1-B5 (B1 = #2210, the owner-only middleware, replaces the original Option A/B choice). | #1734 |
| **9. Optional guards** | `max_quests` gate in `QuestCreate`/`QuestCopy`; `is_open_for_signup` block for at-cap simplified-registration decks; retire the admin change-list jQuery colorizer in favor of status-driven rendering. | polish |

---

## 9. Testing strategy

* All tests `TenantTestCase` + `TenantClient`; public-schema views (webhook, `SubscriptionView` 404-on-tenant behavior) use the established connection-patching pattern (see the `@patch(..., schema_name=get_public_schema_name())` tests in `hackerspace_online/tests/test_views.py`) — a known source of order-dependent flakes, so keep those tests self-contained. New tests must also satisfy the naming/docstring convention guard added in `hackerspace_online/tests/test_conventions.py` (#2025).
* Date logic (properties, cadence, grace) with `freezegun` (already a dependency); cadence tests assert `DeckNotice` rows and `len(mail.outbox)` across simulated day sequences, including renewal-re-arm and beat-outage catch-up.
* Stripe fully mocked (`unittest.mock` on the `stripe` module); webhook tests cover signature failure (400, no DB writes), duplicate `event_id` (200, no double-processing), out-of-order events (monotonic `paid_until`), and unknown events (200).
* Per repo convention: bug-fix PRs (double-count, N+1) are test-driven; 100 % branch coverage on new code; migrations always present (`makemigrations --check` runs in CI).

---

## 10. Rollout & operations

### 10.1 Sequencing note (the phasing trap)

PR 1's count fix *lowers* `active_user_count` everywhere (staff no longer double-counted) while PR 4 *starts enforcing* a cap that never existed. Land PR 1 well before PR 4, review the `deck_status_report` output against production values **before anyone opens the tenant admin changelist** (its refresh loop rewrites the cached counts with the new formula, flattening the deltas the report exists to show), and pre-announce enforcement to deck owners using the existing admin mass-email action.

### 10.2 Report-only first cycle

PR 5 ships with sends disabled (log-only) for at least one daily cycle in production; review which decks *would* be notified before flipping sends on. Same principle as Option B's `SUSPENSION_LOCKOUT_ENABLED` kill-switch.

### 10.3 Legacy subscriber backfill (#2043)

Existing paying decks subscribed via the manual `/pages/subscribe/` checkout: Stripe has Customers, but nothing links them to Tenants. PR 7 includes a management command that lists active Stripe subscriptions and matches customer email → `owner_email_cached`, emitting a **human-review report** (never auto-linking on ambiguity); misses are hand-linked by pasting `stripe_customer_id` into the Tenant admin + "Sync from Stripe". An unlinked paying deck would otherwise drift toward suspension at its admin-set `paid_until` + grace. After PR 7, retire or redirect the legacy checkout flatpage so new payments always carry `client_reference_id`.

### 10.4 Ops checklist (deploy-time)

* Add `STRIPE_*` keys to the production `.env` (per `production/SERVER-README.md` conventions).
* Stripe dashboard: create tier Products/Prices with `metadata.max_active_users`; register the webhook endpoint (five event types) pointing at `https://bytedeck.com/decks/stripe/webhook/`; test with Stripe CLI event replay.
* Remember the DatabaseScheduler wart: never rename `daily-deck-status-check` once created.

### 10.5 Retiring dead decks (#2044)

Suspension (this epic) is where a deck's lifecycle *pauses*; #2044 defines where it *ends*. Abandoned schemas are a compounding cost (every schema multiplies `migrate_schemas` time and backup size), and today even admin deletes keep the schema (`force_drop=False`), leaving orphans that block deck-name reuse. #2044 builds directly on this plan's machinery: "retirable" is defined in terms of the suspension state plus `last_staff_login`, and the pre-removal reminder series reuses the daily status-check task and `DeckNotice` ledger. Its open question — hard delete vs. `pg_dump`-to-S3 archive with a retention window vs. detach-only — is tracked on the issue. Sequencing: after PR 8, since it consumes the suspension state; the reminder machinery it needs exists from PR 5.

---

## 11. Open questions for @tylerecouture

1. **#1734 semantics:** ANSWERED 2026-07-30. Neither original option: suspended decks are owner-only, the semester auto-closes, and the admin-set cap is untouched (§0.2). Implemented by steps B1 (#2210) through B5.
2. **Grace period:** ANSWERED 2026-07-30. 30 days, and it applies to trials too: a trial is treated as a kind of subscription, so every deck falls back on the same 30-day grace before suspension (step B4).
3. **Reminder cadence confirmation (#1733 said "every day until it ends?"):** shipped as proposed in #2083 (30 d / 14 d / 7 d then daily through expiry + grace); no objection raised.
4. **Tiers:** confirm 40/80/120 active students with monthly + annual prices, and that tier limits should live as Stripe Price metadata (no repo record of amounts needed).
5. **Trial length:** the model default is 60 days; #1730 mentions nothing else. Keep 60?

---

## Appendix A — the dj-stripe evaluation (why the raw SDK)

Verified against PyPI metadata and dj-stripe release notes (2026-07-21), for reviewers who'd reasonably ask "why not dj-stripe?":

| dj-stripe line | Python | Django | Notes |
|---|---|---|---|
| 2.9.x (last: 2.9.2, 2026-01) | ≥3.10 | 4.2 / 5.0 / 5.1 declared | stripe SDK capped `<12` |
| 2.10.x (last: 2.10.4, 2026-06) | ≥3.11 | 5.0 / 5.1 | **Full migration reset**; most concrete columns removed in favour of a `stripe_data` JSONField |
| 2.11.0 (2026-06, latest) | ≥3.11 | ≥5.2 (first 5.2/6.0 support) | **Second full migration reset**; `Plan` model removed; stripe SDK `>=15.0.1,<16` |

On the current stack (Python 3.12 / Django 5.2) dj-stripe 2.11.0 **is installable** — the choice is architectural, not forced:

1. **Scale mismatch**: dj-stripe installs ~30 public-schema tables (all flowing through `migrate_schemas --shared` on every container start) to obtain the four scalars this epic needs on `Tenant`.
2. **Migration churn on a multi-tenant deploy**: 2.10 and 2.11 each reset their migrations entirely, making upgrades stepwise (2.9 → 2.10 → 2.11) — the planned "3.0" rewrite was abandoned in favour of exactly this kind of rolling restructuring, so more resets are plausible.
3. **The mirror's value shrank**: since 2.10, most mirrored Stripe data lives in a `stripe_data` JSONField rather than queryable columns — the strongest historical argument for dj-stripe (a queryable local mirror) is much weaker now.
4. The raw `stripe` SDK (15.3.1 current; requires-python ≥3.9; depends only on `requests`/`typing_extensions`) has zero Django coupling, and this plan's webhook surface is five event types funnelling into one idempotent sync method with a `StripeEventLog` — small enough to own outright.

Worth revisiting if in-app invoice history or richer billing UX ever lands on the roadmap; dj-stripe is actively maintained (accelerating release cadence through 2026).

---

*Prepared by Claude Code from a full-codebase and issue-history survey; see epic #1729 for the sub-issues this phasing closes.*
