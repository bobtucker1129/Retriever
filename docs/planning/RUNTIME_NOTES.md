# Runtime Notes

**Status:** planning document  
**Scope:** first production-style runtime for new Retriever, before employee cutover  
**Inputs:** `DEPLOYMENT_BRIDGE.md`, `SECRETS_HANDLING.md`, `../archive/REVIEW-2026-05-04-OPUS.md`, `AUTH_REDESIGN.md`

## Plain-English Summary

New Retriever should first run beside old Retriever, not on top of it. The final public home is still `https://retriever.boonegraphics.net`.

The recommended first host is a sibling Boone LAN Linux app VM. `bggol-vesko01` should stay the live old Retriever host and PrintSmith token authority while the rebuild proves auth, Fetch, health checks, rollback, and token handoff.

This keeps the live production box stable and gives the rebuild the Linux/systemd layout already assumed by the deployment bridge. `retriever-next.boonegraphics.net` is only the side-by-side staging address before the public cutover.

## Host Decision

Decision: use a sibling Boone LAN Linux app VM as the first new Retriever runtime.

`bggol-vesko01` remains:

- old Retriever production host during staging
- source of truth for old module behavior
- current PrintSmith REST token authority
- fallback reference if new Retriever has to be paused

The sibling VM becomes:

- `retriever-next.boonegraphics.net` runtime
- Cloudflare Tunnel endpoint for staging
- systemd owner of `retriever-web.service`
- holder of new Retriever production/staging secrets
- place where deploy, rollback, health, smoke, and logs are exercised

Why this is better than using `bggol-vesko01` first:

- Old Retriever is still live and should not be destabilized by a rebuild runtime.
- The bridge plan assumes a Linux service model: `/opt`, `/etc`, `/var/log`, systemd, release symlinks, and server-pull deploy.
- Keeping old and new hosts separate makes rollback and comparison cleaner.
- The PrintSmith token cutover can be tested as a deliberate service handoff instead of an accidental shared-host side effect.
- Cloudflare and Tailscale routing can be tightened around one new service host.

Fallback: if a sibling VM cannot be provisioned quickly, `bggol-vesko01` can host a limited staging process only after the old Retriever service, ports, token proxy, NSSM/service ownership, logs, and rollback path are explicitly protected. That is a fallback, not the preferred first launch.

## First Runtime Shape

| Dimension | Decision |
|---|---|
| Runtime host | New sibling Boone LAN Linux app VM |
| Old host role | `bggol-vesko01` stays old Retriever and PrintSmith token authority |
| First hostname | `retriever-next.boonegraphics.net` for staging |
| Cutover hostname | `retriever.boonegraphics.net` as the final live Retriever home, only after gates pass |
| Public path | Cloudflare Access + Cloudflare Tunnel |
| App bind | `127.0.0.1:8810` |
| Service owner | `retriever` OS user |
| Service | `retriever-web.service` |
| App root | `/opt/retriever-rebuild/current` |
| Env file | `/etc/retriever-rebuild/retriever.env` |
| Logs | `journalctl -u retriever-web`, `/var/log/retriever-rebuild/` |
| Deploy | Boone-side server-pull deploy script |
| Rollback | Previous release symlink plus service restart |

## Boone VM Requirements

The sibling VM should have:

- static Boone LAN identity and DNS name
- outbound access to GitHub or the chosen release source
- Cloudflare Tunnel installed and owned outside the app repo
- Tailscale installed if BooneOps broker calls still require it
- access only to the databases and services needed for enabled modules
- systemd available for `retriever-web.service`
- a dedicated `retriever` service account
- `/opt/retriever-rebuild`, `/etc/retriever-rebuild`, and `/var/log/retriever-rebuild`
- backup/restore expectations for runtime state, uploads, reports, and logs

Do not put production secrets in Git, Cursor, or project planning docs. The VM should read secrets from `/etc/retriever-rebuild/retriever.env` or another Boone-controlled vault approved before launch.

## Runtime Dependencies

Required for the first staging runtime:

- Cloudflare Access for the public front door
- Cloudflare Tunnel from `retriever-next.boonegraphics.net` to `127.0.0.1:8810`
- existing Boone MySQL server with a new `retriever_core` schema for users, roles, capabilities, sessions, settings, delayed-report state, and audit metadata
- model provider credentials for Fetch, if Fetch is enabled
- report/artifact storage for delayed reports
- log storage and rotation
- deploy scripts and rollback scripts on the Boone VM

Conditional dependencies:

- Tailscale, required for first Fetch launch if Fetch keeps BooneOps broker/report behavior over the existing tailnet path
- BooneOps broker bearer/HMAC credentials, if BooneOps Light or Medium is enabled
- `/printsmith` read-only service credentials, if live PrintSmith answers are enabled
- `/docs` index/storage, if vendor documentation answers are enabled
- PrintSmith token authority service, only after the token handoff plan is approved

Not first-launch dependencies:

- DSF write action service
- PrePress migration
- old Fetch conversation migration
- broad employee rollout
- production hostname cutover

## Identity And Network Rules

Cloudflare Access proves the person reached the front door. Retriever still owns business authorization.

First implementation should:

- validate Cloudflare Access identity explicitly where practical
- record Cloudflare identity and Retriever profile identity together
- deny pending, suspended, and blocked users before Fetch loads
- prevent direct LAN requests from spoofing Cloudflare identity headers
- expose direct local health checks only to localhost/admin paths

Plain English: a request should not become trusted just because it has a friendly-looking email header.

## Storage And Logs

Use the Boone VM filesystem for first deploy mechanics:

- immutable releases under `/opt/retriever-rebuild/releases/<git-sha>`
- runtime shared files under `/opt/retriever-rebuild/shared`
- production env outside Git at `/etc/retriever-rebuild/retriever.env`
- app/deploy/audit logs under `/var/log/retriever-rebuild`

For app state, use Boone MySQL before employee cutover. The current Retriever already uses `retriever_core`; the rebuild should extend that same schema carefully so auth, module access, and future module state stay in one app-state home.

Use `retriever_core` for:

- Cloudflare-linked user profiles
- pending/active/suspended/blocked user state
- roles and capabilities
- BooneOps level assignments
- sessions or session metadata, depending on framework choice
- app settings such as Fetch general-question policy
- delayed-report state
- audit metadata

Business data remains in its source systems. Retriever may cache metadata only when a document explicitly allows it.

## Health And Smoke Expectations

The new host is not ready until these work from the Boone VM:

- `GET http://127.0.0.1:8810/health/live`
- `GET http://127.0.0.1:8810/health/ready`
- `GET http://127.0.0.1:8810/version`
- public Cloudflare Access challenge or service-token check for `retriever-next.boonegraphics.net`
- pending-user flow blocks unapproved users
- seeded admin can load the app shell
- Fetch stays hidden or disabled until intentionally enabled
- `/printsmith`, `/docs`, and BooneOps dependencies report ready/degraded states instead of disappearing
- rollback restores the prior release without Cursor, GitHub install steps, or secret changes

## Cutover Gates

Do not move `retriever.boonegraphics.net` to the new runtime until:

1. sibling VM is stable under `retriever-next.boonegraphics.net`
2. Cloudflare identity binding is proven
3. pending-user/admin approval flow is proven
4. Fetch trust behavior is proven, including delayed reports
5. health, version, smoke, and rollback pass
6. secrets live on the Boone runtime, not in Cursor
7. audit logging records required auth, Fetch, report, and machine events
8. PrintSmith token authority is preserved or intentionally replaced
9. old/new user communication is ready
10. old modules that are not rebuilt remain hidden from the new app

## Open Questions

- Does Boone IT accept `bggol-retriever01`, or require another VM name?
- Who besides Master Tate can read sanitized runtime logs?
- How long should audit and Fetch metadata be retained?
- Does BooneOps broker move closer to Retriever later, after first Fetch launch?
- Which backup job protects `/opt/retriever-rebuild/shared` and app state?
