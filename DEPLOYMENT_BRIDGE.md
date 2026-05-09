# Deployment Bridge

**Status:** planning document  
**Scope:** how new Retriever code moves from OpenClaw/GitHub to the Boone production runtime  
**Security source:** [Cursor Security](https://cursor.com/security)

## Plain-English Summary

Cursor is part of the workshop, not part of the machine employees use.

Cursor can help write, review, and organize the new Retriever. It should not hold production secrets, run production Retriever, bypass Boone approvals, or directly touch live PrintSmith/Switch/DSF systems.

The production Retriever should run on a Boone-controlled runtime, likely a Boone LAN server exposed through Cloudflare Access/Tunnel. Cursor should feed that runtime through reviewed code, commits, deployment scripts, and documented handoffs.

## Production runtime today (Windows)

Live production for the rebuild is **Windows Server** on **`bggol-vesko01`**, not the Linux **`systemd`** layout in the reference section below.

| Item | Value |
|---|---|
| Host | `bggol-vesko01` |
| Public URL | `https://retriever.boonegraphics.net` (Cloudflare Access + Tunnel to `127.0.0.1:8810`) |
| New Retriever | Windows service **RetrieverRebuild** (NSSM), `127.0.0.1:8810` |
| Legacy Retriever | Windows service **Retriever** on port **8000** (PrePress, DSF, PrintSmith token authority until cutover) |
| Deploy + Fetch foundation | **`deploy/WINDOWS_FETCH_RELEASE.md`**: migration **`0002`**, **`smoke.ps1`**, **`FETCH_ENABLED=false`** recommended until deliberate enablement—see runbook for the validation quirk (stub vs required model env vars) |

Plain English: operators follow **PowerShell/NSSM** procedures on the **`D:\retriever-rebuild\`** layout; do not assume **`/opt`**, **bash deploy**, or **`systemd`** on this host.

## Reference: Linux sibling-VM runtime plan (deferred)

The table below describes an **original** Linux-oriented shape (e.g. **`bggol-retriever01`**, **`retriever-web.service`**, **`retriever-next.boonegraphics.net`**) for a possible **future** sibling VM. It is **not** the active production path for **`bggol-vesko01`**. First live hostname is **`retriever.boonegraphics.net`**; a dedicated staging subdomain was deferred per **`PLAN.md`**.

| Dimension | Reference plan (Linux sibling VM) |
|---|---|
| Production runtime | Boone LAN Linux server or VM, not OpenClaw and not Cursor Cloud. |
| Host candidate | Sibling Boone LAN app VM (working name `bggol-retriever01` in older docs); not the current Windows host above. |
| Public entry | Cloudflare Access + Cloudflare Tunnel. |
| First test hostname | `retriever-next.boonegraphics.net` (historical; production launched on `retriever.boonegraphics.net` from first deploy). |
| App bind address | `127.0.0.1` only, behind tunnel/reverse proxy. |
| First app port | `8810` for new Retriever. |
| Service user | `retriever`. |
| Service name | `retriever-web.service`. |
| Deploy model | Server-pull from GitHub by a Boone-side deploy script. |
| Secrets | Boone server env file or approved Boone-controlled vault, never committed. |
| Rollback | Previous release symlink plus systemd restart. |
| Old Retriever | Remains live/reference until explicit module cutover. |

Plain English: new Retriever should first live beside old Retriever, not replace it. Employees should not discover half-built modules through the production hostname.

## Cursor's Role

Allowed:

- write and edit Retriever source code
- create architecture and deployment documents
- run local tests and read-only verification
- prepare commits and pull requests when requested
- inspect non-secret logs and sanitized examples
- help build deployment scripts that run on the Boone side

Not allowed:

- store production credentials
- directly deploy to production without an explicit deployment step
- call production write APIs as an agent convenience
- become the scheduled report runtime
- become the only place where deployment knowledge exists
- hold the sole copy of rollback or recovery instructions

## Security Posture From Cursor

Cursor's security page names useful controls for our build chain:

- Privacy Mode, including contractual and technical controls such as zero data retention terms with model providers
- model blocklist support
- least-privilege infrastructure access and MFA on Cursor's side
- SOC 2 Type II report availability
- annual third-party penetration testing
- published subprocessors and vendor risk review
- documented agent, MCP, hooks, cloud-agent, and data-governance security guidance

These controls improve confidence in the development environment. They do not replace Retriever's own Cloudflare Access, LAN isolation, service credentials, audit logs, health checks, or rollback plan.

## Deployment Boundary

The deploy bridge should have a hard line:

```text
Cursor/OpenClaw -> reviewed code -> GitHub/release point -> Boone deploy script -> Boone runtime
```

Do not use:

```text
Cursor agent -> live production secret -> direct production mutation
```

Production deployment should be a deliberate operation with:

- known source revision
- deploy operator
- server-side script or workflow
- pre-deploy checks
- post-deploy smoke tests
- `/version` endpoint check
- rollback command
- log location
- health endpoint check

## Filesystem Layout

Recommended Boone server layout:

```text
/opt/retriever-rebuild/
  repo/                 # bare or normal Git checkout used by deploy scripts
  releases/
    <git-sha>/          # immutable release directories
  current -> releases/<git-sha>
  previous -> releases/<prior-sha>
  shared/
    uploads/            # runtime uploads if local disk is used
    reports/            # generated delayed-report artifacts if local disk is used
    tmp/
  bin/
    deploy.sh
    rollback.sh
    smoke.sh
    healthcheck.sh

/etc/retriever-rebuild/
  retriever.env         # production env, mode 0640, root:retriever

/var/log/retriever-rebuild/
  app.log
  audit.jsonl
  deploy.log
```

Rules:

- `releases/<git-sha>/` is immutable after deploy.
- `current` is the only path systemd starts.
- `previous` points to the last known-good release.
- runtime data lives in `shared/`, not inside release directories.
- production env files live outside Git.
- logs must not contain bearer tokens, HMAC secrets, cookie values, or raw customer-upload text.

## Service Model

Recommended service:

```text
retriever-web.service
```

Expected behavior:

- runs as the `retriever` service user
- reads environment from `/etc/retriever-rebuild/retriever.env`
- starts the app from `/opt/retriever-rebuild/current`
- binds to `127.0.0.1:8810`
- restarts on ordinary process failure
- does not run as `root`
- does not have write access to deployment scripts

Systemd should be the process owner. Cursor, OpenClaw, and ad hoc shells should not be the production process owner.

## Server-Pull Deploy

First deployment model: a human or approved automation logs into the Boone server and runs a Boone-side deploy script with an explicit Git ref.

*Note: Automated CI/CD (pushing to a staging site, running tests, and promoting to main) is a confirmed Phase 2 goal. We are using manual server-pull first to prove the basic Windows NSSM service stability, but the end goal is a fully automated push pipeline.*

Recommended command:

```bash
sudo /opt/retriever-rebuild/bin/deploy.sh <git-ref-or-sha>
```

Example:

```bash
sudo /opt/retriever-rebuild/bin/deploy.sh main
```

The deploy script should:

1. acquire a deploy lock
2. record operator, timestamp, current version, and requested ref
3. fetch from GitHub
4. resolve the requested ref to a full commit SHA
5. create `/opt/retriever-rebuild/releases/<sha>`
6. check out source into that release directory
7. install dependencies reproducibly
8. run build/type checks
9. run unit tests or the available fast test suite
10. validate production config without printing secrets
11. run database migrations only when explicitly approved for that release class
12. update `previous` to the old `current`
13. atomically update `current` to the new release
14. restart `retriever-web.service`
15. run local health checks
16. run smoke tests through the public Cloudflare path if possible
17. write deploy result to `/var/log/retriever-rebuild/deploy.log`

If any pre-restart step fails, do not change `current`.

If post-restart health or smoke tests fail, rollback automatically unless the operator explicitly chooses to hold the failed release for debugging.

## Rollback

Recommended command:

```bash
sudo /opt/retriever-rebuild/bin/rollback.sh
```

Rollback should:

1. confirm `previous` exists
2. swap `current` and `previous`
3. restart `retriever-web.service`
4. run local health check
5. run smoke test
6. record old version, restored version, operator, timestamp, and reason

Rollback should not require Cursor, GitHub, or package installation. It should use the already-present previous release on disk.

Emergency manual rollback shape:

```bash
sudo systemctl stop retriever-web
sudo ln -sfn /opt/retriever-rebuild/releases/<known-good-sha> /opt/retriever-rebuild/current
sudo systemctl start retriever-web
sudo /opt/retriever-rebuild/bin/healthcheck.sh
```

The manual path is a fallback, not the normal operating procedure.

## Version Endpoint

New Retriever should expose:

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
  "environment": "production",
  "host": "<boone-hostname>"
}
```

Do not include secrets, raw env values, database URLs, or internal credentials.

## Health Checks

Use three levels:

| Endpoint | Purpose | Public? |
|---|---|---|
| `GET /health/live` | process is alive | safe through Cloudflare |
| `GET /health/ready` | app can serve normal Fetch/auth traffic | safe through Cloudflare for admins/service checks |
| `GET /health/deep` | dependency detail for admin/operator troubleshooting | admin only |

`/health/ready` should check:

- app process
- config loaded
- auth/session config present
- app database connection
- Fetch storage/retrieval dependency if enabled
- model provider configured
- `/printsmith` route readiness if enabled
- `/docs` route readiness if enabled
- BooneOps broker readiness if enabled
- report job queue or delayed-report path if enabled

`/health/deep` can include:

- dependency names
- last check timestamp
- degraded components
- request IDs
- version
- broker route status
- Cloudflare identity validation mode
- Tailscale broker reachability

`/health/deep` must not expose secret values, auth headers, database URLs, raw prompts, customer-upload text, or bearer-token fragments.

## Smoke Tests

**Windows production (`bggol-vesko01`, `RetrieverRebuild`):** run **`D:\retriever-rebuild\bin\smoke.ps1`** as documented in **`deploy/WINDOWS_FETCH_RELEASE.md`**. That script is the gate for Fetch foundation deploys (including expectations that **`fetch`** and **`modelProvider`** stay **`disabled`** while **`FETCH_ENABLED=false`**).

Recommended command for a **Linux reference** host or local developer habit:

```bash
sudo /opt/retriever-rebuild/bin/smoke.sh
```

Minimum smoke checks:

1. `GET http://127.0.0.1:8810/health/live`
2. `GET http://127.0.0.1:8810/health/ready`
3. `GET http://127.0.0.1:8810/version`
4. Cloudflare public hostname returns Access challenge or valid service-token response
5. pending-user flow does not expose Fetch to unapproved users
6. seeded admin account can load the app shell
7. Fetch route is hidden or disabled until Fetch is intentionally enabled
8. `/printsmith` health is reported as ready/degraded, not silently ignored
9. `/docs` health is reported as ready/degraded, not silently ignored
10. BooneOps broker health is reported as ready/degraded, including Tailscale reachability when relevant

For early staging, public-path smoke checks can use:

```text
https://retriever-next.boonegraphics.net/version
https://retriever-next.boonegraphics.net/health/live
```

If Cloudflare Access blocks anonymous checks, use a Cloudflare Access service token stored on the Boone server, not in Cursor.

## Log Access

Operational logs:

```bash
sudo journalctl -u retriever-web -n 200 --no-pager
sudo journalctl -u retriever-web -f
```

Deploy log:

```text
/var/log/retriever-rebuild/deploy.log
```

Audit log starting point:

```text
/var/log/retriever-rebuild/audit.jsonl
```

Access policy:

- Master Tate can read all logs.
- A future limited operator can read sanitized app/deploy logs.
- Raw audit logs with customer or employee metadata should not be broadly readable.
- Cursor may inspect sanitized logs by default.
- Cursor may inspect raw production logs only with explicit approval for a specific debugging task.

## Cloudflare Access And Tunnel

Cloudflare should protect the public hostname. The Boone server should not accept direct public traffic.

First path:

```text
retriever-next.boonegraphics.net -> Cloudflare Access -> Cloudflare Tunnel -> 127.0.0.1:8810
```

Cutover path:

```text
retriever.boonegraphics.net -> Cloudflare Access -> Cloudflare Tunnel -> new Retriever
```

Only after old/new coexistence and token authority are solved should the production hostname move.

Identity rule:

- Retriever should validate Cloudflare Access identity explicitly where practical.
- If any route trusts Cloudflare headers, direct LAN access that can spoof those headers must be blocked.
- The app should record the Cloudflare identity and the local Retriever profile used for authorization.

Tunnel credentials live with Cloudflare/system configuration on the Boone server, not in the app repo and not in Cursor.

## Tailscale Runtime Role

Tailscale is a runtime dependency if the new Retriever still calls the existing BooneOps broker over Tailscale.

First rule:

- Treat BooneOps broker reachability as part of `/health/ready` or a clearly visible degraded state.
- Do not describe Tailscale as only an admin path while Fetch depends on it.

Required before launch:

- identify the broker hostname or tailnet address
- define ACLs so only the Retriever service host can call the broker route it needs
- verify broker bearer/HMAC auth still applies over Tailscale
- log broker unavailable separately from model failure
- make delayed reports degrade cleanly if broker/report worker is unreachable

If BooneOps broker later moves into the new Retriever runtime, update this document and `WEBHOOK_AND_BROKER_AUTH.md`.

## Required Deployment Artifacts

**`bggol-vesko01` (current production):** Windows paths and **`RetrieverRebuild`** / **`smoke.ps1`** — see **`deploy/WINDOWS_FETCH_RELEASE.md`**, **`deploy/deploy.ps1`**, and **`D:\retriever-rebuild\env\retriever.env`**. Ignore the **`/opt`** / **`systemd`** list items below for this host.

**Linux sibling VM (if used later):** keep the checklist below.

Before production build-out, define:

- production host or VM: **`bggol-vesko01` (Windows, active)** or a sibling Boone LAN Linux app VM
- service name: **`RetrieverRebuild` (Windows)** or **`retriever-web.service` (Linux reference)**
- filesystem layout: **`D:\retriever-rebuild\` (Windows)** or **`/opt/retriever-rebuild` (Linux reference)**, **`/etc/retriever-rebuild`**, **`/var/log/retriever-rebuild`**
- environment file location: **`D:\retriever-rebuild\env\retriever.env` (Windows)** or **`/etc/retriever-rebuild/retriever.env` (Linux)**
- secret source: Boone-controlled env file or approved vault, not Cursor
- deploy script: **`deploy.ps1` (Windows)** or **`/opt/retriever-rebuild/bin/deploy.sh` (Linux reference)**
- rollback script: **`rollback.ps1` (Windows)** or **`/opt/retriever-rebuild/bin/rollback.sh` (Linux reference)**
- health endpoints: `/health/live`, `/health/ready`, `/health/deep`
- version endpoint: `/version`
- smoke test command: **`smoke.ps1` (Windows)** or **`/opt/retriever-rebuild/bin/smoke.sh` (Linux/local)**
- log path: **Windows service logs / NSSM** (see VM notes) or `journalctl -u retriever-web`, `/var/log/retriever-rebuild/deploy.log`, `/var/log/retriever-rebuild/audit.jsonl`
- Cloudflare Tunnel routing: **`retriever.boonegraphics.net`** to **`127.0.0.1:8810`** (staging subdomain optional/deferred)
- Tailscale role: runtime path for BooneOps broker until broker moves
- old/new Retriever coexistence path: separate hostname plus module gates until cutover

## Cursor-Specific Deployment Rules

- Cursor may generate `.env.example`, never real `.env.production`.
- Cursor may write deployment scripts, but Boone production runs them.
- Cursor may inspect sanitized logs, not raw logs containing secrets or customer payloads unless explicitly approved.
- Cursor-authored changes should land as commits, not invisible manual edits.
- Any production deployment initiated from an agent session must still leave a verifiable artifact: commit hash, deploy output, version endpoint, and rollback point.
- Cursor MCP/dev credentials must not be reused as Retriever production service credentials.

## Old And New Retriever Coexistence

Old Retriever remains the current LAN reference and live runtime until a specific module is proven in the rebuild.

First coexistence plan:

- old Retriever stays **LAN-only** on port **8000** (no Cloudflare hostname); new Retriever uses **`retriever.boonegraphics.net`**
- new Retriever is **`RetrieverRebuild`** on **`bggol-vesko01:8810`**, not a Linux staging host by default
- Cloudflare Access protects the public Retriever hostname
- new Retriever exposes only rebuilt modules
- unfinished modules show no sidebar entry and no public route
- PrePress stays on old Retriever
- DSF write actions stay on old Retriever until LAN action-service design is proven
- old Fetch conversations and private library data do not migrate during the first deployment bridge
- `MIGRATION_PLAN.md` decides old Fetch data migration before employee cutover
- `PRINTSMITH_TOKEN_AUTHORITY.md` decides token ownership before production hostname cutover

Cutover gates:

1. Cloudflare identity binding proven
2. pending-user/admin approval flow proven
3. Fetch trust behavior proven, including delayed reports
4. `/version`, `/health/ready`, and smoke tests green
5. rollback tested
6. secrets stored on Boone runtime
7. audit logging records required auth/Fetch events
8. PrintSmith token authority preserved or intentionally replaced
9. old/new user communication ready

## Deployment Records

Every deploy should leave a short record:

```text
deployedAt: <iso timestamp>
operator: <person or automation>
gitSha: <full sha>
gitRef: <ref>
previousSha: <full sha>
host: <boone host>
service: RetrieverRebuild (Windows) or retriever-web.service (Linux reference)
healthReady: pass/fail
smoke: pass/fail
rollbackPoint: <previous sha>
notes: <short plain-English note>
```

This can start as a **deploy log** on the server (Windows: alongside **`D:\retriever-rebuild\` operations**; Linux reference: **`/var/log/retriever-rebuild/deploy.log`**). Later it can move into a deployment table or release dashboard.

## Open Questions

- Is `bggol-vesko01` the right first host, or should Boone create a sibling app VM?
- Who can read production logs?
- How does deployment prove Cloudflare Access headers cannot be spoofed through direct LAN access?
- Does BooneOps remain behind Tailscale, or move into the new Retriever runtime later?
- Which database will store app and audit state for first launch?
- Will old Fetch data migrate at cutover or remain read-only/archive-only?
