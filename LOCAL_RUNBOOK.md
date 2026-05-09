# Local Runbook

**Status:** first local smoke runbook  
**Scope:** run and smoke-test the FastAPI auth shell on this Mac  
**Current mode:** local scaffold, no Boone MySQL required

## Plain-English Summary

This runbook starts the new Retriever auth shell locally and checks the routes that should work before Fetch is built.

Local mode uses a safe development identity from `.env.example` defaults:

- email: `state@boonegraphics.net`
- display name: `Master Tate`
- role behavior: seeded admin fallback when no MySQL config is present

This is not production auth. Real staging/production must use Cloudflare Access JWT validation and `retriever_cloudflare`.

## One-Time Setup

From `projects/retriever-rebuild`:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e ".[dev]"
```

This Mac currently has Python 3.9 available. The scaffold is compatible with that for local verification. The Boone VM Python version remains a deployment choice.

## Run Tests

```bash
.venv/bin/python -m pytest
```

Expectation: **all tests pass** (the count grows with the codebase; if you see failures, fix before shipping).

## Start Local Server

```bash
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8810
```

Local URL:

```text
http://127.0.0.1:8810
```

## Smoke Checks

Expected working routes:

```bash
curl -i http://127.0.0.1:8810/
curl -i http://127.0.0.1:8810/admin/users
curl -i http://127.0.0.1:8810/health/live
curl -i http://127.0.0.1:8810/health/ready
curl -i http://127.0.0.1:8810/health/deep
curl -i http://127.0.0.1:8810/version
```

Fetch route (unauthenticated `curl`):

```bash
curl -i http://127.0.0.1:8810/fetch
```

Expected: **401** or **403** without a session when the app expects Cloudflare or session identity. In **local** mode with **`LOCAL_DEV_IDENTITY_ENABLED=true`**, browser access may show **200** HTML for the Fetch shell. Production-style smoke on Windows uses **`deploy/smoke.ps1`**, not raw `curl` alone.

When you **do** have a session and Fetch access, **`GET /fetch`** returns **200**: the conversation rail works against MySQL when configured. With **`FETCH_ENABLED=false`**, the composer stays **off** and messages are not accepted through ask. With **`FETCH_ENABLED=true`**, ask saves the user line and appends the **stub** reply only (no live model)—and production operators should read **`deploy/WINDOWS_FETCH_RELEASE.md`** before using that flag because validation still requires model env vars.

## Expected Local Behavior

- `/` shows the Retriever auth shell for the local seeded admin.
- `/admin/users` loads the admin user page.
- `/health/live` returns `ok`.
- `/health/ready` returns `ok` in local mode because missing MySQL is `disabled`, not failed.
- `/health/deep` returns redacted config and dependency states, with no secrets.
- `/version` returns app/version/environment metadata.
- `/fetch` behavior depends on identity: without a session, expect **401/403**; with local dev identity in the browser, expect the **Fetch shell**. **`FETCH_ENABLED=false`** still allows **conversation CRUD** when MySQL is configured—the **ask/composer** path stays locked until **`FETCH_ENABLED=true`** (see Windows runbook for production guidance).

## Real Database Mode Later

When Boone MySQL or a local MySQL test database is available:

1. Create `retriever_cloudflare` (and apply migrations including **`0002_fetch_conversations`** if you need conversation tables—same SQL as production).
2. Configure `.env.local` with MySQL connection values.
3. Run:

```bash
.venv/bin/python -m app.db.migrations --seeds
```

Then restart the app and smoke the same routes.

## BooneOps broker and general LLM (production reference)

Windows operator details live in **`docs/runbooks/booneops-broker-fetch-windows.md`** — **`BOONEOPS_BROKER_ENABLED`**, **`BOONEOPS_BROKER_URL`**, **`BOONEOPS_BROKER_BEARER_TOKEN`**, **`BOONEOPS_BROKER_HMAC_SECRET`**, **`BOONEOPS_BROKER_REQUIRES_TAILSCALE`**. **`FETCH_GENERAL_QUESTIONS_ENABLED`** should stay **`false`** until general internet answers ship behind admin + **`fetch.ask_general`** (**`FETCH_TRUST_PLAN.md`**).

## Do Not Do Yet

- Do not set **`FETCH_ENABLED=true`** in **production** without **`deploy/WINDOWS_FETCH_RELEASE.md`**: validation will require model settings even for the stub-only path.
- Do not point at production PrintSmith credentials for unapproved tests.
- Do not paste real Cloudflare Tunnel credentials into `.env.local`.
- Do not migrate old Fetch conversations unless explicitly requested.
- Do not move `retriever.boonegraphics.net` DNS or Tunnel targets without the Windows deploy runbook.

## First Browser Smoke Goal

For this phase, the goal is to prove the shell starts, renders, reports health, shows Admin, and keeps **production-style** deploys on **`FETCH_ENABLED=false`** until deliberate enablement. Locally you may toggle flags for development if you accept the validation rules in **`app/config.py`**.

