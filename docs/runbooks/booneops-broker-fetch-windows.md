# BooneOps broker — Windows Fetch integration (disabled by default)

**Host:** `bggol-vesko01` only  
**Audience:** operators wiring **RetrieverRebuild** Fetch to the OpenClaw-hosted BooneOps broker over Tailscale  
**Companion:** `deploy/WINDOWS_FETCH_RELEASE.md`

## Plain-English goal

Retriever Fetch should behave like **Discord `#printsmith` via the BooneOps broker**: when the broker is **on** in Fetch configuration and Fetch **ask** is enabled, employee questions follow the Phase 1 BooneOps contract (`projects/booneops-bots/FETCH_HANDOFF.md`, `projects/booneops-bots/BROKER.md`).  

**Broad internet / general-purpose LLM** is a separate lane and stays **off** here: leave **`FETCH_GENERAL_QUESTIONS_ENABLED=false`** until a deliberate per-account policy uses capability **`fetch.ask_general`** plus admin toggles (`FETCH_TRUST_PLAN.md`). Internal PrintSmith-like traffic goes to the broker **only** when **`BOONEOPS_BROKER_ENABLED=true`** **and** the ask path is allowed (**active Fetch access**, **`FETCH_ENABLED=true`**, etc.—see Windows fetch release notes).

### Identity / persona (pilot)

Live pilot expectation: **Retriever Fetch** speaks as **BooneOps**—the **employee-facing** Boone operations helper—not **private LordTate**. If replies sound like the wrong audience or route oddly, **verify broker persona and routing** on the OpenClaw/broker side against `FETCH_TRUST_PLAN.md` (pilot findings).

Store production values only in **`D:\retriever-rebuild\env\retriever.env`**. Do **not** paste secrets into tickets or chat.

## Coexistence (do not regress legacy Retriever)

- **RetrieverRebuild** binds **`127.0.0.1:8810`** (Cloudflare Tunnel to this port).
- **Legacy Retriever** service stays on port **8000** for PrePress, DSF, and PrintSmith token authority until cutover docs say otherwise.
- Broker work must **not** stop, reinstall, or retarget the legacy **Retriever** service.

## Canonical environment variables — Retriever Fetch

These map to **`AppSettings`** (`app/config.py`). When **`BOONEOPS_BROKER_ENABLED=true`**, startup validation requires URL, bearer token, and HMAC secret to be non-empty.

| Env variable | Purpose |
|---|---|
| **`BOONEOPS_BROKER_ENABLED`** | **`false`** (recommended until smoke + enablement checklist). **`true`** when Fetch is cleared to send BooneOps broker traffic. |
| **`BOONEOPS_BROKER_URL`** | Base URL of the OpenClaw broker (Tailscale hostname or Tailscale IP), **no trailing slash**. Example shape: `http://<tailscale-host>:3487`. |
| **`BOONEOPS_BROKER_BEARER_TOKEN`** | Sent as **`Authorization: Bearer …`** on broker requests. Must match broker-side **`BOONEOPS_BROKER_TOKEN`** (see below). |
| **`BOONEOPS_BROKER_HMAC_SECRET`** | Shared secret used to compute **`X-BooneOps-Signature: sha256=<hex>`** over the raw JSON body. Must match broker-side **`BOONEOPS_BROKER_SIGNING_SECRET`**. |
| **`BOONEOPS_BROKER_REQUIRES_TAILSCALE`** | When **`true`** (default), health metadata marks Tailscale-related readiness as **`degraded`** (see health caveat below). Adjust only if Boone changes the networking contract. |

### Related gates (already in **`AppSettings` / `.env.example`**)

| Env variable | Keep off for this phase |
|---|---|
| **`FETCH_GENERAL_QUESTIONS_ENABLED`** | **`false`** — general outside-world answers stay off until a later per-user admin + **`fetch.ask_general`** design. Does **not** block broker-only `#printsmith`-style routing. |
| **`FETCH_ENABLED`** | **`false`** in production until you intentionally unlock the composer and accept model-validation rules in **`deploy/WINDOWS_FETCH_RELEASE.md`**; broker traffic only applies once ask is actually allowed. |

## OpenClaw broker side — matching names (`projects/booneops-bots/BROKER.md`)

The broker process expects:

- **`BOONEOPS_BROKER_TOKEN`** — verifies the **`Bearer`** token Fetch sends.
- **`BOONEOPS_BROKER_SIGNING_SECRET`** — verifies the body signature Fetch sends.

**Operator alignment:** Fetch **`BOONEOPS_BROKER_BEARER_TOKEN`** ↔ broker **`BOONEOPS_BROKER_TOKEN`**. Fetch **`BOONEOPS_BROKER_HMAC_SECRET`** ↔ broker **`BOONEOPS_BROKER_SIGNING_SECRET`**.

## Health and smoke endpoints

### RetrieverRebuild (local to the VM)

After deploy/restart:

- **`GET http://127.0.0.1:8810/health/live`** — process alive.
- **`GET http://127.0.0.1:8810/health/ready`** — aggregates configured checks.

**Important:** Today, when **`BOONEOPS_BROKER_ENABLED=true`**, **`checks.booneopsBroker`** reports **`degraded`** as a configured-on placeholder, **not** proof of an outbound TCP/socket check to the broker. Use the broker **`GET /health`** step below for real upstream readiness.

### OpenClaw BooneOps broker (over Tailscale from `bggol-vesko01`)

Per **`FETCH_HANDOFF.md`** and **`BROKER.md`**:

- **`GET /health`** on the broker base URL (e.g. `http://<broker-host>:3487/health`).
- **`POST /v1/booneops/message`** — message lane (requires auth headers when exercised from tools).
- Other paths — artifacts and conversation reports — are documented in **`FETCH_HANDOFF.md`**.

Treat broker **`GET /health`** returning **HTTP 200** from the Windows host as the **pre-enablement smoke** that Tailscale routing and broker uptime are sane.

### Auth smoke (optional, without enabling Fetch routing)

Only after Boone approves probing the authenticated message lane: a minimal **`POST`** to **`/v1/booneops/message`** with **`Authorization`** and **`X-BooneOps-Signature`** can distinguish **401** (bad token/signature) from **502** (upstream). Prefer coordination with whoever owns broker logs.

## PowerShell verification — `bggol-vesko01`

Run **elevated PowerShell** when your runbook requires service control.

### 1) Edit env file (secrets stay on disk)

Placeholders only below—substitute values from Boone without pasting secrets into shell history if possible (`notepad` is fine).

Ensure **`D:\retriever-rebuild\env\retriever.env`** eventually contains the broker keys you intend to use, but keep integration **off** for the first pass:

```text
BOONEOPS_BROKER_ENABLED=false
BOONEOPS_BROKER_URL=http://<tailscale-host-or-ip>:3487
BOONEOPS_BROKER_BEARER_TOKEN=<same-as-broker-BOONEOPS_BROKER_TOKEN>
BOONEOPS_BROKER_HMAC_SECRET=<same-as-broker-BOONEOPS_BROKER_SIGNING_SECRET>
BOONEOPS_BROKER_REQUIRES_TAILSCALE=true
FETCH_GENERAL_QUESTIONS_ENABLED=false
FETCH_ENABLED=false
```

With **`BOONEOPS_BROKER_ENABLED=false`**, RetrieverRebuild does **not** require broker URL/token/secret at startup (see `validate_contract` in `app/config.py`). You may still fill them in advance so flipping the flag later is only a restart.

### 2) Deploy/restart RetrieverRebuild (broker still disabled)

Follow **`deploy/WINDOWS_FETCH_RELEASE.md`** (typically `deploy.ps1` with migrations only when shipping SQL changes).

After restart:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8810/health/ready" -Method Get | ConvertTo-Json -Depth 8
```

Expect **`checks.booneopsBroker`: `disabled`** while **`BOONEOPS_BROKER_ENABLED=false`**.

### 3) Broker health from Windows (recommended before flipping Fetch broker flag)

Substitute your broker URL (same host/port as **`BOONEOPS_BROKER_URL`**):

```powershell
$brokerBase = "http://<tailscale-host-or-ip>:3487"
Invoke-RestMethod -Uri "$brokerBase/health" -Method Get
```

If this fails, fix Tailscale, firewall, broker service, or URL before **`BOONEOPS_BROKER_ENABLED=true`**.

### 4) Optional: Windows service sanity

```powershell
Get-Service RetrieverRebuild
Get-Service Retriever
```

**Retriever** on **8000** should remain **Running** if PrePress/token authority still depends on it.

### 5) Enablement order (don’t skip)

1. Broker **`GET /health`** succeeds from **`bggol-vesko01`**.
2. **`BOONEOPS_BROKER_ENABLED=true`** — **RetrieverRebuild restart** — confirm config validation passes (**URL**, **bearer**, **HMAC** all set).
3. **`FETCH_ENABLED=true`** — only after **`deploy/WINDOWS_FETCH_RELEASE.md`** checklist (includes model env vars for validation). For deploy-time **`healthcheck.ps1`** and **`smoke.ps1`**, set **`RETRIEVER_SMOKE_EXPECT_FETCH_ENABLED=true`** (machine or session env **or** the same line in **`retriever.env`**, inherited when **`deploy.ps1`** loads the file) whenever the service intentionally has **`FETCH_ENABLED=true`**, including GitHub Actions deploys on **`bggol-vesko01`** (see **`docs/runbooks/github-actions-retriever-rebuild-deploy.md`**). Feedback **`-RunSmoke`** applies the **same pilot flag** (process env, else that key read safely from **`retriever.env`**).
4. **`FETCH_GENERAL_QUESTIONS_ENABLED`** stays **`false`** until the separate general-LLM design ships.

## Source references

- `projects/booneops-bots/BROKER.md` — broker endpoints and broker-side env names.
- `projects/booneops-bots/FETCH_HANDOFF.md` — Tailscale topology, **`GET /health`**, **`POST /v1/booneops/message`**, auth headers, example base URL `:3487`.
- **`deploy/WINDOWS_FETCH_RELEASE.md`** — **`FETCH_ENABLED`**, **`smoke.ps1`**, migration **0002**, port **8810** / **8000** rules.
