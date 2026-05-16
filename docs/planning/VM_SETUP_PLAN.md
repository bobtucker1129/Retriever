# VM Setup Plan

> **Production path today:** new Retriever first shipped beside old Retriever on **Windows `bggol-vesko01`** (see `../deploy/VM_SETUP_RUNBOOK.md` and `../deploy/WINDOWS_FETCH_RELEASE.md`). This file remains the **Linux-first** alternate plan (`bggol-retriever01`) if you later split onto a dedicated app VM.

**Status:** planning document  
**Scope:** first Boone LAN app VM for new Retriever  
**Inputs:** `RUNTIME_NOTES.md`, `DEPLOYMENT_BRIDGE.md`, `SECRETS_HANDLING.md`, `PRINTSMITH_TOKEN_AUTHORITY.md`

## Plain-English Summary

Build new Retriever on its own Boone LAN Linux VM so it can prove itself beside old Retriever without risking the current production box.

Working name: `bggol-retriever01`.

`retriever-next.boonegraphics.net` points to this VM during staging. After the cutover gates pass, `retriever.boonegraphics.net` becomes the public hostname for this same new app.

## Host Decision

Use a sibling Boone LAN Linux app VM, not `bggol-vesko01`, for the first new Retriever runtime.

Recommended host identity:

| Dimension | Decision |
|---|---|
| VM name | `bggol-retriever01` |
| Role | New Retriever app host |
| Environment | Boone LAN |
| OS | Current Ubuntu LTS or Debian stable |
| Process manager | systemd |
| Service name | `retriever-web.service` |
| App user | `retriever` |
| Local bind | `127.0.0.1:8810` |
| Staging hostname | `retriever-next.boonegraphics.net` |
| Final hostname | `retriever.boonegraphics.net` after cutover |

If Boone IT has a required naming pattern, use that pattern. The important part is that the host is clearly the first new Retriever app VM and is not confused with old Retriever.

## Ownership

Plain English split:

- Boone infrastructure owner provisions the VM, network, DNS, backup, base OS, and remote access.
- Master Tate owns the Retriever app decisions, release gates, secrets approval, and cutover decision.
- The `retriever` service account owns the running app, not a human shell account.
- Cursor/OpenClaw can prepare scripts and docs, but production deployment runs on the Boone side.

## Required Base Setup

The VM should have:

- static Boone LAN IP or stable internal DNS
- outbound HTTPS to GitHub or the chosen release source
- outbound HTTPS to model providers when Fetch is enabled
- access to the Boone MySQL server for `retriever_core`
- Cloudflare Tunnel installed outside the app repo
- Tailscale installed if first Fetch launch uses the existing BooneOps broker/report path
- systemd
- log rotation
- time sync
- a dedicated `retriever` user and group
- SSH/admin access limited to approved operators

Recommended filesystem:

```text
/opt/retriever-rebuild/
  repo/
  releases/
  current -> releases/<git-sha>
  previous -> releases/<prior-sha>
  shared/
    uploads/
    reports/
    tmp/
  bin/
    deploy.sh
    rollback.sh
    smoke.sh
    healthcheck.sh

/etc/retriever-rebuild/
  retriever.env

/var/log/retriever-rebuild/
  app.log
  audit.jsonl
  deploy.log
```

## Network And Hostnames

Staging path:

```text
retriever-next.boonegraphics.net
  -> Cloudflare Access
  -> Cloudflare Tunnel
  -> bggol-retriever01:127.0.0.1:8810
```

Final path:

```text
retriever.boonegraphics.net
  -> Cloudflare Access
  -> Cloudflare Tunnel
  -> bggol-retriever01:127.0.0.1:8810
```

Rules:

- The app binds to localhost only.
- Cloudflare Access protects both staging and final hostnames.
- Direct LAN requests must not be able to spoof Cloudflare identity headers.
- Local health checks can use localhost.
- Public smoke checks should go through Cloudflare Access with an approved service token when needed.

## Tailscale Role

For first Fetch launch, assume Tailscale is required if Fetch keeps the current BooneOps broker/report behavior.

Required before enabling BooneOps-backed Fetch:

- install Tailscale on `bggol-retriever01`
- join the approved Boone tailnet
- restrict ACLs so the Retriever host can call only the broker/report routes it needs
- keep broker bearer/HMAC auth even over Tailscale
- include broker reachability in `/health/ready` or a visible degraded state

Later goal: move the broker/report path closer to Retriever so Tailscale is no longer a Fetch runtime dependency.

## MySQL Access

The VM needs a service database user with access to `retriever_core`.

Principle:

- new Retriever can read/write only its own app schema by default
- old business data remains in source systems
- `/printsmith` and future module integrations get separate, purpose-specific access

Recommended first DB grants:

```sql
CREATE DATABASE IF NOT EXISTS retriever_core
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE USER 'retriever_app'@'<bggol-retriever01-lan-host>' IDENTIFIED BY '<redacted>';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX
  ON retriever_core.* TO 'retriever_app'@'<bggol-retriever01-lan-host>';
```

Use narrower migration grants later if the app runtime should not be able to alter schema.

## Secrets On The Host

Production/staging secrets live in:

```text
/etc/retriever-rebuild/retriever.env
```

Rules:

- file mode `0640`
- owner `root`
- group `retriever`
- never committed
- never copied into Cursor by default
- redacted examples only in docs

Cloudflare Tunnel credentials live with Cloudflare/system configuration, not in the app repo.

## Deploy And Rollback

First deploy command:

```bash
sudo /opt/retriever-rebuild/bin/deploy.sh <git-ref-or-sha>
```

Rollback command:

```bash
sudo /opt/retriever-rebuild/bin/rollback.sh
```

The deploy script should:

1. acquire a deploy lock
2. record operator, timestamp, current version, and requested ref
3. fetch source
4. resolve full commit SHA
5. create immutable release directory
6. install dependencies reproducibly
7. run build/type checks
8. run tests or fast verification
9. validate config without printing secrets
10. run approved migrations
11. update `previous`
12. atomically update `current`
13. restart `retriever-web.service`
14. run local health check
15. run Cloudflare smoke check
16. write deploy record

Rollback must not require Cursor, GitHub, or package installation.

## Backup Expectations

Back up:

- `retriever_core` MySQL schema
- `/opt/retriever-rebuild/shared/uploads`
- `/opt/retriever-rebuild/shared/reports` if reports need retention
- `/etc/retriever-rebuild/retriever.env` through an approved secret backup process
- deploy records and audit logs according to retention policy

Do not rely on release directories as the only backup. Releases are rebuildable from Git; runtime state is not.

## First VM Acceptance Checklist

The VM is ready for app build when:

1. host exists as `bggol-retriever01` or approved equivalent
2. `retriever` OS user exists
3. `/opt/retriever-rebuild`, `/etc/retriever-rebuild`, and `/var/log/retriever-rebuild` exist with correct ownership
4. Cloudflare Tunnel reaches `127.0.0.1:8810`
5. `retriever-next.boonegraphics.net` shows Cloudflare Access challenge or approved service-token response
6. MySQL connection to `retriever_core` works from the VM
7. Tailscale broker path works if Fetch/BooneOps is enabled
8. systemd can start/stop `retriever-web.service`
9. deploy and rollback scripts exist, even if app release is still a stub
10. backup owner/process is identified

## Open Questions

- Does Boone IT require a different VM name than `bggol-retriever01`?
- Who provisions the VM and DNS/Tunnel records?
- Which backup job protects MySQL and `/opt/retriever-rebuild/shared`?
- Who besides Master Tate can SSH into the host?
- When does Tailscale become optional because broker/report work moved closer to Retriever?
