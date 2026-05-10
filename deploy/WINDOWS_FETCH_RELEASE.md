# Windows release checklist — Fetch foundation (migration 0002)

Use on **bggol-vesko01** only. Employees reach the app through **Cloudflare Access** at **https://retriever.boonegraphics.net** (tunnel to `127.0.0.1:8810`). This path touches **RetrieverRebuild** on port **8810** and **must not** stop, reinstall, or retarget the legacy **Retriever** Windows service or port **8000**.

For **manual GitHub Actions deploy** from **`bobtucker1129/Retriever`** (workflow dispatch, no repo secrets — server-side **`deploy.ps1`** only): see **`docs/runbooks/github-actions-retriever-rebuild-deploy.md`** (`preflight.ps1`, self-hosted runner labels **`self-hosted`, `Windows`, `RetrieverRebuild`**).

## What this release is (plain English)

- **New Retriever** (**RetrieverRebuild**) is the auth shell, admin tools, and **new Fetch**: conversation list, rename, soft delete, and messages stored in MySQL after migration **0002**.
- **Old Retriever** (**Retriever**, port **8000**) stays up for **PrePress, DSF, and PrintSmith REST token authority** until a later planned cutover. Smoke checks expect it still to accept connections unless you explicitly skip that probe.
- **Old Fetch** in the legacy app is **off** so employees are not offered two Fetch surfaces.
- **Real model calls, provider routing, PrintSmith/docs/BooneOps from the ask box, and uploads** are **not** wired through the ask path yet. If `FETCH_ENABLED=true`, the ask action still saves the user message and appends a **fixed stub assistant reply** only.

## BooneOps broker (Tailscale — disabled until you intentionally enable)

**Operator runbook:** `docs/runbooks/booneops-broker-fetch-windows.md` (broker health **`GET /health`**, **`BOONEOPS_*`** env names, **`bggol-vesko01`** PowerShell verification, coexistence with port **8000**).

Phase 1 intent: Fetch should match **Discord `#printsmith`** behavior **via** the BooneOps broker (`projects/booneops-bots/FETCH_HANDOFF.md`). When **`BOONEOPS_BROKER_ENABLED=false`**, RetrieverRebuild does **not** require broker URL/token/secret at startup. **`BOONEOPS_BROKER_ENABLED=true`** prepares the outbound client, but **`FETCH_ENABLED=false`** still keeps the composer closed so broker turns are not reachable in the UI; follow the **`FETCH_ENABLED`** checklist below (and merged code changes) before employees rely on BooneOps replies.

Exact **Retriever Fetch** env names (mirror **`AppSettings`** in **`app/config.py`**; values only in **`D:\retriever-rebuild\env\retriever.env`**, never in chat):

- **`BOONEOPS_BROKER_ENABLED`** — default **`false`**; **`true`** only after Tailscale **`GET …/health`** smoke from **`bggol-vesko01`** passes and you accept startup validation (**URL**, **Bearer**, **HMAC** required when **true**).
- **`BOONEOPS_BROKER_URL`** — broker base (**no trailing slash**, typically `http://<tailscale-host-or-ip>:3487`).
- **`BOONEOPS_BROKER_BEARER_TOKEN`** — must match broker-side **`BOONEOPS_BROKER_TOKEN`**.
- **`BOONEOPS_BROKER_HMAC_SECRET`** — must match broker-side **`BOONEOPS_BROKER_SIGNING_SECRET`** ( **`X-BooneOps-Signature`** body signing).
- **`BOONEOPS_BROKER_REQUIRES_TAILSCALE`** — default **`true`**.

Separate from broker traffic: **`FETCH_GENERAL_QUESTIONS_ENABLED`** (**`false`** = no broad internet/general LLM path; future per-user admin + **`fetch.ask_general`** per **`FETCH_TRUST_PLAN.md`**).

**Smoke nuance:** with **`BOONEOPS_BROKER_ENABLED=true`**, **`/health/ready`** exposes **`checks.booneopsBroker`** as **`degraded`** today (configured-on indicator, **not** a live broker socket check). Confirm the real broker with **`GET /health`** on the **`BOONEOPS_BROKER_URL`** host from **`bggol-vesko01`** before widening employee use.

## `FETCH_ENABLED` and config validation (read this before changing env)

In code today, **`FETCH_ENABLED` only unlocks the ask/composer stub**; it does **not** turn on real model routing.

Startup validation is stricter: **if `FETCH_ENABLED=true`, the app still requires `MODEL_PROVIDER`, `MODEL_DEFAULT`, and (for Anthropic) `ANTHROPIC_API_KEY` to be set** even though the stub does not call the provider. If you flip the flag without those variables, **the service will fail config validation and will not start.**

**Production recommendation for this foundation phase:** keep **`FETCH_ENABLED=false`**. Operators still get the Fetch shell, conversation CRUD, and storage against MySQL after **0002**; the composer stays off and `/health/ready` keeps **`fetch`** and **`modelProvider`** in the **`disabled`** state, which matches the post-deploy smoke script. Treat **`FETCH_ENABLED=true`** as a deliberate test or pilot step, not the default, until you complete the enablement checklist at the end of this document.

With **`FETCH_ENABLED=false`**, **model-related environment variables are not required** for validation—you may leave placeholders out of production env until you approach real routing.

## Preconditions

- `D:\retriever-rebuild\env\retriever.env` is current (no secrets pasted into chat or docs).
- Deploy scripts that clear inherited legacy env vars are in use (`deploy.ps1` clears old `FETCH_*`, `MODEL_*`, etc., before loading this file).
- You run PowerShell **as Administrator** when the runbook says so.

## Deploy steps (release includes `0002_fetch_conversations`)

1. Copy latest `deploy\*.ps1` and `deploy\windows\*.ps1` into `D:\retriever-rebuild\bin\` if the repo versions changed.
2. Pull and deploy the target Git ref (example: `main`):

   ```powershell
   $env:RETRIEVER_RUN_MIGRATIONS = "true"
   powershell -ExecutionPolicy Bypass -File D:\retriever-rebuild\bin\deploy.ps1 main
   ```

   The **first** deploy after the code that adds **`0002_fetch_conversations`** **must** run migrations once (`RETRIEVER_RUN_MIGRATIONS=true`). That applies the conversation/message tables and records **`0002`** in `retriever_cloudflare.schema_migrations`. Later deploys can omit the variable unless a new SQL migration ships.

3. Optional safety after the database has been upgraded at least once: fail the deploy early if **`0002`** is missing (catches a half-upgraded or wrong database):

   ```powershell
   $env:RETRIEVER_ASSERT_MIGRATION_0002 = "true"
   powershell -ExecutionPolicy Bypass -File D:\retriever-rebuild\bin\deploy.ps1 main
   ```

4. If the deploy script did not restart the service (first install), install or start **RetrieverRebuild** only via the documented NSSM flow; do **not** change the legacy **Retriever** service.

5. Smoke (localhost + optional Cloudflare path + legacy port):

   ```powershell
   powershell -ExecutionPolicy Bypass -File D:\retriever-rebuild\bin\smoke.ps1
   ```

   For checks through the public hostname, set **`RETRIEVER_SMOKE_CF_URL`** (and optional Access service-token variables documented in **`smoke.ps1`**). To skip the legacy **8000** listener check, set **`RETRIEVER_SMOKE_SKIP_LEGACY=true`**.

## Smoke expectations (foundation, `FETCH_ENABLED=false`)

The shipped **`smoke.ps1`** is aligned with **foundation** operation:

- **`/health/live`**, **`/health/ready`**, **`/version`** succeed on **`http://127.0.0.1:8810`** (or your base URL).
- **`/version`** JSON includes **`gitSha`** and **`environment`**, and must not echo secrets.
- **`/health/ready`**: under current health logic, **`checks.fetch`** and **`checks.modelProvider`** are both **`disabled`** when **`FETCH_ENABLED=false`**. The smoke script asserts that—if you set **`FETCH_ENABLED=true`**, expect these checks to fail until smoke expectations are updated for a pilot.
- **`checks.booneopsBroker`**: **`disabled`** when **`BOONEOPS_BROKER_ENABLED=false`**. If you set **`BOONEOPS_BROKER_ENABLED=true`** for integration work, **`/health/ready`** may show **`degraded`** overall because broker/tailscale rows are placeholders—still run broker **`GET /health`** manually from **`docs/runbooks/booneops-broker-fetch-windows.md`** until smoke expectations catch up.
- **`GET /fetch`**: without a browser session, expect **401/403** (Cloudflare identity or app auth). Anonymous **200** is only for local-dev smoke override.
- **Legacy Retriever** on **8000**: by default, smoke still checks that something answers (token authority unchanged).

Manual sanity after smoke: sign in through Access, open **Fetch**, create a conversation, rename it, confirm it survives refresh. Users need active Fetch module/capability access for the shell and ask path when **`FETCH_ENABLED=true`**. **Do not** expect real AI replies while **`FETCH_ENABLED=false`**; with it **`true`**, expect only the **stub** reply text unless BooneOps broker routing is deliberately enabled.

## Verify

- **RetrieverRebuild**: `Get-Service RetrieverRebuild` shows **Running**; `http://127.0.0.1:8810/version` returns JSON with **`gitSha`** and **`environment`**.
- **Fetch policy**: with foundation settings, **`/health/ready`** shows **`fetch`** and **`modelProvider`** as **`disabled`**.
- **Legacy Retriever**: still listening on **8000** when the smoke legacy check is enabled; **`Get-Service Retriever`** should remain **Running** when that service is still required for PrePress and token authority.

## What must stay disabled or unwired for this phase

Until a separate **model-routing enablement** pass is signed off:

- **Real LLM/provider calls** from the Fetch ask path.
- **Tool routing** to PrintSmith, docs indexes, BooneOps broker, uploads, and delayed reports from chat turns.
- **Treat `FETCH_ENABLED=true` as exposing the stub only**, not as “Fetch is fully live.”

## Rollback

Use **`rollback.ps1`** only for **RetrieverRebuild**; it does not alter the legacy **Retriever** service.

---

## Checklist — before turning on **real** model routing and tools

Use this when you intentionally move past the stub. Items are decision + verification pairs; do not flip **`FETCH_ENABLED`** (or change smoke expectations) until the business and technical checks you need are satisfied.

**Policy and trust (`FETCH_TRUST_PLAN.md`, `AUTH_REDESIGN.md`)**

- [ ] Default model and provider approved; data-retention and vendor posture documented.
- [ ] Who may use general outside-world answers vs internal-only routes is decided (`fetch.ask_general`, admin settings).
- [ ] Uploads, email cleanup, and delayed reports: which lanes are in scope for first live routing.

**Config and secrets**

- [ ] Production env includes valid **`MODEL_*`** / provider keys **before** **`FETCH_ENABLED=true`** if validation requires them.
- [ ] BooneOps broker: **`BOONEOPS_*`** aligns with **`projects/booneops-bots/BROKER.md`** / **`FETCH_HANDOFF.md`**; Tailscale **`GET /health`** from **`bggol-vesko01`** succeeded before **`BOONEOPS_BROKER_ENABLED=true`** (`docs/runbooks/booneops-broker-fetch-windows.md`).
- [ ] **`FETCH_GENERAL_QUESTIONS_ENABLED=false`** stays the default until the general LLM rollout is deliberate (broker-only BooneOps/`#printsmith`-style lanes do **not** need this flip).
- [ ] PrintSmith token authority mode still matches coexistence plan (**old authority** on **8000** vs future cutover in **`PRINTSMITH_TOKEN_AUTHORITY.md`**).
- [ ] No accidental use of dev identity or placeholder cookie secrets in production.

**Health and observability**

- [ ] **`/health/ready`** and **`/health/deep`** semantics updated or accepted for “fully enabled Fetch” (today, **`fetch`** / **`modelProvider`** flip to **`ok`** when **`FETCH_ENABLED=true`** even for the stub—tighten or document before relying on health for provider truth).
- [ ] Audit/logging covers model calls, tool calls, and denials at the level you need.

**Tests**

- [ ] Automated tests green for the release that wires routing.
- [ ] Manual: internal question, PrintSmith-backed question (when routed), docs question, failure and timeout behavior per trust plan.
- [ ] Post-deploy **`smoke.ps1`** updated if **`FETCH_ENABLED=true`** is normal—today’s script assumes both integrations **`disabled`**.

**Operational**

- [ ] Rollback path verified from a release with routing enabled.
- [ ] Operators know how to detect “model down” vs “Fetch stub” vs “tool denied” from user-visible copy and logs.
