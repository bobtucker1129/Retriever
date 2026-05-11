# GitHub Actions manual deploy — RetrieverRebuild (`bggol-vesko01`)

This document covers installing a **GitHub self-hosted Actions runner** on **Windows Server `bggol-vesko01`** and running the **`Deploy RetrieverRebuild (Windows self-hosted)`** workflow. It complements:

- **`deploy/WINDOWS_FETCH_RELEASE.md`** — Fetch foundation, migrations, BooneOps broker, smoke expectations.
- **`deploy/VM_SETUP_RUNBOOK.md`** — First-time **`D:\retriever-rebuild`** layout, NSSM **`RetrieverRebuild`**, ports.
- **`docs/runbooks/automated-feedback-bridge-windows.md`** — extended plan (Cloudflare-path checks with on-box service token, deeper Fetch probes). **Part E** in this file covers the **localhost JSON + artifact** loop that ships today.

After deploy, operators and agents should pull **Part E** artifacts from GitHub Actions; use the bridge runbook for staged public-path work.

## Deployment scope (critical)

**This automation deploys ONLY the NSSM service `RetrieverRebuild` on port `8810` under `D:\retriever-rebuild`.**

- **Guardrail:** **`deploy.ps1` must never stop, reinstall, rename, retarget port, or “clean up” the legacy Windows service named `Retriever` on port `8000`.** That service stays the PrintSmith-token / PrePress / DSF lane until an explicit planned cutover.
- The GitHub workflow does **not** add SSH keys or API tokens into the repo. Production secrets belong only on the server (**`D:\retriever-rebuild\env\retriever.env`** and similar), never in workflow YAML inputs.

Keeping **8710 vs 8810**: the only supported new-app port here is **`8810`**. Mistyping **8810 vs 8710** in tunnel or NSSM configs has caused outages elsewhere — double-check NSSM **`RetrieverRebuild`** and Cloudflare Tunnel target **`127.0.0.1:8810`**.

---

## Part A — Prerequisites on `bggol-vesko01`

Complete normal server setup before turning on Actions:

1. **`D:\retriever-rebuild`** exists (`releases`, `bin`, `env\retriever.env`, logs).
2. **`D:\retriever-rebuild\bin\deploy.ps1`** (and **`healthcheck.ps1`**, **`smoke.ps1`**, **`rollback.ps1`** as referenced by deploy) copied from **`deploy\*`** when those files change (**`WINDOWS_FETCH_RELEASE.md`** step 1).
3. NSSM service **`RetrieverRebuild`** installed (**`deploy/windows/install-service.ps1`**), listening on **`8810`**, using **`deploy/windows/run-service.ps1`** semantics per **`deploy/VM_SETUP_RUNBOOK.md`**.
4. **Git** reachable on `PATH` (the runner installs Git bundled; `preflight.ps1` requires **`git.exe`**).
5. The machine can **`git fetch`** from **`https://github.com/bobtucker1129/Retriever.git`** (HTTPS; no PAT required if the repo is public; if ever private, use `git`'s credential resolution on-box **outside** of GitHub Actions secrets for this workflow design).

Optional local check (**no secrets**, read-only probes):

```powershell
powershell -ExecutionPolicy Bypass -File D:\retriever-rebuild\repo\deploy\github-runner\preflight.ps1
```

(After this repo merges, clone or copy `deploy\github-runner\preflight.ps1` onto the host and invoke it from whichever path matches your layout; or run it from Actions after checkout.)

---

## Part B — Install the GitHub self-hosted runner (operator steps)

These steps assume you have **Admin rights** on `bggol-vesko01` and **`Owner`/Admin access** on the **`bobtucker1129/Retriever`** GitHub repository (or Org settings if org-level runners replace repo-level runners later).

### 1. Create a runner registration token

1. In GitHub, open **`https://github.com/bobtucker1129/Retriever`** (or Org **Settings → Actions → Runners** if you consolidate hosts).
2. **Settings → Actions → Runners → New self-hosted runner**.
3. Select **Windows** and **x64**. GitHub prints a **`config.cmd` / `./config`** one-liner with a **temporary registration token**.
4. **Security:** Tokens are short-lived. Do not paste them into issues, chat logs, or this repo — only into the server's console locally.

### 2. Extract the runner binaries on `bggol-vesko01`

Use a sensible install root, for example **`C:\actions-runner`** (recommended by GitHub; avoid `\Program Files` unless corporate policy dictates it).

Example (syntax only — filenames change per GitHub downloads page):

```powershell
New-Item -ItemType Directory -Path 'C:\actions-runner' | Out-Null
# Download the Actions runner ZIP from the GitHub runners page linked in the wizard, then expand:
Expand-Archive -Force -Path .\actions-runner-windows-x64-*.zip -DestinationPath C:\actions-runner
Set-Location C:\actions-runner
```

Run **`config`** from that directory using the **`./config.cmd`** flow shown in GitHub UI for Windows.

During configuration:

| Prompt / setting | Recommendation |
|---|---|
| Labels | **`RetrieverRebuild`** (custom), keep defaults **`self-hosted`**, **`Windows`**, **`X64`** GitHub assigns. |
| Runner group | Default is fine unless the org restricts groups. |
| Work folder **`_work`** | Default **`_work`**, on a disk with ample free space. |
| Running as Windows Service | Prefer **interactive service account** aligned with NSSM (**`RetrieverRebuild`**) conventions on this host (**`deploy/VM_SETUP_RUNBOOK.md`**) — many teams pick a dedicated **`Network Service`**/`Local System`/`gMSA`; match your MSSQL / UNC / permission model. Administrator is **not** required for **`git`** and **`venv`** builds if **`D:\`** paths are readable by the runner account. **`deploy.ps1`** expects **elevated NSSM/service restarts** separately; runners often cannot restart services unless the account can control **`RetrieverRebuild`** (discuss IT policy). |

**Most common blocker:** Runner account lacks rights to **`Restart-Service RetrieverRebuild`**. Coordinate with Boone IT so NSSM **`RetrieverRebuild`** is restartable by the runner principal (often **Log on as batch** rights + **`SeServiceLogonRight`**).

### 3. Labels must match workflow `runs-on`

Workflow file:

**`.github/workflows/deploy-retriever-rebuild-windows.yml`**

Uses:

```yaml
runs-on:
  - self-hosted
  - Windows
  - RetrieverRebuild
```

Ensure the runner exposes **all three** labels (capitalization should match **`Windows`**/`RetrieverRebuild`; GitHub compares labels lexically).

### 4. Start the runner listener

Either **run interactively**:

```powershell
.\run.cmd
```

or install as service per GitHub's Windows service snippet (elevated prompt).

---

## Part C — Preflight harness (repo-maintained script)

Repo path: **`deploy/github-runner/preflight.ps1`**

The workflow checks out **`deploy/`**, syncs the latest deploy scripts into **`D:\retriever-rebuild\bin\`**, and invokes this script **before** `deploy.ps1`. It verifies:

- **`D:\retriever-rebuild`** layout (**`bin`**, **`releases`**, **`env\retriever.env`**).
- **`D:\retriever-rebuild\bin\deploy.ps1`**
- **`git.exe`** visible.
- **Helpful diagnostics** for NSSM **`RetrieverRebuild`** legacy **`Retriever`**.

Failures block the workflow **before** a partial deploy wastes time.

---

## Part D — When the workflow runs

Repository: **`bobtucker1129/Retriever`**

Workflow **`.github/workflows/deploy-retriever-rebuild-windows.yml`** runs on:

- **`push`** to **`main`** (automatic deploy to **`RetrieverRebuild`** / **`8810`**), and
- **`workflow_dispatch`** (manual run with inputs below).

For **push** events, optional dispatch inputs are absent—**`deploy.ps1`** receives the commit **`github.sha`**. Use **manual dispatch** when you need migrations toggles or **`skip_legacy_liveness`** for controlled maintenance.

### Manual dispatch steps

1. Open **GitHub Actions** tab → workflow **`Deploy RetrieverRebuild (Windows self-hosted)`**.
2. **`Run workflow` → choose branch carrying the YAML** (usually **`main`**).
3. Select inputs:

| Input | Typical use |
|---|---|
| **`git_ref`** | Default **`main`**, or **`v1.2.x`**, **`feature/foo`**, or full SHA **`965a75c`** — passed straight to **`D:\retriever-rebuild\bin\deploy.ps1`**. |
| **`run_migrations`** | **True once** whenever a migration ships (**`WINDOWS_FETCH_RELEASE.md`** recommends **`RETRIEVER_RUN_MIGRATIONS=true`** for first **`0002`**, then usually false). Workflow maps to **`$env:RETRIEVER_RUN_MIGRATIONS`**. |
| **`assert_migration_0002`** | Optional safety (**`deploy.ps1`**: **`RETRIEVER_ASSERT_MIGRATION_0002=true`**) forcing DB verification before swapping junctions. |
| **`skip_legacy_liveness`** | When **false** (default), **`smoke.ps1`** still performs the **read-only HTTP probe** against **`localhost:8000`** to prove legacy stays up alongside **`8810`**. Toggle **true** only if probing legacy is undesirable (temporary outage troubleshooting). Workflow maps to **`$env:RETRIEVER_SMOKE_SKIP_LEGACY`**. |
| **Runner host env (not a workflow input)** | **`RETRIEVER_SMOKE_EXPECT_FETCH_ENABLED=true`** — set **on the Windows host** (system or account env visible to the runner) **only** while **`RetrieverRebuild`** intentionally runs with **`FETCH_ENABLED=true`**, so **`smoke.ps1`** expects **`checks.fetch`** and **`checks.modelProvider`** = **`ok`**. Omit for **`FETCH_ENABLED=false`** (foundation). Same pattern as optional **`RETRIEVER_SMOKE_CF_URL`**. |

4. **`Run workflow`**.

Observe logs on GitHub Actions and cross-check **`D:\retriever-rebuild\logs\deploy.log`**. For structured feedback, see **Part E**.

Built-in **`deploy.ps1` behavior:**

- Validates config, swaps staged release dirs, **clears guarded stale listeners still bound to `8810` under `D:\retriever-rebuild`**, **`Restart-Service RetrieverRebuild`**, then **`GET /version`** must report **`gitSha`** equal to the deployed full SHA (else deploy fails and rollback runs) before **`healthcheck.ps1`** + **`smoke.ps1`** (includes Cloudflare knobs only if **`RETRIEVER_SMOKE_CF_URL`** / secrets are preset **on-server**). **`RETRIEVER_SMOKE_EXPECT_FETCH_ENABLED=true`** is **machine-level** env on the runner when **`FETCH_ENABLED=true`** so deploy smoke asserts **`checks.fetch`** / **`checks.modelProvider`** as **`ok`**; leave unset for the default foundation expectation (**`disabled`**).
- Before invoking **`deploy.ps1`**, the workflow copies **`deploy\*.ps1`**, **`deploy\github-runner\post-deploy-feedback.ps1`**, and **`deploy\windows\*.ps1`** from the GitHub checkout into **`D:\retriever-rebuild\bin\`** so deploy script fixes ship automatically.

**There is intentionally no YAML toggle to skip automated health/smoke** — see **`WINDOWS_FETCH_RELEASE.md`** rationale.

Concurrency: **`concurrency.group: retriever-rebuild-deploy-bggol-vesko01`** means parallel dispatches serialize (second waits). **`cancel-in-progress: false`** prevents aborting mid-restart mid-deploy.

---

## Part E — Post-deploy feedback (agents, Cursor, humans)

After every workflow run, the job runs **`deploy/github-runner/post-deploy-feedback.ps1`** with **`if: always()`**, so it still collects localhost probes when **`deploy.ps1`** fails partway (for example after a bad restart). That does **not** turn a failed deploy green: the deploy step outcome still drives the overall workflow result unless a later step fails for a separate reason.

### What gets written (under the Actions workspace)

| File | Purpose |
|---|---|
| **`deploy-feedback/feedback.json`** | Machine-readable: version, health, Fetch `GET /fetch` status, optional broker **`GET …/health`**, legacy **`:8000`** probe, **`RetrieverRebuild` / `Retriever`** service states, optional **`smoke-transcript.txt`** metadata. No tokens or env secrets are read from **`retriever.env`** except **`BOONEOPS_BROKER_URL`** for an optional broker health URL (no bearer/HMAC). |
| **`deploy-feedback/FEEDBACK_SUMMARY.md`** | Short Markdown table for log paste and chat. ASCII-oriented. |
| **`deploy-feedback/smoke-transcript.txt`** | Full console capture of a second **`smoke.ps1`** pass (workflow uses **`-RunSmoke`**). Deploy already ran smoke once on success; this file is for CI visibility. |

### Where to download it

1. Open the workflow run on GitHub.
2. Under **Artifacts**, download **`retriever-rebuild-deploy-feedback`**.
3. Unzip and open **`FEEDBACK_SUMMARY.md`** first; use **`feedback.json`** for tools and agents.

The job log also prints a block between **`=== FEEDBACK_SUMMARY (concise) ===`** markers so you can screenshot or copy without downloading.

### How agents and operators should use it

- Treat **`gitStampOk: false`** (or the summary line **git stamp ok … NO**) as a mis-stamped release: **`/version`** still shows placeholder **`gitSha`** **`dev`** or **`gitRef`** **`local`**, which should not happen after **`deploy.ps1`** (see **`.release-meta`** stamping in **`deploy.ps1`**). Investigate the running release and env before trusting the deploy.
- **`fetchGet.statusCode`** should be **401** or **403** on production; **200** is only expected when **`RETRIEVER_SMOKE_LOCAL_FETCH=true`** (local dev identity). The script never sends cookies or service tokens.
- **Broker**: when **`BOONEOPS_BROKER_URL`** is set in **`D:\retriever-rebuild\env\retriever.env`**, the script probes **`{url}/health`**. By default a broker outage does **not** fail the workflow. Set the machine env **`RETRIEVER_FEEDBACK_FAIL_ON_BROKER=true`** on the runner (or a user env visible to the runner) if you want **`post-deploy-feedback.ps1`** to exit **1** when that probe fails.
- **Legacy**: respects **`RETRIEVER_SMOKE_SKIP_LEGACY`** / **`RETRIEVER_FEEDBACK_SKIP_LEGACY`** the same way as **`smoke.ps1`**.

### Manual rerun on the server

```powershell
powershell -ExecutionPolicy Bypass -File D:\retriever-rebuild\bin\post-deploy-feedback.ps1 -RunSmoke
# or from a full repo checkout:
powershell -ExecutionPolicy Bypass -File .\deploy\github-runner\post-deploy-feedback.ps1 -OutputDir .\deploy-feedback -RunSmoke
```

---

## Risks / watchouts

- **Privileges:** Runner lacks **Restart-Service **`RetrieverRebuild`** — deploy fails near end with service still **Stopped**/stale **`current`** symlink.
- **`deploy.ps1`** lock file **`deploy.lock`** — simultaneous manual **and** Actions deploy could contend; Actions concurrency mitigates only **within** Actions, not rogue RDP admins.
- **Git ref typos:** Non-existent branch → **`rev-parse`** error in **`deploy.ps1`**; fix ref and rerun.
- **Legacy port `8000`:** Default smoke treats legacy disappearance as Failure **by design**. Do **not** “fix CI” by stopping legacy **`Retriever`**; fix the outage or **`skip_legacy_liveness`** during controlled maintenance only.
- **Sparse checkout mismatch:** Updating **`deploy/github-runner/preflight.ps1`** affects **immediate** Actions health after merge once workflow branch includes it.

---

## After changes to deploy scripts locally

The GitHub Actions workflow now copies **`deploy/deploy.ps1`**, **`deploy/smoke.ps1`**, **`deploy/healthcheck.ps1`**, **`deploy/rollback.ps1`**, **`deploy/github-runner/post-deploy-feedback.ps1`**, and **`deploy/windows/*.ps1`** into **`D:\retriever-rebuild\bin\`** before each deploy. Manual RDP deploys should do the same if you bypass Actions.
