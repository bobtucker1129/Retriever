# Opus Review: Retriever Rebuild Planning

**Date:** 2026-05-04  
**Reviewer:** Opus 4.7, read-only senior-engineer review  
**Scope:** `projects/retriever-rebuild/`, project rule, project index, and old `projects/Retriever/` reference where needed

## Bottom Line

The current rebuild plan has a strong auth and capability spine, but it is thin around production engineering. Before code starts, the project needs explicit plans for deployment, secrets, audit logs, runtime hosting, PrintSmith token authority, webhook and broker auth, and Fetch's heavy-query failure behavior.

Fetch remains the trust barrier. The old Fetch-to-BooneOps integration was real and partially working, but its major weakness was heavy PrintSmith/DSF list queries timing out instead of turning into stable delayed reports.

## What Is Strong

- `AUTH_REDESIGN.md` correctly separates Cloudflare identity from Retriever business authorization.
- The role, module access, capability, and BooneOps level split fixes a major problem in the current app.
- The module/action matrix is useful and should survive into implementation.
- The project correctly treats Fetch as the first trust barrier.
- The old `projects/Retriever/` copy is clearly marked as reference-only.
- BooneOps Full and Shipping Chat have been removed from Retriever scope.
- `/printsmith`, `/docs`, and `/printsmith-estimate` boundaries are now mostly clear.

## Material Gaps To Fix

### P0: Deployment Bridge

The project does not yet define how code moves from OpenClaw/GitHub to the Boone server. The deployment plan needs to specify the server-side deploy script, rollback, health checks, version endpoint, smoke tests, Cloudflare Tunnel setup, Tailscale access, and log access.

### P0: PrintSmith Token Authority

Old Retriever is the sole `LordTate` PrintSmith REST token authority. It exposes `/api/printsmith-token` and `/api/printsmith-token/invalidate` so other systems can borrow the shared token without stomping each other. This must be preserved or intentionally replaced before cutover.

### P0: Cloudflare Identity Binding

The plan says Cloudflare proves identity, but it does not yet say how Retriever validates that identity. The new app must either validate the Cloudflare Access JWT or be protected so only Cloudflare can reach it. Direct LAN access that can spoof Cloudflare headers must be blocked.

### P0: Tailscale As Runtime Data Path

Tailscale is not only an admin path today. Current Fetch uses Tailscale to call the BooneOps broker. The rebuild must treat Tailscale as a runtime dependency for BooneOps unless the broker moves into the new Retriever runtime.

### P0: Fetch Heavy-Query Timeout

The old logs show rich PrintSmith/DSF list queries timing out around the broker/gateway boundary. The Fetch trust plan needs a clear synchronous limit and delayed-report path. Heavy reports should not wait until timeout and then fail in chat.

### P1: Secrets Handling

The rebuild needs a secrets inventory and storage plan. Known secrets include Cloudflare Access/Tunnel credentials, cookie/session keys, BooneOps broker bearer token, broker HMAC signing secret, Switch webhook secret, PrintSmith token proxy key, PrintSmith REST credentials, MIS Postgres credentials, MySQL credentials, Switch API credentials, Anthropic key, Vertex credentials, and web-search keys.

### P1: Audit Log Design

`AUTH_REDESIGN.md` names audit tiers but does not define schema, storage, retention, redaction, tamper evidence, or who can read logs. This matters for HIPAA/SOC2 posture.

### P1: Webhook And Broker Auth

Switch review webhook auth is currently a shared header secret. BooneOps broker auth uses bearer plus HMAC. PrintSmith token proxy uses its own shared key. The rebuild needs one machine-to-machine auth design that covers all of these.

### P1: PrePress Operator Binding

Current PrePress normalizes local username/full name to a canonical PrePress operator. Cloudflare email identity can break this silently. PrePress cannot move until that mapping is proven.

### P1: Inventory Role Migration

Inventory manager access is hardcoded today for `admin`, `project_manager`, and `sales`. The rebuild needs a role-to-capability seed or current inventory users will lose write access at cutover.

### P1: Dev Backdoors Must Not Ship

Old Retriever has development paths that synthesize an admin user, auto-create `admin/admin123`, and fall back to an insecure default cookie secret. The rebuild must hard-fail in production when required config is missing.

## Inconsistencies To Resolve

- Same-hostname cutover is not defined. Old and new Retriever may both need to exist while `retriever.boonegraphics.net` points somewhere.
- OpenClaw is described as not being runtime, but scheduled reports inside Retriever may still depend on the OpenClaw broker unless we redesign that path.
- The docs say to prefer explicit routing, but some language still resembles the old keyword-regex router.
- The kickoff rule did not originally load active architecture artifacts; this should be fixed so future sessions do not lose `AUTH_REDESIGN.md` and `FETCH_TRUST_PLAN.md`.
- Standalone Shipping Chat is removed, but DSF scoped invoice chat remains. Future docs should name that distinction clearly.

## Missing Artifacts

Recommended order:

1. `FETCH_TRUST_PLAN.md`
2. `DEPLOYMENT_BRIDGE.md`
3. `RUNTIME_NOTES.md`
4. `SECRETS_HANDLING.md`
5. `AUDIT_LOG_DESIGN.md`
6. `MIGRATION_PLAN.md`
7. `PRINTSMITH_TOKEN_AUTHORITY.md`
8. `WEBHOOK_AND_BROKER_AUTH.md`
9. `BUILD_CODE_LAYOUT.md`

## Fetch Trust Plan Requirements

The next artifact should include:

- explicit routing for local Fetch, `/printsmith`, `/docs`, BooneOps Light/Medium, uploads, email cleanup, and general-world questions
- a synchronous response limit for chat turns
- a delayed-report path for slow PrintSmith/DSF list or export requests
- inline failure states for broker unavailable, auth rejected, model failure, tool timeout, and delayed report pending
- filtering of transient broker failure messages from retry context
- a BooneOps Light/Medium to broker-bot mapping decision
- per-feature capabilities for preserved Fetch features
- upload privacy and data-retention rules
- general-world LLM privacy guardrails
- Fetch health checks that report tool and broker readiness, not just process uptime

## Open Questions Before Code

1. Which Boone server or VM will run new Retriever?
2. How will old and new Retriever coexist during cutover?
3. Will Retriever validate Cloudflare Access JWTs, or enforce tunnel-only access and trust headers?
4. Does BooneOps Medium map to the old `booneops.super` broker, or does the broker contract change?
5. Where will audit logs live?
6. Where will production secrets live?
7. Will deploys be server-pull from GitHub, CI-push, or triggered remotely from OpenClaw?
8. What is the rollback path for a failed deploy?
9. How will old Fetch conversations and private library data migrate?
10. How will uploaded customer files be kept out of outside-world LLM prompts?
11. What provider data-retention policy is acceptable for general Fetch answers?
12. How is PrintSmith token proxy preserved on day one?
13. How will PrePress stay on old Retriever during transition?
14. Is emergency local admin login removed, LAN-only, or disabled by default?

## Build Engineer Watch List

- HIPAA/SOC2 posture for customer files and prompts
- file handling boundaries between Fetch uploads, proof files, and job folders
- audit hygiene and tamper resistance
- deploy hygiene, smoke tests, and `/version`
- monitoring/log access for someone other than Master Tate
- secret rotation
- Tailscale dependency for BooneOps
- heavy-query delayed report behavior
- concurrent PrintSmith writes from desktop users and DSF actions
- removal of dev backdoors
- PrePress operator binding
- inventory role-to-capability seed
- DSF business constants migration
- project context preservation across kickoff/wrap

