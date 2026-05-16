# Auth Shell Build Plan

**Status:** build plan  
**Scope:** first code scaffold for new Retriever before Fetch implementation  
**Inputs:** `AUTH_REDESIGN.md`, `RETRIEVER_CORE_SCHEMA.md`, `CONFIG_AND_HEALTH_CONTRACT.md`, `VM_SETUP_PLAN.md`

## Plain-English Summary

Build the smallest useful new Retriever shell:

- Cloudflare Access proves the person at the door.
- Retriever creates or finds their local profile.
- New users land as pending.
- Master Tate can approve users and assign module access/capabilities.
- Fetch exists only as a disabled/coming-soon module until auth is proven.

This first build is not the new Fetch. It is the front door and permissions foundation that Fetch will sit behind.

## Framework Decision

Use Python/FastAPI with server-rendered HTML and small HTMX-style interactions for the first build.

Why:

- old Retriever already uses FastAPI, Jinja, MySQL, and server-rendered operational pages
- the app will run on a Boone LAN Linux VM under systemd
- the first shell needs secure routing, config validation, MySQL migrations, and simple admin pages more than a heavy frontend
- fewer moving parts means easier deploy, rollback, smoke tests, and support
- Fetch can still later use richer frontend behavior where it matters

Do not start with:

- a separate SPA frontend
- a cloud-only runtime
- local password login as the normal front door
- old Fetch code migration

## First Code Layout

Recommended first scaffold:

```text
projects/retriever-rebuild/
  app/
    __init__.py
    main.py
    config.py
    dependencies.py
    middleware/
      __init__.py
      request_id.py
      security_headers.py
    auth/
      __init__.py
      cloudflare.py
      sessions.py
      permissions.py
    db/
      __init__.py
      connection.py
      migrations.py
      repositories/
        __init__.py
        users.py
        settings.py
        audit.py
    routes/
      __init__.py
      health.py
      auth_shell.py
      admin.py
      fetch_placeholder.py
    services/
      __init__.py
      audit.py
      health.py
      feature_flags.py
    templates/
      base.html
      pending.html
      admin/
        users.html
        user_detail.html
      fetch/
        disabled.html
    static/
      app.css
      app.js
  migrations/
    0001_retriever_core_auth.sql
    seeds/
      0001_seed_auth_shell.sql
  tests/
    test_config.py
    test_cloudflare_identity.py
    test_permissions.py
    test_health.py
    test_pending_user_flow.py
  deploy/
    systemd/
      retriever-web.service.example
    smoke.sh
  .env.example
  pyproject.toml
```

The exact layout can shift during implementation, but it should keep config, auth, database, routes, services, templates, migrations, tests, and deploy files separate.

## Build Slice 1: Project Scaffold

Create:

- `pyproject.toml`
- app package
- test package
- `.env.example`
- `app/main.py`
- base route wiring
- local development start command

Recommended initial dependencies:

- `fastapi`
- `uvicorn`
- `jinja2`
- `python-multipart` if forms need it
- `pydantic-settings`
- `mysql-connector-python` or `pymysql`
- `cryptography` or `pyjwt[crypto]` for Cloudflare Access JWT validation
- `httpx` for JWKS fetch and later dependency checks
- `pytest`

Do not add model-provider dependencies until Fetch build starts.

Acceptance:

- app starts locally with fake local settings
- `/health/live` returns `ok`
- `/version` returns static/dev version data
- tests run

## Build Slice 2: Config Validation

Implement config through Pydantic Settings or equivalent strict validation.

Config must enforce `CONFIG_AND_HEALTH_CONTRACT.md`.

Acceptance:

- staging/production fails with missing cookie secret
- staging/production fails when Cloudflare Access validation is disabled
- staging/production fails when `MYSQL_DATABASE != retriever_core`
- Fetch-disabled config starts without model keys
- Fetch-enabled config fails without model keys
- PrintSmith contradictory authority settings fail
- no secret values appear in validation errors

## Build Slice 3: MySQL Migrations

Create first migration:

```text
migrations/0001_retriever_core_auth.sql
```

It should create:

- `schema_migrations`
- `users`
- `roles`
- `capabilities`
- `user_capabilities`
- `user_module_access`
- `sessions`
- `app_settings`
- `delayed_reports`
- `report_artifacts`
- `audit_events`

Use `RETRIEVER_CORE_SCHEMA.md` as the source of truth.

If Boone MySQL does not support JSON columns, replace JSON columns with `LONGTEXT` and validate JSON in app code.

Seed only:

- owner/admin role
- viewer role
- first auth/admin/fetch capabilities
- Master Tate admin user from configured seed email
- safe feature flags with Fetch disabled

Acceptance:

- migration can run once
- migration can be safely detected as already applied
- seed does not create a password
- app can connect using `retriever_app`
- no old `retriever_core` writes happen

## Build Slice 4: Cloudflare Identity

Implement Cloudflare identity handling.

Preferred production path:

- validate Cloudflare Access JWT using JWKS and expected audience
- extract email and display/name claims
- normalize email lowercase
- reject missing/invalid identity
- prevent direct LAN header spoofing from becoming trusted

Local development path:

- allow an explicit local-only dev identity fixture only when `RETRIEVER_ENV=local`
- never allow unsigned identity fixtures in staging/production

Acceptance:

- valid Cloudflare identity loads/creates user
- missing identity is denied in staging/production
- invalid audience is denied
- direct spoofed email header is not enough when JWT validation is required
- local fixture works only in local environment

## Build Slice 5: Pending User Flow

Behavior:

1. Cloudflare-authenticated email arrives.
2. Retriever looks up `retriever_core.users`.
3. Unknown email creates a `pending` user.
4. Pending user sees the access-pending page.
5. Pending user cannot access Fetch, Admin, or future modules.
6. Audit event records pending user creation.

Acceptance:

- first visit creates pending user
- repeat visit reuses pending user
- pending page is plain English
- pending user cannot hit protected routes directly
- audit event is written

## Build Slice 6: Seeded Admin And Approval Flow

Seed Master Tate as active admin/operator using a configured Cloudflare email.

Admin can:

- view pending users
- activate a user
- suspend a user
- block a user
- assign role
- assign module access
- assign capabilities
- assign BooneOps level: `none`, `light`, `medium`

Acceptance:

- seeded admin can open `/admin/users`
- admin can approve a pending user
- approved user can see assigned modules
- suspended/blocked user loses access
- every admin change writes an audit event
- Fetch can be assigned but remains disabled until the feature flag is enabled

## Build Slice 7: App Shell And Disabled Fetch

Create the first app shell:

- header with app name/environment
- signed-in user display
- left navigation based on module access
- Admin visible only to admin capability
- Fetch hidden or disabled based on settings/capability
- Help/basic status page

Admin must be part of the same Retriever shell, not a standalone-looking admin site. The old Retriever pattern was right in this respect: Admin appears as a left-sidebar option for admins and shares the same visual language as the rest of the app.

Fetch placeholder:

- if feature disabled: show "Fetch is not enabled yet"
- if user lacks capability: show permission denied
- do not load model/provider code yet

Acceptance:

- pending user sees pending page only
- active non-admin user sees only assigned modules
- admin sees admin area
- Fetch route cannot become usable accidentally
- UI does not expose old modules
- Admin page shares the same layout and styling as the rest of Retriever

## Build Slice 8: Health, Version, Smoke

Implement:

- `/health/live`
- `/health/ready`
- `/health/deep`
- `/version`
- `../deploy/smoke.sh`

Health checks should use stable dependency names from `CONFIG_AND_HEALTH_CONTRACT.md`.

Acceptance:

- `/health/live` works without DB checks
- `/health/ready` checks config, MySQL, sessions, audit, and enabled features
- disabled features appear as `disabled`, not `failed`
- `/health/deep` hides secrets
- `/version` includes git/app/env details
- smoke script fails on broken required dependencies

## First Test Plan

Minimum tests before moving to Fetch:

- config validation rejects unsafe staging/production config
- config validation accepts safe local config
- migration SQL contains required tables
- Cloudflare identity normalization lowercases email
- invalid Cloudflare identity is denied
- local identity fixture works only in local
- unknown Cloudflare user becomes pending
- pending user cannot access admin/fetch
- seeded admin can approve user
- capability check allows/denies correctly
- suspended/blocked user cannot access app
- health output redacts secret-like values

## Auth Shell Done Means

The auth shell is done when:

1. app starts locally
2. app can run against `retriever_core`
3. config validation prevents unsafe production launch
4. Cloudflare identity maps to Retriever users
5. pending-user flow works
6. Master Tate seeded admin works
7. admin approval and capability assignment work
8. app shell hides disabled/unassigned modules
9. Fetch is present only as disabled/placeholder
10. health/version/smoke checks pass
11. no old Fetch data or old local passwords are required

## Open Questions

- Which Python version should be pinned for the new app VM?
- Should MySQL access use `mysql-connector-python` or `pymysql`/SQLAlchemy?
- Should session state be fully server-side or signed cookie plus DB metadata?
- What exact Cloudflare claim should be treated as display name?
- Should `/health/deep` require admin session, Cloudflare service token, or both?
