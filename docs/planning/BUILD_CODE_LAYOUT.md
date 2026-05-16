# Build Code Layout

**Status:** planning document  
**Scope:** repository structure, config layout, protected files, and Cursor-agent-safe development conventions  
**Security source:** [Cursor Security](https://cursor.com/security)

## Plain-English Summary

The codebase should make the safe path easy.

Cursor agents should be able to build Retriever by reading source, editing templates, running tests, and preparing deployment scripts. They should not need production secrets or live write access to do ordinary development work.

## Source Layout Goals

The rebuild should separate:

- app code
- production deployment scripts
- local development config
- templates and examples
- generated artifacts
- secrets
- migration tools
- tests
- architecture docs

The old `projects/Retriever/` folder remains reference-only unless Master Tate explicitly asks to patch it.

## Cursor-Safe Files

Cursor can freely edit:

- source files
- tests
- docs
- `.env.example`
- config schema
- deployment script templates
- local seed data with fake records
- fixtures with redacted data

Cursor should not edit or create:

- `.env.production`
- live credential files
- raw production database dumps
- raw customer-upload corpuses
- unredacted PrintSmith exports
- private keys
- Cloudflare Tunnel credential JSON
- any file marked as protected governance unless explicitly requested

## Recommended Config Pattern

Use:

- `.env.example` for required variable names and comments
- `.env.local` for local-only development values
- production env file outside Git on the Boone server
- config validation at startup
- hard failure for missing production secrets
- redacted sample payloads in docs and tests

Do not use:

- committed defaults for production secrets
- fallback admin passwords
- automatic production admin creation
- generic SQL execution tools
- broad development bypass flags in production

## Agent And Hook Guardrails

Cursor's security page references agent, MCP, hooks, cloud-agent, and data-governance security guidance. Retriever should adopt a local version of that posture:

- agents can write code, but production actions require explicit deployment steps
- hooks should never exfiltrate secrets
- MCP tools should be least-privilege and environment-specific
- cloud-agent work should not require direct LAN production access
- generated code must be reviewable in Git
- tests should use fake credentials and fixtures

## Model And Data Controls

For code and docs work:

- keep Cursor Privacy Mode enabled
- respect model blocklists if configured
- avoid pasting customer files into prompts
- use redacted logs and fixtures
- prefer synthetic examples for tests

For app runtime:

- Retriever chooses its own model/provider policy
- Fetch customer uploads stay under Fetch privacy rules
- production prompts and logs follow `FETCH_TRUST_PLAN.md` and `AUDIT_LOG_DESIGN.md`

## Framework Decision

Use Python/FastAPI with server-rendered HTML and small HTMX-style interactions for the first build.

Why:

- old Retriever already uses FastAPI, Jinja, MySQL, and server-rendered operational pages
- the app will run on a Boone LAN Linux VM under systemd
- the first shell needs secure routing, config validation, MySQL migrations, and simple admin pages more than a heavy frontend
- fewer moving parts means easier deploy, rollback, smoke tests, and support
- Fetch can still later use richer frontend behavior where it matters

Do not start with a separate SPA frontend, a cloud-only runtime, local password login as the normal front door, or old Fetch code migration.

## Expected Top-Level Rebuild Shape

The first code layout should support this separation:

```text
projects/retriever-rebuild/
  KICKOFF.md
  PLAN.md
  PARKED.md
  SESSION-LOG.md
  HANDOVER.md
  docs/
    README.md
    planning/
      (architecture + trust + runbooks-in-prose live here)
  app/
    main.py
    config.py
    auth/
    db/
    middleware/
    routes/
    services/
    templates/
    static/
  migrations/
  tests/
  deploy/
  scripts/
  fixtures/
```

Rules:

- `fixtures/` contains fake or redacted data only.
- `deploy/` contains scripts/templates, not live secrets.
- `.env.example` contains variable names and fake/redacted examples, not production values.
- `migrations/` contains schema migrations and seed scripts with no real secrets.
- app templates must not expose disabled modules or secret/config details.
- Admin templates must use the same app shell/layout as normal Retriever pages. Admin is a module in the left sidebar for admins, not a separate mini-site.
- Smoke-test pages can be plain while scaffolding, but the target app shell should be clean, consistent, and recognizably Retriever before Fetch UI work starts.

## Review Requirements

Before any production-facing code is built, confirm:

- `.gitignore` blocks env files and generated secret material
- startup config validation exists
- tests do not require production credentials
- deployment scripts read secrets from Boone-controlled locations
- health checks do not leak secret values
- logs redact authorization headers and tokens
- protected files are documented
- old Retriever reference files are not modified by accident

## Open Questions

- Which generated files should be ignored from Git?
- Do we need a local preflight script that scans for accidental secrets before commit?
