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

Expected current result:

```text
47 passed
```

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

Expected disabled Fetch route:

```bash
curl -i http://127.0.0.1:8810/fetch
```

Expected result: `503 Service Unavailable` with a page saying Fetch is not enabled yet.

## Expected Local Behavior

- `/` shows the Retriever auth shell for the local seeded admin.
- `/admin/users` loads the admin user page.
- `/health/live` returns `ok`.
- `/health/ready` returns `ok` in local mode because missing MySQL is `disabled`, not failed.
- `/health/deep` returns redacted config and dependency states, with no secrets.
- `/version` returns app/version/environment metadata.
- `/fetch` returns disabled until auth/admin/session behavior is proven.

## Real Database Mode Later

When Boone MySQL or a local MySQL test database is available:

1. Create `retriever_cloudflare`.
2. Configure `.env.local` with MySQL connection values.
3. Run:

```bash
.venv/bin/python -m app.db.migrations --seeds
```

Then restart the app and smoke the same routes.

## Do Not Do Yet

- Do not enable Fetch.
- Do not point at production PrintSmith credentials.
- Do not paste real Cloudflare Tunnel credentials into `.env.local`.
- Do not migrate old Fetch conversations.
- Do not move `retriever.boonegraphics.net`.

## First Browser Smoke Goal

For this phase, the goal is only to prove the shell starts, renders, reports health, shows Admin, and keeps Fetch disabled.

