# Config And Health Contract

**Status:** planning document  
**Scope:** first `.env.example`, startup validation, and health-check contract for new Retriever  
**Inputs:** `SECRETS_HANDLING.md`, `BUILD_CODE_LAYOUT.md`, `RUNTIME_NOTES.md`, `FETCH_TRUST_PLAN.md`, `PRINTSMITH_TOKEN_AUTHORITY.md`

## Plain-English Summary

New Retriever should fail loudly when production config is missing or contradictory.

Cursor can create `.env.example` and validation code. Real production values live on the Boone VM in `/etc/retriever-rebuild/retriever.env`, not in Git or planning docs.

Health checks should tell us whether the app is alive, ready for users, or degraded because a dependency is missing.

## Environment Files

Use:

| File | Purpose | In Git? |
|---|---|---|
| `.env.example` | names, comments, fake/redacted examples | yes |
| `.env.local` | developer-only local values | no |
| `/etc/retriever-rebuild/retriever.env` | staging/production runtime values | no |

Production env file rules:

- owner `root`
- group `retriever`
- mode `0640`
- read by `retriever-web.service`
- never printed by health checks
- never committed
- rotated if exposed to Cursor, chat, Git, screenshots, or logs

## Required App Config

Recommended first `.env.example` shape:

```text
# App identity
RETRIEVER_ENV=staging
RETRIEVER_PUBLIC_BASE_URL=https://retriever-next.boonegraphics.net
RETRIEVER_BIND_HOST=127.0.0.1
RETRIEVER_PORT=8810
RETRIEVER_COOKIE_SECRET=<generate-on-host>
RETRIEVER_SESSION_TTL_SECONDS=86400

# Cloudflare Access
CLOUDFLARE_ACCESS_ENABLED=true
CLOUDFLARE_ACCESS_TEAM_DOMAIN=<redacted>
CLOUDFLARE_ACCESS_AUDIENCE=<redacted>
CLOUDFLARE_ACCESS_JWKS_URL=<redacted>
CLOUDFLARE_ACCESS_VALIDATE_JWT=true

# MySQL app state
MYSQL_HOST=<redacted>
MYSQL_PORT=3306
MYSQL_DATABASE=retriever_cloudflare
MYSQL_USER=retriever_app
MYSQL_PASSWORD=<redacted>
MYSQL_SSL_MODE=preferred

# Fetch feature gates
FETCH_ENABLED=false
FETCH_GENERAL_QUESTIONS_ENABLED=false
FETCH_UPLOADS_ENABLED=false
FETCH_DELAYED_REPORTS_ENABLED=true

# Model provider
MODEL_PROVIDER=anthropic
ANTHROPIC_API_KEY=<redacted>
MODEL_DEFAULT=<approved-model>

# Docs and PrintSmith routes
DOCS_ROUTE_ENABLED=false
DOCS_SERVICE_URL=<redacted>
PRINTSMITH_ROUTE_ENABLED=false
PRINTSMITH_TOKEN_AUTHORITY_MODE=disabled
PRINTSMITH_TOKEN_PROXY_URL=<redacted>
PRINTSMITH_TOKEN_PROXY_KEY=<redacted>

# BooneOps broker/report path
BOONEOPS_BROKER_ENABLED=false
BOONEOPS_BROKER_URL=<redacted>
BOONEOPS_BROKER_BEARER_TOKEN=<redacted>
BOONEOPS_BROKER_HMAC_SECRET=<redacted>
BOONEOPS_BROKER_REQUIRES_TAILSCALE=true

# Runtime storage
RETRIEVER_SHARED_DIR=/opt/retriever-rebuild/shared
RETRIEVER_UPLOAD_DIR=/opt/retriever-rebuild/shared/uploads
RETRIEVER_REPORT_DIR=/opt/retriever-rebuild/shared/reports

# Logging
LOG_LEVEL=info
AUDIT_LOG_MODE=mysql
AUDIT_LOG_FILE=/var/log/retriever-rebuild/audit.jsonl
```

Implementation choice: use `pydantic-settings` for the first FastAPI scaffold. Framework-specific names can still change during implementation, but the contract is the important part.

## Startup Validation

Production/staging must hard-fail when:

- `RETRIEVER_COOKIE_SECRET` is missing, short, or an insecure default
- Cloudflare Access is disabled in staging/production
- `CLOUDFLARE_ACCESS_VALIDATE_JWT` is false in staging/production without explicit approved exception
- MySQL host, database, user, or password is missing
- `MYSQL_DATABASE` is not `retriever_cloudflare`
- Fetch is enabled without a model provider and model key
- uploads are enabled without upload storage
- delayed reports are enabled without report storage and app database access
- BooneOps broker is enabled without URL, bearer token, and HMAC secret
- BooneOps broker is enabled and Tailscale-required health cannot be checked
- PrintSmith route is enabled with contradictory token authority settings
- token proxy mode is enabled without proxy URL/key
- new-authority token mode is enabled without direct PrintSmith REST credentials
- direct PrintSmith REST credentials are present while authority mode says old Retriever owns the token

Production/staging must not allow:

- `AUTH_ENABLED=false`
- default admin password
- auto-created `admin/admin123`
- fallback cookie secret
- generic SQL execution endpoint
- silent downgrade from signed broker calls to unsigned calls

## Feature Gate Rules

Feature gates should block routes at the server, not only hide buttons.

First launch defaults:

- `FETCH_ENABLED=false` until auth shell is proven
- `FETCH_GENERAL_QUESTIONS_ENABLED=false` until policy is decided
- `FETCH_UPLOADS_ENABLED=false` until retention wording and storage are ready
- `FETCH_DELAYED_REPORTS_ENABLED=true` because heavy work needs progress state
- `PRINTSMITH_ROUTE_ENABLED=false` until old token authority dependency is configured
- `BOONEOPS_BROKER_ENABLED=false` until Tailscale/broker health is proven

When a feature is disabled:

- sidebar item should hide
- route should return a clear disabled/degraded response
- health should show disabled, not failed

## Health Endpoints

Use three levels:

| Endpoint | Purpose | Audience |
|---|---|---|
| `/health/live` | process is running | safe through Cloudflare |
| `/health/ready` | app can serve enabled features | admin/service checks |
| `/health/deep` | dependency detail for troubleshooting | admin only |

## `/health/live`

Minimum response:

```json
{
  "status": "ok",
  "app": "retriever-rebuild",
  "environment": "staging"
}
```

Rules:

- no dependency checks
- no secrets
- fast response

## `/health/ready`

Minimum response shape:

```json
{
  "status": "ok|degraded|failed",
  "environment": "staging",
  "checks": {
    "config": "ok",
    "mysql": "ok",
    "cloudflareAccess": "ok",
    "sessions": "ok",
    "audit": "ok",
    "fetch": "disabled",
    "modelProvider": "disabled",
    "uploads": "disabled",
    "delayedReports": "ok",
    "docsRoute": "disabled",
    "printsmithRoute": "disabled",
    "tokenAuthority": "disabled",
    "booneopsBroker": "disabled",
    "tailscale": "disabled"
  }
}
```

Status meanings:

- `ok`: required and working
- `disabled`: intentionally off
- `degraded`: enabled but limited or unreachable
- `failed`: enabled and required, but not working

`/health/ready` should fail deployment smoke tests when required launch dependencies are `failed`.

## `/health/deep`

May include:

- dependency names
- enabled/disabled state
- last successful check time
- error category
- request ID/correlation ID
- app version
- git SHA
- Cloudflare identity validation mode
- token authority mode
- BooneOps broker route status
- Tailscale broker reachability
- report storage path status

Must not include:

- env values
- database URLs
- passwords
- bearer tokens
- HMAC secrets
- PrintSmith tokens
- proxy keys
- raw prompts
- uploaded customer text
- full authorization headers

## Version Endpoint

Use:

```text
GET /version
```

Minimum response:

```json
{
  "app": "retriever-rebuild",
  "version": "0.1.0",
  "gitSha": "<full-sha>",
  "gitRef": "<ref>",
  "builtAt": "<iso-timestamp>",
  "deployedAt": "<iso-timestamp>",
  "environment": "staging",
  "host": "bggol-retriever01"
}
```

Do not include secrets, raw env values, or database URLs.

## Dependency Names

Use stable names in config, health, logs, and audit:

- `config`
- `mysql`
- `cloudflareAccess`
- `sessions`
- `audit`
- `fetch`
- `modelProvider`
- `uploads`
- `delayedReports`
- `docsRoute`
- `printsmithRoute`
- `tokenAuthority`
- `booneopsBroker`
- `tailscale`
- `artifactStorage`

Stable names make the status bar, health UI, logs, and smoke tests easier to line up.

## Smoke Test Contract

First smoke command:

```bash
sudo /opt/retriever-rebuild/bin/smoke.sh
```

Minimum checks:

1. localhost `/health/live`
2. localhost `/health/ready`
3. localhost `/version`
4. Cloudflare hostname gives Access challenge or valid service-token response
5. pending-user flow blocks unapproved users
6. seeded admin can load app shell
7. disabled Fetch route fails clearly
8. enabled dependencies appear as `ok`, `degraded`, or `failed`
9. disabled dependencies appear as `disabled`
10. health output contains no secret fragments

## Logging And Redaction

Redact before logs:

- `Authorization`
- `Cookie`
- `X-Token-Proxy-Key`
- bearer tokens
- HMAC signatures
- PrintSmith token values
- database passwords
- model provider keys
- customer-upload text

Log useful metadata:

- request ID
- correlation ID
- user ID or service ID
- route
- capability
- dependency name
- result
- error category

## Open Questions

- Should local development allow unsigned Cloudflare identity fixtures, or should every dev request use a test identity middleware?
- Should `/health/deep` be hidden behind admin session only, Cloudflare service token only, or both?
- Which model provider and default model are approved for first Fetch build?
- What retention periods should config enforce for sessions, reports, artifacts, and audit metadata?
