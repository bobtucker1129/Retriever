# PrintSmith Token Authority

**Status:** planning document  
**Scope:** preserving the shared `LordTate` PrintSmith REST token authority before new Retriever cutover  
**Inputs:** `REVIEW-2026-05-04-OPUS.md`, `SECRETS_HANDLING.md`, `WEBHOOK_AND_BROKER_AUTH.md`, old Retriever token proxy code and session log

## Plain-English Summary

PrintSmith allows only one live REST token for the `LordTate` vendor. If two apps generate tokens independently, they knock each other offline.

Old Retriever already solved this by becoming the single token authority. New Retriever must not accidentally become a second token owner.

For staging and first launch, old Retriever on `bggol-vesko01` stays the PrintSmith token authority. New Retriever may borrow the token through the existing proxy contract, but it must not generate or delete PrintSmith tokens directly.

Authority moves only when new Retriever PrePress is migrated and ready to become the primary PrintSmith token owner.

## Current Working Contract

Old Retriever exposes two machine-to-machine endpoints:

| Method | Path | Behavior |
|---|---|---|
| `GET` | `/api/printsmith-token` | Returns the current valid token, generating one if needed |
| `POST` | `/api/printsmith-token/invalidate` | Clears the cached token, regenerates, and returns a fresh token |

Authentication:

- request header: `X-Token-Proxy-Key`
- value: shared machine secret stored in the old Retriever service environment
- no user session dependency

Response shape:

```json
{
  "token": "<redacted>",
  "expires_at": "<printsmith-local-iso-time-or-null>",
  "vendor": "LordTate"
}
```

Known status behavior:

- missing or invalid proxy key returns `401`
- upstream PrintSmith failure returns `502`
- successful get/invalidate returns `200`

Current cache:

- database: `retriever_prepress`
- table: `printsmith_api_token`
- key: `vendor`
- cached fields include token and expiration time

Current reason this exists:

- old Retriever and the Node app on LordTate previously generated PrintSmith tokens independently
- PrintSmith's single-token rule caused the two systems to stomp each other
- old Retriever became the shared authority so other systems borrow its token instead of managing token lifecycle themselves

Known current users:

- old Retriever PrePress
- one other project that is currently on hold

## Authority Rule

There must be exactly one active PrintSmith REST token authority for the `LordTate` vendor.

Allowed:

- one service may generate, validate, cache, delete, and regenerate the token
- other services may request the current token from that authority
- clients may cache the borrowed token briefly with an expiry buffer
- clients may ask the authority to invalidate when PrintSmith proves the token is bad

Not allowed:

- new Retriever generating its own `LordTate` token during staging
- `/printsmith`, Fetch, DSF, PrePress, or Node tools each managing token lifecycle separately
- copying raw PrintSmith REST credentials into Cursor or planning docs
- storing borrowed tokens in `.env` files or long-lived app config
- logging returned token values
- using the token proxy key as a general service credential

## Launch Decision

For first staging and first launch:

1. `bggol-vesko01` remains old Retriever and PrintSmith token authority.
2. The sibling Boone LAN app VM runs new Retriever under `retriever-next.boonegraphics.net`.
3. New Retriever treats PrintSmith token access as an external dependency.
4. New Retriever does not receive PrintSmith REST username/password unless and until it becomes the authority.
5. Any new `/printsmith` route uses the existing token proxy or a read-only service that already follows this authority rule.

Plain English: old Retriever gets first dibs until new Retriever PrePress is ready to take over.

## Future Authority Options

### Option A: Keep Old Retriever As Token Authority During First Cutover

Old Retriever keeps serving `/api/printsmith-token` internally even after new Retriever owns the public hostname.

Use this if:

- old PrePress remains live
- old DSF or other modules still need PrintSmith behavior
- the rebuild is not ready to own token lifecycle
- fastest safe cutover is preferred

This is the selected launch posture.

Requirements:

- old Retriever service remains monitored
- token proxy remains reachable from approved Boone/Tailscale hosts
- old proxy key is rotated or confirmed before production cutover
- new Retriever health reports token proxy ready/degraded
- old host is documented as a runtime dependency, not merely a reference box

### Option B: Move Token Authority Into New Retriever

New Retriever becomes the single authority and preserves the old proxy contract.

Use this only after:

- old Retriever PrePress is ready to move, or old PrePress no longer needs to own token lifecycle
- the on-hold project is confirmed idle, migrated, or configured to borrow from the new authority
- new token cache storage is chosen
- new proxy key is stored on the Boone runtime
- old token generation path is disabled or pointed at the new authority
- cutover and rollback behavior are tested

Compatibility requirement:

- keep `GET /api/printsmith-token`
- keep `POST /api/printsmith-token/invalidate`
- keep `X-Token-Proxy-Key` until clients are intentionally migrated to a stronger signed service-auth pattern
- keep `401`, `502`, and `200` semantics unless every client is updated
- keep response fields `token`, `expires_at`, and `vendor`

### Option C: Create A Small Dedicated Token Authority Service

A small Boone LAN service owns the PrintSmith token and both old/new Retriever borrow from it.

Use this if:

- token sharing expands beyond Retriever and one Node app
- old Retriever needs to be retired before new Retriever is fully ready
- the token endpoint should be independent from app deployments

Requirements:

- service-specific secret or signed request auth
- narrow logs and health checks
- no user-facing routes
- clear owner and restart procedure
- tested client migration

This is clean, but it adds another service. It should not block first staging.

## Recommended Path

Use this sequence:

1. Staging: old Retriever remains token authority.
2. New Retriever consumes the old proxy only if `/printsmith` is enabled.
3. First public cutover: old Retriever still remains token authority.
4. Later, when new Retriever PrePress is migrated and ready to become primary, move authority into new Retriever or a dedicated service.
5. Keep the old proxy contract until every current client is migrated or intentionally retired.

Recommended first public cutover posture: Option A.

## New Retriever Runtime Behavior

New Retriever should model token authority as a dependency with explicit states:

- `disabled`: `/printsmith` is off
- `using_old_authority`: new Retriever borrows from old Retriever
- `using_new_authority`: new Retriever owns the token lifecycle
- `degraded`: authority is unreachable or rejects auth
- `blocked`: config allows more than one authority

Startup validation:

- production must fail if configured to own token authority without PrintSmith REST credentials
- production must fail if configured to borrow from a proxy without a proxy URL and proxy key
- production must fail if both direct REST credentials and proxy borrowing are enabled without an explicit authority mode

Health checks:

- `/health/ready` reports whether `/printsmith` token authority is ready or degraded
- `/health/deep` can include authority mode, proxy hostname, last successful token check time, and error category
- health output must never include token values, proxy keys, usernames, passwords, or credential fragments

## Secrets

Secret names should be documented in `.env.example`, not filled with real values.

Likely variables:

```text
PRINTSMITH_TOKEN_AUTHORITY_MODE=disabled|using_old_authority|using_new_authority
PRINTSMITH_TOKEN_PROXY_URL=<redacted>
PRINTSMITH_TOKEN_PROXY_KEY=<redacted>
PRINTSMITH_API_BASE_URL=<redacted>
PRINTSMITH_API_VENDOR=LordTate
PRINTSMITH_API_USERNAME=<redacted>
PRINTSMITH_API_PASSWORD=<redacted>
```

Rules:

- staging/new Retriever should start with proxy URL/key only, not direct PrintSmith REST credentials
- direct REST credentials belong only on the active token authority host
- proxy key rotation is required if the key appears in Cursor, chat, Git, logs, screenshots, or transcripts
- token values are secrets even though they are short-lived

## Audit And Logs

Audit these events:

- token proxy request accepted
- token proxy request denied
- token invalidation requested
- token regenerated
- token authority dependency degraded
- token authority mode changed
- token authority cutover started/completed/rolled back

Log only:

- timestamp
- service/client identity when known
- request ID/correlation ID
- action
- vendor
- result
- error category
- source host or service origin when safe

Never log:

- token value
- proxy key
- PrintSmith REST password
- full authorization headers
- raw upstream credential payload

## Cutover Checklist

Before moving `retriever.boonegraphics.net` to the new app:

1. Confirm the known current clients are old Retriever PrePress and the on-hold project.
2. Confirm old Retriever still owns token lifecycle.
3. Verify only one service has active `LordTate` PrintSmith REST credentials.
4. Verify all non-authority clients borrow tokens from the authority.
5. Verify old proxy key storage and rotation status.
6. Verify new Retriever health reports token authority ready/degraded.
7. Verify wrong proxy key returns `401`.
8. Verify valid proxy key returns `200` with the expected shape.
9. Verify invalidate returns `200` and a fresh token.
10. Verify upstream PrintSmith failure returns `502` or a documented equivalent.
11. Verify tokens and proxy keys are redacted from logs.
12. Verify rollback returns clients to the previous authority path.

## Verification Commands To Preserve Later

Use redacted examples in docs and scripts:

```bash
curl -sS -H "X-Token-Proxy-Key: <redacted>" \
  https://<authority-host>/api/printsmith-token
```

```bash
curl -sS -X POST -H "X-Token-Proxy-Key: <redacted>" \
  https://<authority-host>/api/printsmith-token/invalidate
```

Expected:

- no key: `401`
- valid key: `200`
- invalidation with valid key: `200`
- upstream PrintSmith unavailable: `502` or equivalent documented upstream-failure response

## Open Questions

- What hostname should new Retriever use to call the old proxy during staging?
- Should the future contract keep shared-header auth or move to bearer plus HMAC like the broker?
- Where should token authority audit events live for first launch?
- Who is allowed to rotate `PRINTSMITH_TOKEN_PROXY_KEY`?
- What exact event marks new Retriever PrePress ready to become the primary PrintSmith token authority?
