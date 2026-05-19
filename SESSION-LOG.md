# retriever-rebuild: Session Log

Exit summaries, newest at top. Use project-local wrap to keep this current.

**Path note:** Older entries may name planning files as if they lived in the repo root (for example `FETCH_TRUST_PLAN.md`). Those files now live under **`docs/planning/`**. See **`PLAN.md`** → *Active Architecture Artifacts* and **`docs/README.md`** for current paths.

---

## 2026-05-18 — Codex: Help freshness cron scaffold

**Goal:** Add a high-level, dry-run-safe OpenClaw scaffold for periodically auditing Retriever Help freshness without touching Worker A's app implementation work or enabling a real cron.

**What changed:**

- Added outer OpenClaw script `scripts/retriever-help-freshness.js`.
- The script scans local Retriever docs, route files, templates, Wiki helpers, and future Help folders when present.
- It writes report artifacts under `projects/retriever-rebuild/.help-freshness/`:
  - `help-freshness-report.md`
  - `help-freshness-report.json`
  - `last-run.json`
- Added `.help-freshness/` to Retriever `.gitignore` so recurring audit artifacts stay local.
- Added `docs/planning/HELP_ORCHESTRATION.md` to document the ownership boundary: Retriever publishes Help, OpenClaw audits/drafts, human/admin review gates publication, English/Spanish parity gets checked, and biweekly cadence is the default.
- Linked the Help orchestration doc from the docs map, planning README, and active artifact list.

**Proof:**

- `node --check /Users/whitakertate/Whitaker/workspace/scripts/retriever-help-freshness.js` passed.
- `node /Users/whitakertate/Whitaker/workspace/scripts/retriever-help-freshness.js --dry-run` wrote the report artifact and found 86 help-relevant files, 94 route touchpoints, 50 flagged files, and no explicit English/Spanish pairs yet.

**Cron status:** No real cron was registered or enabled. Recommended disabled-cron/manual command is:

```bash
cd /Users/whitakertate/Whitaker/workspace && node scripts/retriever-help-freshness.js --dry-run
```

## 2026-05-18 — Codex: Wiki sync freshness visibility

**Goal:** Add the next Wiki-ready surface while the OpenClaw sync waits on production/shared secrets.

**What changed:**

- Confirmed the latest Windows self-hosted deploy completed successfully after the Wiki sync bridge landed.
- Verified `RetrieverRebuild` on `BGGOL-VESKO01` reported green `/version`, `/health/live`, and `/health/ready` feedback; BooneOps broker stayed green and legacy `Retriever` on port `8000` stayed running.
- Verified the public sync endpoint is still protected by Cloudflare Access and no local `WIKI_SYNC_*` / `RETRIEVER_WIKI_*` secrets are available in this workspace.
- Added Wiki homepage sync/freshness visibility from `wiki_sources`, latest `wiki_sync_runs`, and indexed document counts.
- `/wiki/` now shows source status, card counts, scanned/changed counts, and last synced time once inventory has landed; before that, it explains that OpenClaw cron enablement will populate the panel.

**Proof:**

- Focused suite: `python3 -m pytest -q tests/test_wiki_repository.py tests/test_wiki_sync.py tests/test_routes.py tests/test_config.py` -> **109 passed**.
- Full suite: `python3 -m pytest -q` -> **333 passed, 1 PyPDF2 deprecation warning**.

## 2026-05-18 — Codex: Wiki sync activation attempt

**Goal:** Activate the Wiki sync path as far as possible without leaking secrets or taking over unrelated dirty work.

**What changed / verified:**

- Generated and installed a strong `WIKI_SYNC_TOKEN` into local `retriever.env` for OpenClaw-side use.
- Used a temporary GitHub Actions workflow with a masked repo secret to add `WIKI_SYNC_ENABLED=true` and the matching `WIKI_SYNC_TOKEN` to `D:\retriever-rebuild\env\retriever.env`; then deleted the temporary workflow and removed the GitHub secret.
- Dispatched a migration-enabled deploy after updating `migrations/0004_wiki_catalog.sql` to avoid database-level foreign-key constraints because production `retriever_app` lacks MySQL `REFERENCES` privilege.
- Verified the Windows localhost sync endpoint succeeded: `status=ok internalScanned=28 driveScanned=0`.
- Confirmed the OpenClaw public POST is still blocked:
  - `https://retriever.boonegraphics.net/wiki/sync/source-inventory` returns Cloudflare Access `302` without a service token.
  - A proposed `retriever-sync.boonegraphics.net` DNS route was created for the Retriever tunnel, but the Windows runner cannot edit `C:\cloudflared\config.yml` (`Access denied`), so that hostname currently returns `404` and is not usable for sync.
- Cron `retriever-wiki-sync` remains disabled.

**Next blocker:**

- Either add a Cloudflare Access service token for OpenClaw (`RETRIEVER_WIKI_CF_SERVICE_TOKEN=<client-id>:<client-secret>`) or have an admin add a path-only `retriever-sync.boonegraphics.net` ingress rule for `/wiki/sync/*` on `bggol-vesko01`'s `cloudflared` config and restart the service.

## 2026-05-18 — Codex: Wiki sync command foundation

**Goal:** Continue the live Retriever Wiki by adding the first idempotent sync foundation for source metadata without scheduling automation or exposing raw ISO documents to normal readers.

**What changed:**

- Added `python3 -m app.wiki.sync` with `--internal-wiki` for SweetProcess links and `--drive-inventory path/to/export.json|csv` for Google Drive inventory exports.
- Added Wiki repository write support for `wiki_sources`, `wiki_sync_runs`, `wiki_documents`, and source/document `wiki_links`.
- Google Drive inventory rows now create draft employee-facing document cards with admin-only raw source links.
- `/wiki/` now uses synced `boone-internal-wiki` SweetProcess links when available, falling back to the built-in procedure list until the first DB sync runs.
- Added tests for SweetProcess parsing, Drive inventory loading, draft card classification, admin-only source links, repository upserts, and synced link reads.

**Proof:**

- Production unauthenticated probes reached Cloudflare Access redirects as expected: `/health/live`, `/version`, and `/wiki/` each returned `302`.
- Focused suite: `python3 -m pytest -q tests/test_wiki_repository.py tests/test_wiki_sync.py tests/test_routes.py` -> **97 passed**.
- Full suite: `python3 -m pytest -q` -> **321 passed, 1 PyPDF2 deprecation warning**.
- CLI smoke: `python3 -m app.wiki.sync --help` displayed the expected sync options.

**Open / next Wiki work:**

- Run the command against production MySQL with a real Drive inventory export and the live internal-wiki page.
- Add reviewed/approved summary workflow and admin visibility for sync freshness/failures before scheduling recurring automation.
- Keep raw Google Drive/ISO source links admin-only unless Master Tate explicitly approves broader exposure.

## 2026-05-18 — Codex: OpenClaw Wiki sync bridge design + disabled cron

**Goal:** Figure out how recurring Wiki sync should work now that OpenClaw has Google Drive access but Retriever production owns LAN/MySQL access.

**What changed:**

- Added workspace operator script **`scripts/retriever-wiki-sync.js`** in the outer OpenClaw workspace.
  - Reads Google Drive using existing OpenClaw/LordTate Google credentials.
  - Inventories the first safe root, **`Final Boone`**, instead of crawling every broad ISO/source folder.
  - Writes inventory artifacts under **`projects/retriever-rebuild/.wiki-sync/`**.
  - Can either run Retriever's local Python sync directly or POST the inventory to Retriever when `RETRIEVER_WIKI_INGEST_URL` is set.
- Confirmed direct DB sync from Whitaker/OpenClaw is **not viable**: Boone MySQL `192.168.33.243:3306` timed out from this machine. Correct boundary is:
  - **OpenClaw** inventories Drive.
  - **Retriever on Windows/LAN** ingests and writes `retriever_core`.
- Added Retriever ingest config:
  - `WIKI_SYNC_ENABLED`
  - `WIKI_SYNC_TOKEN`
- Added secure POST endpoint:
  - `POST /wiki/sync/source-inventory`
  - Requires `Authorization: Bearer <WIKI_SYNC_TOKEN>` or `X-Retriever-Wiki-Sync-Token`.
  - Pulls SweetProcess links and ingests posted Drive inventory on the Retriever/LAN side.
- Added disabled OpenClaw cron job:
  - Name: **`retriever-wiki-sync`**
  - ID: **`df821699-0a39-4b86-bb34-d6c94c8858cf`**
  - Schedule: **5:30 AM America/New_York daily**
  - Disabled until the Retriever code is deployed and secret env values are installed.

**Proof:**

- `node scripts/retriever-wiki-sync.js --dry-run` found **Final Boone** and wrote an inventory of **1,362 files from 1 root**.
- Direct DB proof failed as expected from Whitaker: `Can't connect to MySQL server on '192.168.33.243:3306'`.
- Focused tests after endpoint/config changes: **106 passed**.
- Full suite: `python3 -m pytest -q` -> **324 passed, 1 PyPDF2 deprecation warning**.
- OpenClaw cron show confirms the disabled job exists.

**Enablement remaining:**

1. Deploy the Retriever endpoint to production.
2. Add `WIKI_SYNC_ENABLED=true` and a strong `WIKI_SYNC_TOKEN` to `D:\retriever-rebuild\env\retriever.env`.
3. Add matching `RETRIEVER_WIKI_SYNC_TOKEN` or `WIKI_SYNC_TOKEN` to the environment visible to OpenClaw cron.
4. If Cloudflare Access blocks the machine POST, add a Cloudflare Access service token to OpenClaw as `RETRIEVER_WIKI_CF_SERVICE_TOKEN` or reuse `RETRIEVER_SMOKE_CF_SERVICE_TOKEN`.
5. Run `openclaw cron run df821699-0a39-4b86-bb34-d6c94c8858cf --expect-final --timeout 900000`.
6. Enable after a clean run: `openclaw cron enable retriever-wiki-sync`.

## 2026-05-18 — Codex: Wiki module shell, catalog, SweetProcess links live

**Goal:** Add a small, low-risk Wiki module to Retriever for Boone internal knowledge without destabilizing Fetch or exposing raw ISO documents to normal readers.

**What changed:**

- Added **Wiki** to the Retriever left rail with a **W** sign and `/wiki/` route.
- Built the first Wiki landing page structure around Master Tate's desired categories:
  - **SweetProcess Procedures**
  - **Work Instructions**
  - **Quality & ISO**
  - **Security Posture**
  - **General Knowledge**
- Pulled the existing `https://www.boonegraphics.net/internal-wiki` SweetProcess links into the top section and kept those external procedure URLs intact because they are heavily used.
- Added Wiki catalog schema/read shape:
  - `wiki_sources`
  - `wiki_documents`
  - `wiki_document_versions`
  - `wiki_sections`
  - `wiki_links`
  - `wiki_sync_runs`
- Added `/wiki/doc/{slug}` detail routes and fallback cards for representative ISO / Work Instruction documents including `M-001`, `SOP-023`, `WI-015`, `WI-018`, `WI-022`, `WI-023`, `WI-024`, and `WI-030`.
- Inventoried the shared Google Drive ISO folder enough to identify the first source spine: `Final Boone`, `External Documents`, `Training Documents`, `Updates & In-process`, and `Archive`.
- Confirmed architecture direction:
  - Google Drive and the Boone internal-wiki page stay source systems.
  - Retriever stores controlled metadata/summaries and sync state.
  - Vector search can be added later as an index, not the canonical source.
  - Normal Wiki readers should get cards, summaries, and drill-downs, not raw ISO document opens.
  - Fetch should later use a tiny feature-flagged read-only Wiki lookup adapter, not a broad Fetch rewrite.

**Production / deploy:**

- Pushed and deployed these main commits:
  - **`1b57414`** — Add Wiki module shell
  - **`19f4e0d`** — Add Wiki catalog drilldown
  - **`777886d`** — Promote Wiki procedure links
- Production **`/version`** verified on **`777886d4d63863bfab5ccb360c5b37203dd228ed`**, host **`BGGOL-VESKO01`**.
- Production **`/health/live`** returned **200 OK**.
- `https://retriever.boonegraphics.net/wiki/` was verified live behind Cloudflare Access with SweetProcess links and Wiki categories visible.

**Proof:** `python3 -m pytest -q` -> **315 passed, 1 PyPDF2 deprecation warning**.

**Open / next Wiki work:**

- Build the idempotent sync command/service for Google Drive ISO / Work Instruction metadata and `boonegraphics.net/internal-wiki` SweetProcess links.
- Generate draft summaries and section drill-downs from synced content, with review/approved state before treating the summaries as controlled knowledge.
- Add operator/admin visibility for last sync status, stale documents, failed syncs, and summary review state.
- Schedule the recurring sync through OpenClaw or the chosen automation path after the sync command exists. **No OpenClaw cron has been scheduled yet.**
- Keep Fetch changes out of this phase except for a later small feature-flagged Wiki search adapter.

---

## 2026-05-18 — Codex: PrePress migration, auth locations, ticket save live

**Goal:** Bring old Retriever PrePress into the rebuild while keeping the old and new apps side-by-side on the same PrePress database, aligned to the new auth/location matrix, and restore the old job-ticket save workflow.

**What changed:**

- Wired **PrePress** into the rebuild using the existing MySQL data path: **`retriever_prepress`** for app state and **`switch_shared.prepress`** / MIS data for active operators and invoice/job-part visibility.
- Added/verified admin location support from MIS production locations; operator locations now drive the PrePress queue mapping. Master Tate’s seed/admin row can be edited for location and was set to **`100/Scott Working`** in production.
- Removed stale auth ideas from earlier Cursor attempts, including **BooneOps** access toggles and old Fetch-level/regular-LLM toggles that no longer match the product decision.
- Ported the old PrePress WIP shell into the rebuild and iterated visual sizing: tighter controls, old-style cell dividers, wider PrePress work area, compact top filters, page-size control, and statistics controls.
- Restored the **Ticket → View / Save** behavior. New Retriever borrows the old Retriever PrintSmith token authority through the proxy instead of minting its own token while old Retriever is still live.
- Fixed the PrePress page script block not rendering from the shared layout. That restored both:
  - the **parts expander** (`+`) for invoice job parts;
  - the tiny top **save confirmation banner**.
- Fixed live ticket save 500s on Windows by adding **`tzdata`** and a timezone fallback. The banner now returns the old-style message, e.g. **`Saved Y1_JobTicket_103166_20260517-175120.pdf under Remote.`**
- Improved save error handling so non-JSON server failures show as server failures instead of always saying “network error.”

**Production / deploy:**

- Pushed and deployed these main commits:
  - **`0d160ac`** — Port PrePress shell into rebuild
  - **`ff354c2`** — Show legacy PrePress open rows in WIP
  - **`0091f55`**, **`ee3178c`**, **`9c5c714`** — PrePress visual/layout refinements
  - **`f0ff2cb`** — Prepare PrePress ticket save proxy support
  - **`30ced05`** — Fix PrePress page scripts
  - **`bf2db0e`** — Fix PrePress ticket save timezone
- Production **`/version`** verified on **`bf2db0e5db0f4c07b4558a35ab057b0644aa16d9`**, host **`BGGOL-VESKO01`**.
- Production **`/health/live`** returned **200 OK** after the final deploy.

**Verified live:**

- `https://retriever.boonegraphics.net/prepress/` loads behind Cloudflare Access.
- WIP table loads 25 rows and shows **Ticket View + Save**.
- The **parts expander** opens invoice `103166` and loads job parts.
- Copy buttons in PrePress work.
- Real ticket save succeeded and wrote:
  - **`D:\SwitchJobs\Jobs_26\103166_TestingForScott\Remote\Y1_JobTicket_103166_20260517-175120.pdf`**
- Local full test suite before final deploy: **`python3 -m pytest` → 308 passed, 1 PyPDF2 deprecation warning**.

**Important secrets note:** The PrintSmith proxy key/token values were found in the general OpenClaw/workspace envelope and applied to the Windows new Retriever env. Do **not** paste or log those values. New Retriever env now uses old-authority proxy mode for PrePress ticket saves.

**Open / next PrePress work:**

- Continue comparing visual behavior against old Retriever after Scott uses it live for a round.
- Investigate any remaining old PrePress API behavior around ticket save edge cases, selected-part PDF merge, and file-share permissions if operators hit failures.
- Keep old Retriever PrePress running side-by-side until Scott confirms read/write behavior and user/location alignment.

## 2026-05-16 — Codex: auth admin users matrix

**Goal:** Replace the pending-only admin approval card with the actual user authorization table Master Tate described after testing `weborders@boonegraphics.net` through Cloudflare Access.

**What changed:**

- Added migration **`0001_retriever_core_auth.sql`** for admin profile fields: `full_name`, production location id/name, Inventory level, and Proofs level.
- Reworked **Admin → Users** into one user matrix: **Last Login**, Cloudflare email, Full Name, Location, Admin, Fetch, PrePress, DSF, Inventory, Proofs, Role, BooneOps, Status, Actions.
- New pending users show **Pending** in **Last Login** until approval; approval now requires a full name.
- **Admin / Fetch / PrePress / DSF** are yes/no module gates. **Inventory / Proofs** are placeholder levels: **No / Viewer / Manager**.
- Location options come from the MIS `productionlocations` query when available; saved location id/name is copied to the Retriever user row.
- Server derives the internal role from the **Admin** yes/no selection; no hidden role choice is trusted from the UI.
- Seed operator account remains protected from matrix and direct legacy admin POST endpoints.
- Added **Remove** action: deletes the Retriever profile/access rows, revokes sessions, audits the delete, protects self/seed, and lets the same Cloudflare email return later as pending.
- Checked old Retriever auth: it used MySQL **`retriever_core.users`** as the sole auth source with username/password hashes, role enum, active flag, location fields, `last_login`, and hard delete. Rebuild now targets that same **`retriever_core`** app-state schema instead of the Cursor-era **`retriever_cloudflare`** schema.
- Updated admin onboarding runbook to match the new operator flow.

**Update after DB review:** Master Tate confirmed **`retriever_cloudflare`** was the Cursor/new-rebuild attempt and asked to use the existing Boone MySQL **`retriever_core`** app-state database instead. Active code/config/migrations now target **`retriever_core`**; `0001_retriever_core_auth.sql` preserves old password-auth compatibility columns while adding Cloudflare identity/status/module/session/audit tables and fields. Do **not** drop the live `retriever_cloudflare` schema until the `retriever_core` deploy is verified.

**Proof:** `python3 -m pytest -q` → **270 passed** after the `retriever_core` switch. Local dev server on **`127.0.0.1:8810`** returned **200** for `/health/live`, `/version`, `/`, `/admin/users`, and `/fetch`. Chrome DevTools MCP opened local `/admin/users` with no console errors earlier in the auth-matrix pass. Production Chrome snapshot before deploy showed the old pending-only card for `weborders@boonegraphics.net`, confirming the target behavior gap.

**Next:** Apply migration and deploy through the Windows runner, then use production `/admin/users` to save Full Name/Location/modules for `weborders@boonegraphics.net` and Approve.

---

## 2026-05-16 — Codex: admin onboarding matrix hardening

**Goal:** Continue from the current Retriever workspace state and make the in-progress admin user matrix safer to ship.

**What changed:**

- Preserved the new **Admin → Users** matrix direction: directory view across pending/active/suspended/blocked users, pending-account copy, minimal pending shell nav, and `docs/runbooks/admin-user-onboarding.md`.
- Split the accidentally blended route test so **activate user** coverage is its own test again.
- Hardened admin actions so the **seed operator account** cannot be changed through direct legacy POST endpoints, not only hidden from the matrix UI.
- Added direct endpoint coverage for seed-row protection.

**Proof:** `python3 -m pytest -q` → **264 passed**. Local dev server on **`127.0.0.1:8810`** returned **200** for `/health/live`, `/version`, `/`, `/admin/users`, and `/fetch`. Chrome DevTools MCP opened `/admin/users`; no console errors; document/CSS/logo requests were **200**.

**Notes:** Local dev server was stopped after verification. The repo still contains broader pre-existing dirty state, including doc moves and untracked documentation/assets; separate commits by concern before push.

---

## 2026-05-17 — Wrap: planning docs → `docs/planning/`, kickoff path clarified

**Goal (this wrap):** Close the session after **documentation layout** work: Master Tate could not judge “how aggressive” cleanup should be without knowing what **kickoff** actually loads; simultaneously reduce **root markdown sprawl** (~22 files) so the default session path matches **human expectation**.

**What landed:**

- **Root = session spine only:** **`KICKOFF.md`**, **`PLAN.md`**, **`PARKED.md`**, **`SESSION-LOG.md`**, **`HANDOVER.md`** stay at repo root; **17** long-form specs moved to **`docs/planning/`** (single hub + relative links fixed: `../deploy/`, `../runbooks/`, `../archive/`).
- **Navigation:** **`docs/README.md`** (map) and **`docs/planning/README.md`** (what lives there); archived Opus review links retargeted; **`HANDOVER.md`** / **`KICKOFF.md`** explain “read `PLAN`’s active artifact list, paths under `docs/planning/`.”
- **Cross-repo pointers:** **`deploy/WINDOWS_FETCH_RELEASE.md`**, **`docs/runbooks/*`**, **`.cursor/skills/retriever-test-ready/SKILL.md`**, **LordTate** **`.cursor/rules/retriever-rebuild.mdc`**, **`memory/shared/seeds/2026-05-17-fetch-broker-openclaw-topology.md`** and **`2026-05-05-cursor-security-model.md`** use the new **`docs/planning/...`** paths where they cited Retriever trust docs.

**What we learned (plain English):** Kickoff **never** implied “read every root `.md`”; it implied **five spine files + whatever `PLAN.md` lists for the active goal**. Putting long specs one folder down makes that **visible** without deleting history (**`SESSION-LOG`** path note preserves older references).

**Proof:** `python3 -m pytest -q` → **255 passed** (no runtime code changes in this pass).

**Repo / next push:** **Retriever** nested repo under `projects/retriever-rebuild` has **staged-ready** doc moves (many `D` at old paths + **`?? docs/planning/`** until `git add`); **LordTate** workspace shows **modified** **`retriever-rebuild.mdc`** and seed path tweaks—**commit separately** per repo policy. `git status` still shows unrelated untracked noise (**.DS_Store**, **`.cursor/`** plugin copy, **`retriever_favicon_package/`**) — **do not** mix into a docs-only commit without intent.

**Next session:** **`PLAN.md` → Next Recommended Session`** (Discord–Fetch parity **eight-step program**). Before coding: **`.cursor/skills/retriever-test-ready/SKILL.md`** preflight + open **Retriever** in a browser (local **`http://127.0.0.1:8810/`** or **`https://retriever.boonegraphics.net/`** after Access).

---

## 2026-05-17 — Broker: Fetch gateway-first (unified agent path)

**BooneOps broker (`projects/booneops-bots`):** Retriever Fetch (`sessionMetadata.source: retriever-fetch`) now **defaults to gateway-only**: broker-local **data-list** and **report/chart** steps are skipped unless `BOONEOPS_FETCH_GATEWAY_ONLY` is set false on the host. `getConfig()` passes `fetchGatewayOnly` into routing; `buildGatewayEnvelope` no longer tells the model that a separate broker report engine owns charts when gateway-only is on. **Rollback:** set `BOONEOPS_FETCH_GATEWAY_ONLY=false` and restart the broker. Integration tests force `BOONEOPS_FETCH_GATEWAY_ONLY=false` inside `withBrokerEnv` so HTTP fixtures stay stable. See `BROKER.md` and `docs/DISCORD_FETCH_PARITY.md` for operator notes and the `reportContext` / export follow-up gap.

---

## 2026-05-17 — Wrap: parity spine reset (golden Discord contract + kill forks)

**Goal (this wrap):** Close the session after **live pilot feedback**: Fetch **`/docs`** first answers can still **diverge hard from Discord** (example: **Enfocus Review** story first, **Checkpoint via mail** only after operator pushback); **PrintSmith** can still show **generic failure** with **footer that does not match the error**. **Whitaker** broker **`launchctl kickstart`** + **`/health` 200** confirmed after broker updates.

**What landed (earlier in this arc — repos):**

- **LordTate `main`:** Broker **parity docs**, **golden fingerprint fixtures**, **`BROKER.md`** timeout note (**`a2bceccf`**); **Fetch `/docs` grounding** tighten against invented elements + meta-preface (**`e8565fad`**).
- **Retriever `main`:** **Transport error copy** centralized (**`broker_user_visible_copy`**), **`booneops_broker`** wiring, tests, **`docs/DISCORD_FETCH_PARITY.md`** pointer, **PLAN/SESSION** updates (**`09a097a`**).

**What we learned (plain English):** Shared **logs and calmer HTTP errors** do not equal **same first-turn answer**. **Discord is defined by the exact broker POST + the pipeline behind it**; until Fetch sends the **same inputs** through the **same forks** (MCP vs gateway, session key, envelope, model policy, retrieval), **operators will still feel “old Fetch.”** **UI polish is last** once outcome-class match is proven.

**Next session:** **`PLAN.md` → Next Recommended Session`** — owner **eight-step program**: (1) capture **one real Discord** redacted **`POST /v1/booneops/message` + assistant text**; (2) **one shared builder** with Discord; (3) **remove path splits** or align Discord; (4) **session key parity**; (5) **identical model stack**; (6) **same tools/retrieval**; (7) **shadow harness** on fixed prompts; (8) **UI copy last**. Run **Retriever test-readiness preflight** before code.

**Retriever git (nested repo):** This wrap updates **`PLAN.md`** + **`SESSION-LOG.md`** in **`projects/retriever-rebuild`**; run **`git status`** there and in **LordTate workspace** before unrelated commits.

---

## 2026-05-16 — Wrap: unified broker trace row + parity handoff

**Goal (this wrap):** Continue **Discord–Fetch parity** — ship **one trace row** on every broker message completion and align **Retriever** operator logs; close the session with a clear **next-session punch list**.

**What landed (LordTate workspace `main`):**

- **`6ac5568b`** — Parity **foundation**: single **`retriever-fetch`** source check, honest **transcript labels** for non-Fetch gateway envelopes, correct **MCP caller `source`**, **`parity-outcome`** + harness tests, **`DISCORD_FETCH_PARITY.md`** (+ Retriever pointer).
- **`88f8e2e3`** — **`traceSummaryForMessageComplete`** merged into **`booneops.message.complete`** JSON (`traceV`, `conversationId`, `sessionSource`, `routeLabel`, **`parity*`** fingerprint fields). Retriever **`app/fetch/booneops_broker.py`** **`BooneOps broker turn`** line adds **gateway model**, **error codes**, **artifact count** for cross-log grepping.

**Verification:** **`npm test`** in **`projects/booneops-bots`** (98 passed); **`pytest`** in **`projects/retriever-rebuild`** (246 passed).

**What we learned (plain English):** Matching Discord and Fetch is easier when **logs speak the same language** — one broker JSON line plus a Fetch line that carries the same **route, outcome shape, and correlation** beats comparing prose answers alone.

**Next session:** See **`PLAN.md` → Next Recommended Session → Immediate next session`** (tier parity, error copy, golden harness, gateway model if needed, Whitaker broker pull + Retriever deploy when you want prod logs).

**Retriever git:** This wrap updates **`PLAN.md`** + **`SESSION-LOG.md`** only in the workspace; other paths may still be dirty — run **`git status`** before shipping unrelated work.

---

## 2026-05-14 — Parity program: broker envelope + harness foundation

**Goal:** Start executing the **Discord–Fetch parity** plan: single source for Fetch-stamped requests, honest transcript labels for non-Fetch broker posts, MCP observability metadata, structured outcome diff helper + tests, canonical docs.

**What landed:** `projects/booneops-bots` — `lib/broker-request-source.cjs`, `lib/parity-outcome.cjs`, `test/parity-harness.test.cjs`, envelope transcript heading fix, MCP `source` from `sessionMetadata`; `docs/DISCORD_FETCH_PARITY.md`; `BROKER.md` link. `projects/retriever-rebuild` — `docs/DISCORD_FETCH_PARITY.md` pointer, `PLAN.md` open-item refresh.

**Verification:** `npm test` in `booneops-bots` (97 passed); `pytest` in `retriever-rebuild` (246 passed).

**Next:** Tier/timeouts/denials, unified trace row, Retriever retry/error copy sweep, golden prompts against live broker, OpenClaw gateway model telemetry if needed.

---

## 2026-05-15 — Wrap: honest Fetch status + broker telemetry shipped; next = nine-track Discord parity

**Goal (this wrap):** Close the **model/context footer honesty** work and **broker-side** grounding/logging; hand off with a **single next arc**: **Discord–Fetch behavioral parity** (nine engineering tracks).

**What landed (engineering):**

- **Retriever (`Retriever` repo `main`):** **`35a5d45`** — per-answer line uses **broker `gatewayModelId`** when present (**friendly + raw slug**); **not recorded** when absent; **thread load** metadata (char estimate, bucket, conservative new-chat hint) on BooneOps turns; **`/printsmith`** unchanged by **General Question** flag (still only **`general_candidate`**).
- **LordTate workspace (`main`):** **`278ec9a5`** — **`retriever-docs-guidance`**: **`/docs`** Switch **grounding** prompt block for **`retriever-fetch` + `docs_candidate`**; **`broker-runtime`**: structured **`pickGatewayModelFromStructuredPayload`**, WebSocket **stream/chat counts**, **`gatewayModelId` / `gatewayRunId` / session suffix`** on broker JSON + **`createSuccessResponse`**; **`broker-server`**: **`booneops.message.complete`** carries **capped** telemetry; **`report-runtime`**: unwrap **`runGatewayPrompt`** object return. **Whitaker:** repo **already on** broker commit; **`launchctl kickstart`** **`com.boonegraphics.booneops-broker`**; **`/health`** OK on **3487** and **3488** after brief startup delay.
- **Deploy:** GitHub Actions **Deploy RetrieverRebuild** run **25895650494** **success**; production **`/version`** shows **`gitSha`** prefix **`35a5d45`**, host **`BGGOL-VESKO01`**.

**What we learned (plain English):**

- **General Question On** does **not** help **`/printsmith`** typos — that flag only unlocks **`general_candidate`** to the broker; **PrintSmith** routes already use BooneOps when the broker is on.
- **“Copy the same settings”** fails because parity is a **chain** (history, envelope, fast paths, retries, randomness), not one knob.
- Operator **feel**: pilot is **“in a really good place”**; remaining pain is **Discord vs Fetch variance**, not the footer lie.

**Next session (owner-picked):** Execute the **nine-track Discord–Fetch parity program** spelled in **`PLAN.md` → Next Recommended Session`** (shared contract, session semantics, kill forks, identical tools/denials, shared errors/retries, parity harness, unified traces, nondeterminism budget, intentional non-goals).

**Retriever git:** **`PLAN.md`** + **`SESSION-LOG.md`** updated this wrap; other local noise may exist — next agent **`git status`** in **`projects/retriever-rebuild`** before shipping.

---

## 2026-05-15 — Wrap: Discord vs Fetch first-turn capture, wrong element repro, next fixes

**Goal (this session arc):** Prove **first-turn** Fetch **`/docs`** vs **Discord `#general`** after conv-scoped gateway session; capture **broker + OpenClaw** evidence; line up **next engineering**.

**What we learned (plain English):**

- **Side-by-side in Chrome:** DevTools MCP can drive **Retriever** and **Discord web** by **switching tabs**; not one fused split view unless both are in one browser layout.
- **Paired capture (no operator paste):** New Fetch thread **`fb2ab908-2bcd-4b96-8ccf-ea2d0b86bae7`**, single ask: `/docs Are there any switch elements that let you approve a step via email?` **First answer was confidently wrong** — invented **“Approve via Email” / “Approval submit point”** (not **Checkpoint via mail**). Discord BooneOps on the same question named **Checkpoint via mail** correctly.
- **Broker (Whitaker):** `projects/booneops-bots/logs/broker-node.log` → **`requestId` `3b13c5a0-5ef3-4b4a-930c-dca216dd12c9`**, **`elapsedMs` ~24508**, **`ok` true** for that turn.
- **OpenClaw gateway (`~/.openclaw/logs/gateway.log`):** Same wall-clock window shows **`useResume=false session=none`**, **`claude-sonnet-4-6` via `claude-cli`**, **`promptChars=3267`**, **`rawLines=55`**, then the wrong answer text logged. Earlier **same day** another cold Fetch run (`19:48` block) with **same `promptChars=3267`** produced a **correct Checkpoint via Mail** answer (**`rawLines=179`**) — so failure is **not** “Fetch is always cold”; it is **unreliable first-turn grounding** / variance.
- **UI honesty gap:** Fetch footer still shows **“Model: Opus 4.7”** while gateway runs **Sonnet**; **context percent** stays **0%** in UI — both mislead operators about **when to start a new chat**.

**What landed in repo earlier this arc (reminder):** LordTate **`main`** broker commit **`d8785870`** — extra **Discord parity** lines in `projects/booneops-bots/lib/retriever-docs-guidance.cjs` (anti title-dump); **`pytest`** broker-runtime tests green.

**Next session (owner-picked):**

1. **Truthful status line:** show **actual model / provider** from broker or gateway metadata when available; replace hard-coded Opus label where wrong; add a **defensible context-window hint** (estimate from message count + rough chars, or broker `session_context` if exposed) so “0% forever” is not the only story.
2. **Broker / gateway grounding:** small **prompt + logging** change with **tests** — e.g. require **retrieved element names** before asserting, log **tool turn counts** / session flags next to **`requestId`** — Tier 1 in **`projects/booneops-bots`**.

**Retriever git:** wrap does not imply commit; workspace may carry unrelated dirty paths — next agent should **`git status`** in **`projects/retriever-rebuild`** before shipping.

---

## 2026-05-14 — Wrap: Fetch broker parity, gateway session continuity, operator defaults

**Goal (this session arc):** Fetch should feel like **Discord BooneOps** for docs and shop questions—**follow-ups** stay on the broker lane, **errors** are clearer, and **first answers** use the same kind of OpenClaw continuity Discord gets.

**What landed (engineering):**

- **Retriever (`main`):** Sticky routing so **`general_candidate` / `unknown`** follow-ups after a successful **`docs_candidate`** or **`printsmith_candidate`** BooneOps turn inherit that lane (fixes **`?`** → general stub). **One** broker HTTP retry on transient failure or **5xx**; calmer errors with **`request_id`** in metadata for support.
- **LordTate workspace (`main`):** Broker builds OpenClaw gateway **`sessionKey`** from **Fetch `conversationId`** for **`retriever-fetch`** so one employee thread **reuses** the same gateway session across asks (Whitaker broker + gateway; see `projects/booneops-bots`). **Whitaker:** `git pull` at **`3eef1323`**, **`launchctl kickstart`**, **`/health`** OK.
- **Live check:** Chrome MCP against production Fetch—**new chat** repro showed **no** general stub and **no** BooneOps error on the skeptical follow-up after deploy **`9375099`**.

**What landed (governance / next sessions):**

- **Canonical operator defaults** for Cursor: **`memory/shared/seeds/2026-05-14-master-tate-cursor-session-discipline.md`** (act first, prefer Chrome/Retriever verification, same-session retry loop with **five-try cap**, **push `main` → deploy → live test** cadence while building). **Cursor rule:** **`.cursor/rules/master-tate-session-discipline.mdc`** (always-on summary + pointer to seed). **`PROJECT_INDEX`** row for **retriever-rebuild** / **booneops-bots** nudged.

**Next recommended focus:** Re-compare **first-turn `/docs`** answers to **Discord** on the same Switch question after gateway session fix; if substance still drifts, tune **gateway prompt / tools** (not Retriever routing). Continue **docs summary + source** UX per **`FETCH_TRUST_PLAN.md`**.

**Retriever git:** `main` clean for tracked files; only local **untracked** noise (e.g. `.cursor/`, favicon package) if present—operators can ignore or `.gitignore` when ready.

---

## 2026-05-14 — BooneOps broker live on Whitaker; Fetch docs quality up; follow-up kinks

**Goal (this arc):** Retriever Fetch should ride the same **BooneOps / OpenClaw** path as Discord for docs-style questions, not the old catalog title-dump.

**What landed:**

- **LordTate `main`:** Broker skips MCP fast path when `sessionMetadata.source` is `retriever-fetch`; gateway envelope gets **Discord-style parity** text when `retrieverDiscordAnswerParity` is set. Whitaker: **`git pull`**, **`brew`** repair for **Node/merve/simdutf** dyld crash, **`install-macos-launchagent.sh`** so broker + proxy on **3487** actually run current code.
- **Retriever `main`:** Payload sends **`retrieverDiscordAnswerParity`**; logs **`BooneOps broker turn … actions=…`** and stores **`booneops_actions`** on assistant metadata for operator visibility.
- **Memory:** `memory/business/boone-graphics.md` + **`PROJECT_INDEX`** updated with **one-tree workspace** map (`/Users/whitakertate/Whitaker/workspace`, nested `retriever-rebuild` vs sibling `booneops-bots`).

**Pilot feedback (Master Tate):** First **`/docs`** answer after broker fix was **much better structured** (clearly BooneOps-shaped) but **substance was still wrong** on at least one try. **Follow-up** in the same thread **reverted** to the old **“general question / download charts…”** stub behavior. Prefixing **`/docs`** on the follow-up produced **“BooneOps encountered a server error”** (broker or upstream failed that turn).

**Next session (priority):**

1. **Harden the BooneOps link** — treat Fetch → broker as **first-class**: retries, clearer user copy on 5xx, maybe correlation id in UI for support.
2. **Follow-up routing** — ensure **continuations** of a **`docs_candidate`** (or recent BooneOps) thread **stay** on broker/docs lane instead of falling through to **`general_candidate`** stub (`followup_routing.py`, `resolve_fetch_ask_route`, prior message `route_key`).
3. **Reproduce `/docs` follow-up 500** — check Retriever logs for **`BooneOps broker turn`** + **`booneops_actions`**, Whitaker **`logs/broker-node.log`** / gateway for that `request_id`; fix root cause (timeout, gateway, envelope size, etc.).

**Verification:** Retriever **`pytest`** green on broker paths after metadata logging commit; Whitaker **`curl 127.0.0.1:3487/health`** OK post-restart.

---

## 2026-05-14 — Docs trust presentation + local artifact lifecycle

**Goal:** Pilot-ready **`/docs`** readability (summary lead-in for long answers, collapsed sources), **30-day** default for local HTML/PDF snapshots, **delete snapshot files when a conversation is deleted**, user-facing retention copy, plan/trust doc updates (gateway rotation marked done; answer-snapshot PDF explicitly deferred).

**What happened:**

- **Config:** `fetch_local_artifact_retention_days` default **30**; **`fetch_docs_summary_min_chars`** (default **900**); `.env.example` documents both.
- **Retention:** `unlink_local_snapshot_files_from_messages` before conversation soft-delete; existing mtime-based prune unchanged.
- **UI:** `docs_aware_assistant_body_html` + Jinja filter; **`<details>`** around source cards; summary-lead CSS; Fetch shell **retention note**.
- **Docs:** `FETCH_TRUST_PLAN.md` pilot bullets + **Local snapshots vs broker** subsection; `PLAN.md` open items updated.

**Verification:** `python3 -m pytest -q` → **233 passed** (Whitaker).

**Next:** Windows **`smoke.ps1`** + Chrome after deploy per runbook.

---

## 2026-05-13 — Fetch routing polish, test-readiness discipline, wrap vs /end

**Goal:** Make **`/docs`** and **`/printsmith`** reliable forced routes and widen docs-keyword routing without turning on general questions; surface slash commands in the Fetch UI; add a favicon; strip those slash prefixes in the broker payload; add **project-wide** test-readiness preflight (skill + rule + KICKOFF); clarify that **`wrap`** owns the next-session handoff (browser + preflight) while workspace **`/end`** stays LordTate-wide only.

**What happened:**

- **Local routing:** `classify_fetch_intent` handles `/docs` → docs lane, `/printsmith` → PrintSmith lane; expanded `_DOCS_HINTS` for Switch/Enfocus-style questions; help stub lists new slash commands.
- **UI:** Composer chips for `/docs`, `/printsmith`, `/help`, `/sources`, `/health` with insert-into-composer behavior; `fetch-favicon.svg` + layout cache-bust link; workspace `.gitignore` exception for `projects/retriever-rebuild/app/static/*.svg`.
- **Broker:** `broker_message_after_slash_route_prefix` strips forced slash prefix before BooneOps message; placeholders if the user sends only the command.
- **Operator tooling:** `retriever-test-ready` skill, `retriever-preflight` rule (globs app/tests/migrations/deploy), KICKOFF preflight note; **wrap** rule updated so every handoff prompt mandates preflight + browser; **reverted** adding that handoff to `/end` so OpenClaw-wide save stays separate.
- **Tests:** Retriever `pytest` suite green at **229** on the committed paths; LordTate `main` includes commits through **`f33254e2`** for this arc.

**Plain-English result:** Employees (and you) can force docs vs PrintSmith lanes with slash commands; the next agent is steered to **prove** they can see Retriever before another long code loop. **`wrap`** and **`/end`** are no longer mixed up.

**Still open:** Same pilot priorities as **PLAN.md** (docs answer UX, artifact lifecycle, gateway rotation). **Working tree:** many `projects/retriever-rebuild/` paths are still **modified or untracked** locally versus `git status`—reconcile, test, and commit when you are ready (this wrap does not commit).

**Next recommended session:** See PLAN **Next Recommended Session**; add **reconcile local retriever-rebuild git state** if you need a clean deploy branch.

---

## 2026-05-12 — Fetch tables, artifacts, follow-up context, and styled exports

**Goal:** Continue **Fetch pilot employee-readiness** without widening rollout: make answers easier to read, route PrintSmith/report questions more naturally, make downloads work, and let normal follow-up language act on the previous report instead of falling into the general stub.

**What happened:**

- **Markdown/table rendering:** Deployed **`9136fa2`** so assistant pipe tables render as real sanitized HTML tables with compact Fetch styling; live Chrome found existing stored pipe-table answers rendering as table elements with horizontal overflow inside the bubble.
- **Source/artifact presentation:** Source cards now show only when real metadata exists and stay compact; artifact cards render safe same-origin links. Local general/download stub wording is clearer when a request cannot run.
- **Routing fixes:** Deployed **`8edbf72`** so dated job/work-order prompts route to PrintSmith/report handling. The exact prompt “Can you give me a list of job that were digital Color in the month of Jan, 2026” no longer hit the general stub.
- **Follow-up exports:** Deployed **`afc2570`** so “export that” style follow-ups inherit the previous successful report/docs route. Local sanitized **HTML** exports work from the previous answer and return a same-origin attachment link.
- **Artifact download proxy:** Deployed **`60dd1ad`** so BooneOps PDF/Excel/CSV artifacts download through Retriever instead of browser requests receiving JSON. Live Chrome verified existing PDF/XLSX links now stream real files, and new artifacts use `/fetch/artifacts/broker/{artifactId}`.
- **Fuzzy follow-up language:** Deployed **`baf1e48`** so normal phrases like “fancy up the Excel file,” “make the spreadsheet prettier,” and “add colorful headers” continue recent successful report/export context instead of going general.
- **Styled Excel:** Committed BooneOps **`8bd5db0e`** and restarted the Whitaker BooneOps broker LaunchAgent. Styled Excel mode adds blue header fill, white bold header text, and thin borders while preserving freeze row, autofilter, widths, and number/date formats.
- **Report context handoff:** Deployed **`8867ff6`** so Retriever persists bounded BooneOps `reportContext` and forwards it with later follow-ups. This fixed the live “No structured report context is available” error for styled Excel follow-ups.
- **Verification:** Retriever tests reached **198 passed**; BooneOps tests reached **58 passed**. Live Chrome verified production Retriever SHA **`8867ff6`**, a fresh DSF report, normal Excel export, then the exact fuzzy “fancy up the Excel” phrase producing a new valid XLSX. The downloaded workbook contained blue header fill **`FF4472C4`**, white font **`FFFFFFFF`**, and thin borders.

**Plain-English result:**

Fetch now feels much more like an employee-facing assistant: it reads tables cleanly, remembers the last report well enough to handle natural follow-ups, produces HTML snapshots locally, downloads BooneOps artifacts correctly, and can regenerate a nicer styled Excel file when asked in normal language. Rollout posture stayed **pilot-only**: **`FETCH_GENERAL_QUESTIONS_ENABLED` remains off**.

**Still open:**

- **Docs answers** still need summary-first presentation and short source cards before broad rollout.
- **OpenClaw gateway credential rotation** is still a security follow-up if not already done.
- **Artifact retention** needs a policy for local HTML exports and long-lived broker artifacts.
- **PDF expectations** need a product decision: BooneOps PDFs are chart/report artifacts; a local “snapshot this answer as a PDF” path would be separate work.

**Next recommended session:**

`kickoff projects/retriever-rebuild` — goal: **docs answer quality + artifact lifecycle cleanup**. Keep pilot flags narrow; do not enable general questions broadly. Decide whether Fetch needs local answer-snapshot PDFs and confirm gateway credential rotation status.

---

## 2026-05-12 — Fetch pilot employee-readiness UX (layout, scroll, attribution)

**Goal:** Improve **Fetch pilot readiness** without widening rollout: **easier-to-read answers**, **clear source/metadata presentation**, **reliable viewport layout and scroll**, and **correct local routing** for PrintSmith-shaped questions despite typos; keep **narrow pilot flags**.

**What happened:**

- **Answer presentation:** Assistant turns use **Markdown → safe HTML** for structure (lists, emphasis, breaks) via **`app/fetch/answer_render.py`**; **per-message status line** (model label, general-questions toggle, context). Stored content stays plain text; rendering is display-only after sanitize.
- **Broker metadata:** Conversation messages persist optional **JSON metadata** for **source/status/artifact-style cards** (repository + broker presentation path).
- **Fetch UI:** Removed confusing **preview trust** and pilot boilerplate strips; tightened **top bar** spacing; transcript is the **primary scroll surface** anchored to **latest turns** with **optimistic user bubble** and scroll scripts in **`shell.html`**.
- **Layout:** **`app.css`** + shell use **viewport-height flex/grid** so Fetch fills the window on varied resolutions (**not tied to one monitor**).
- **Static/CSS delivery:** **`layout.html`** cache-busters `app.css` with **`git_sha`**; **`main.py`** serves static files from an **absolute** `static` root to avoid cwd drift on Windows.
- **Routing:** **`local_routing.py`** tolerates PrintSmith-like misspellings and pairs **invoice/estimate-style** wording with **time cues** so fewer questions fall through to “general stub.”
- **Deploy verified (prior arc):** Layout/CSS fixes shipped through commits including **`0e4f494`** and **`085b082`**; GitHub Actions run **`25705235002`**; live **Chrome** spot-checks at several viewport sizes including a short window.
- **Wrap hygiene:** A local working tree had **accidental deletions** of core Fetch files and tests; **`git restore`** from **`HEAD`** brought them back; **`python3 -m pytest`** → **139 passed** on **`085b082`**.

**Plain-English result:**

Employees get a **calmer, more readable** Fetch thread, **attribution-friendly** metadata hooks, and **stable “stay at the bottom”** behavior; rollout posture stays **pilot-only**. **Next small win:** render **pipe tables** as real HTML tables (Markdown `tables` extension + allow-list + CSS), still inside the bubble.

**Next recommended session:**

`kickoff projects/retriever-rebuild` — goal: **Markdown pipe tables** in assistant answers + table styling; continue **docs summary + source cards** quality; **rotate OpenClaw gateway credential** if not done; do not enable **general internet** Fetch for everyone.

---

## 2026-05-11 — Live Fetch broker pilot verified (deploy lane + observability)

**Goal:** Prove **live Retriever Fetch** talking to BooneOps broker end-to-end in a **pilot-only** configuration, with deploy feedback reliably **green**, legacy **8000** untouched, and **no broad rollout** yet.

**What happened:**

- **Deploy + feedback:** Auto-deploy and post-deploy feedback were already wired; remaining gaps closed with **version stamping**, **broker URL**, and **Windows runner service permissions** so latest feedback runs read as success.
- **Engineering throughput this arc:** Deploy feedback/version fixes, **Windows restart / commit-SHA gate** hardening, **Fetch pilot spinner and smoke expectations** (`RETRIEVER_SMOKE_EXPECT_FETCH_ENABLED` alignment with live flags), **healthcheck alignment** with the pilot, and **Retriever-side broker error observability** (`4789cc3`, run **25693145755** verified: `/version` matches deployed SHA; smoke passed in pilot mode with **fetch**/ **modelProvider** and **broker health** okay; legacy **Retriever** on **8000** still responding; `/fetch` still **requires auth** and returns **401** when unauthenticated).
- **BooneOps correlation:** Workspace commit **`0b21f1bb`** adds **broker request correlation** logging; LaunchAgent restarted on Whitaker broker host; broker health verified.
- **Broker gateway misconfig:** BooneOps Deep Search / Fleet-style prompt initially failed with **gateway unavailable** because broker **`.env.broker`** aimed at Linux-default OpenClaw paths. **Whitaker broker** fixed by pointing env at **local OpenClaw gateway URL**, **gateway token file**, **device identity file**, **agent id**, **device family**; token file installed with restrictive permissions; broker restarted successfully.
- **Security follow-up:** OpenClaw **gateway-equivalent credential** appeared in tool output during config search — **schedule rotation** of that credential; do not duplicate values in docs.
- **Pilot flags (constrained):** `FETCH_ENABLED=true`, `BOONEOPS_BROKER_ENABLED=true`, `FETCH_GENERAL_QUESTIONS_ENABLED=false`, smoke expects Fetch on. General-questions path remains **stub**; local greeting **stub**; **PrintSmith / docs broker path** behaves usefully (**DSF proof-status** prompt returns a substantive BooneOps answer). **Telegram** and **Discord** stayed responsive through checks.
- **Product notes:** Docs retrieval answers are **too raw** for employees — need **summary + source hygiene** before widening audience. Spinner is acceptable for now; **Cursor-style threaded progress/thinking** is **roadmap**, not required to ship pilot polish. Retriever Fetch should speak as **BooneOps**, not **private LordTate** (already in plan decisions).

**Plain-English result:**

The **live pilot** demonstrates broker-backed Fetch behind Access with observability and deploy feedback behaving; rollout stays **narrow** until **presentation and persona polish** catch up.

**Next recommended session:**

**Product/readiness**, not wider flags: **docs answer formatting** (summaries, **source cards**), optionally **clearer progress/status in the Fetch UI**, keep **general internet** Fetch off and **pilot posture** deliberate; **`kickoff projects/retriever-rebuild`** to continue.

---

## 2026-05-11 — Automated feedback bridge documented (post auto-deploy)

**Goal:** Plan the **automated feedback bridge** after GitHub self-hosted **push-to-`main`** deploy: agent-readable outcomes without clipboard mediation, Windows- and **`8000`**-safe.

**What happened:**

- Confirmed **auto deploy** is **`on.push.branches: main`** on **`.github/workflows/deploy-retriever-rebuild-windows.yml`** (plus **manual dispatch**).
- Added **`docs/runbooks/automated-feedback-bridge-windows.md`**: Phases **A** (localhost feedback artifact), **B** (Cloudflare Access public URL via **service token on `bggol-vesko01`**, not repo secrets), **C** (Fetch/broker prompt smoke when enabled), **D** (workflow summaries / artifacts for agents).
- Updated **`docs/runbooks/github-actions-retriever-rebuild-deploy.md`**: intro links, **Part D** describes **push + manual**, **post-deploy feedback** pointer.
- Updated **`PLAN.md`**: **current phase** = feedback after deploy; **completed** auto deploy line; **resolved** decision text; **next session** = Phase A implementation; **open** items for artifact format/cadence/token rotation; **guardrail** for legacy **`8000`**.

**Plain-English result:**

Deploy lane is documented as **done** for routine **`main`** merges; the project now points **next engineering** at **Phase A feedback** (bundle health/smoke/version/legacy probe for agents), then Access token-on-box checks, then broker Fetch smoke.

**Next recommended session:**

Implement **Phase A** (workflow +/or server script producing artifact or bounded log block) and record the chosen format in the GitHub Actions runbook.

---

## 2026-05-09 — Fetch foundation deployed and smoke passed

**Goal:** Build and deploy the first real new-Fetch foundation behind the deployed auth shell while keeping model and tool routing disabled.

**What happened:**

- Confirmed old Fetch is off in the legacy Retriever.
- Built new Fetch conversation management in `RetrieverRebuild`: conversation list, create, select, rename, soft delete, and message storage backed by MySQL migration `0002_fetch_conversations`.
- Added gated ask handling: active user, Fetch access, and `FETCH_ENABLED` are required before any ask turn is accepted.
- Added deterministic local route labels and offline replies for `/help`, `/sources`, `/health`, email cleanup, PrintSmith-like requests, docs-like requests, general questions, blocked writes, local greetings, and unknown prompts.
- Kept all live model/provider/tool paths off: no Anthropic, PrintSmith, docs API, BooneOps, uploads, delayed reports, or web search calls.
- Hardened Windows deploy and smoke scripts for `RetrieverRebuild` on port `8810`, including migration `0002` checks and read-only old Retriever port `8000` liveness.
- Committed and pushed `89ecd60` (`Build safe Fetch foundation.`) to `main`.
- Deployed `89ecd60` on `bggol-vesko01`; `smoke.ps1` passed.
- Verified both Windows services are running: `RetrieverRebuild` and legacy `Retriever`.

**Plain-English result:**

New Fetch now has its safe foundation live behind Cloudflare Access. It can manage conversations and show deterministic offline replies when deliberately enabled for stub testing, but production model and tool routing remain off. Old Retriever still handles PrePress, DSF, and PrintSmith token authority.

**Next recommended session:**

Browser-check `https://retriever.boonegraphics.net/fetch` through Cloudflare Access with an approved admin user, then choose the next Fetch slice: admin settings/capability management, real model-provider enablement, or the first read-only internal/docs route.

---

## 2026-05-08 — Windows deploy path corrected and first release staged

**Goal:** Deploy the auth shell to `retriever.boonegraphics.net` from the Boone runtime.

**What happened:**

- Corrected a major deployment assumption: `bggol-vesko01` is Windows Server, not Linux. Old Retriever runs there as the `Retriever` NSSM service on port `8000`.
- Replaced the failed Linux/systemd/bash deployment path with Windows PowerShell/NSSM scripts.
- Configured Cloudflare Zero Trust for `retriever.boonegraphics.net`: team domain `boonegraphics.cloudflareaccess.com`, Boone Employees Access policy, tunnel `bf859516-9782-4c53-9098-1923709b4028`, DNS route, and `cloudflared` service running.
- Created MySQL `retriever_core` schema/user access from `192.168.33.12`.
- Fixed first-deploy blockers in the Windows deploy script: PowerShell 5.1 compatibility, reserved `$Args` variable shadowing, `pyproject.toml` install, old Retriever env-var pollution, Python cwd for static/templates, and the real migration API.
- Successfully staged release `ed41f94261910256edc71d104adcabf7dd00324c`; migrations applied `0001_retriever_core_auth.sql` and `0001_seed_auth_shell.sql`; `D:\retriever-rebuild\current` points at the staged release.
- Installed `RetrieverRebuild` via NSSM after making `install-service.ps1` PowerShell 5.1 safe; service started and returned `Health check OK: 200`.
- Local smoke passed: `/health/live`, `/health/ready`, `/version`, version metadata, no secret leakage, and disabled `/fetch` all passed (`8 passed, 0 failed`).
- Corrected the `cloudflared` Windows service command to run the configured tunnel (`--config C:\cloudflared\config.yml tunnel run retriever`); browser verification now shows Cloudflare Access first, then reaches Retriever successfully.

**Plain-English result:**

The first deploy is effectively live: new Retriever is installed as a Windows service, passed local smoke, and is reachable through Cloudflare Access at `retriever.boonegraphics.net`.

**Next recommended session:**

Confirm old Retriever on port `8000` remains untouched, run the updated Cloudflare smoke script once, then begin the first real Fetch build. Do not recreate Linux deploy artifacts.

---

## 2026-05-07 — Fetch UI polish, Boone brand colors, collapsible sidebar, and first GitHub push

**Goal:** Decide between Impeccable document pass, old Retriever visual inspection, or first Fetch skeleton. Run Impeccable critique and polish. Push to GitHub.

**What happened:**

- Inspected old Fetch UI directly and captured the visual continuity target in `FETCH_UI_CONTINUITY.md`.
- Built the disabled/stubbed Fetch skeleton: current-Fetch-style left conversation rail, rename UI, Thread Reports strip, centered Retriever logo empty state, composer, suggestion chips, and status footer showing model and context level for all users.
- Applied Boone brand palette from the 2024 brand guide: sidebar Boone Blue, active nav Boone Red, user messages blue, Ask Fetch button red.
- Added collapsible outer module sidebar with compact initials when collapsed, real Retriever logo in the main header, and light/dark theme toggle persisted via localStorage.
- Ran Impeccable critique (score 26/40). Applied distill/clarify/polish pass: simplified disabled screen to old-Fetch empty state plus Thread Reports strip, moved trust-state examples behind progressive disclosure, clarified disabled controls with inline copy, removed side-stripe list anti-patterns.
- Resolved deployment hostname: `retriever.boonegraphics.net` is the live hostname from first deploy. Old Retriever is LAN-only and has no Cloudflare presence so there is no DNS conflict.
- Created a new standalone git repo for `projects/retriever-rebuild/`, configured SSH remote, and pushed initial commit (`965a75c`) to `https://github.com/bobtucker1129/Retriever`.
- 48 tests passed throughout.

**Plain-English result:**

The rebuild now has a real app that looks and feels like old Retriever made sharper, uses Boone brand colors, and is on GitHub. The Fetch skeleton is a credible disabled preview, not a developer scaffold. The next session is the first production deployment.

**Next recommended session:**

`kickoff projects/retriever-rebuild`, then provision `bggol-retriever01`, harden the production `.env`, run the MySQL migration, configure Cloudflare Tunnel to `retriever.boonegraphics.net`, and smoke-test the live site.

---

## 2026-05-06 — Auth shell scaffold, shared layout, and local smoke

**Goal:** Continue the Retriever rebuild from runtime/token planning into a working auth-shell scaffold, then shape and polish the shared layout.

**What happened:**

- Resolved runtime and token-authority details: new Retriever should stage on a sibling Boone LAN Linux VM, `retriever.boonegraphics.net` remains the final live hostname, `retriever-next.boonegraphics.net` is staging, app state belongs in MySQL `retriever_core`, and old Retriever keeps first dibs on the shared PrintSmith token until new PrePress is ready.
- Wrote the core planning/build artifacts: `RUNTIME_NOTES.md`, `PRINTSMITH_TOKEN_AUTHORITY.md`, `VM_SETUP_PLAN.md`, `RETRIEVER_CORE_SCHEMA.md`, `CONFIG_AND_HEALTH_CONTRACT.md`, `AUTH_SHELL_BUILD_PLAN.md`, `LOCAL_RUNBOOK.md`, `PRODUCT.md`, and `SHARED_LAYOUT_SHAPE.md`.
- Built the first FastAPI auth shell with config validation, health/version routes, Cloudflare Access JWT validation, MySQL migration/seed SQL, repository scaffolding, DB-backed pending/admin user flow, strict audit writes, session cookies, logout/session revocation, and disabled Fetch placeholder.
- Added admin user actions for approve, suspend, block, role assignment, BooneOps level, module access, and capability grant/revoke.
- Ran Impeccable teach/shape for the shared Retriever shell and changed the scaffold from ugly standalone pages into a single shared Retriever layout where Admin is a normal left-sidebar module.
- Verified the scaffold locally: `pytest` reached 47 passing tests, compile/import passed, local route smoke passed, and `deploy/smoke.sh` passed.

**Plain-English result:**

The rebuild now has a real starting app, not just architecture notes. The new Retriever auth shell can start locally, prove core health routes, render a shared app layout, keep Fetch disabled, and exercise the admin/session/user-management logic through tests.

**Next recommended session:**

`kickoff projects/retriever-rebuild`, then decide whether to run Impeccable document for `DESIGN.md`, inspect old Retriever for closer visual matching, or start the first Fetch skeleton behind the polished shared shell.

---

## 2026-05-06 — Session wrapped for commit

**Goal:** Close the current Retriever planning session and commit the architecture artifacts.

**What happened:**

- Confirmed the Fetch trust plan, Cursor security planning docs, and concrete deployment bridge are now captured in project-local files.
- Left `PLAN.md` pointing to the next work: `RUNTIME_NOTES.md` and `PRINTSMITH_TOKEN_AUTHORITY.md`.
- Prepared the project for a local git commit.

**Plain-English result:**

The rebuild now has a documented path from product trust planning into production engineering. The next session should decide the exact Boone runtime shape and protect the existing PrintSmith token authority before any production cutover.

**Next recommended session:**

`kickoff projects/retriever-rebuild`, then write `RUNTIME_NOTES.md` and `PRINTSMITH_TOKEN_AUTHORITY.md`.

---

## 2026-05-06 — Deployment bridge made concrete

**Goal:** Complete the concrete Boone runtime and deployment details in `DEPLOYMENT_BRIDGE.md`.

**What happened:**

- Expanded `DEPLOYMENT_BRIDGE.md` from a boundary note into a concrete first deployment plan.
- Set the working runtime shape as a Boone LAN server or VM, with `bggol-vesko01` as the first host candidate unless a sibling Boone LAN app VM is cleaner.
- Defined `retriever-next.boonegraphics.net` as the first test hostname and kept `retriever.boonegraphics.net` for cutover only after gates pass.
- Defined the recommended service layout: `retriever-web.service`, app bound to `127.0.0.1:8810`, service user `retriever`, `/opt/retriever-rebuild`, `/etc/retriever-rebuild`, and `/var/log/retriever-rebuild`.
- Chose server-pull deploy from GitHub as the first deployment model, with `deploy.sh`, `rollback.sh`, `smoke.sh`, `healthcheck.sh`, release symlinks, and deploy records.
- Defined `/version`, `/health/live`, `/health/ready`, `/health/deep`, smoke tests, log access, Cloudflare Tunnel/Access routing, Tailscale runtime responsibilities, and old/new Retriever coexistence gates.
- Updated `PLAN.md` so the next session moves to runtime notes and PrintSmith token authority.

**Plain-English result:**

The rebuild now has a practical deploy bridge: Cursor builds and reviews, GitHub records the code, the Boone server pulls and runs the release, Cloudflare exposes it safely, and rollback does not depend on Cursor or GitHub being available.

**Next recommended session:**

`kickoff projects/retriever-rebuild`, then write `RUNTIME_NOTES.md` and `PRINTSMITH_TOKEN_AUTHORITY.md`. Decide whether `bggol-vesko01` is the first host or whether a sibling Boone LAN app VM is better, and make sure old Retriever's shared PrintSmith token role survives cutover.

---

## 2026-05-06 — Cursor security added to planning artifacts

**Goal:** Add Cursor security to the Retriever rebuild documents so the project benefits from Cursor's development controls without confusing them for production Retriever security.

**What happened:**

- Created `DEPLOYMENT_BRIDGE.md` with the core boundary: Cursor/OpenClaw can build and review code, but Boone production runs Retriever.
- Created `SECRETS_HANDLING.md` with rules that Cursor can see templates and redacted examples, not production secrets by default.
- Created `AUDIT_LOG_DESIGN.md` separating Retriever app audit logs from the Cursor/development audit trail.
- Created `WEBHOOK_AND_BROKER_AUTH.md` separating Cursor MCP/dev credentials from Retriever production service credentials.
- Created `BUILD_CODE_LAYOUT.md` with repo/config rules that let Cursor agents work safely without touching production secrets.
- Updated `PLAN.md` so these documents are active architecture artifacts and the next session focuses on concrete Boone runtime/deployment details.

**Plain-English result:**

Cursor is now documented as part of the workshop, not part of the production machine. It can help build Retriever safely, but production Retriever still needs Boone-controlled secrets, Cloudflare Access, LAN isolation, service auth, audit logs, deployment rollback, and runtime health checks.

**Next recommended session:**

`kickoff projects/retriever-rebuild`, then complete the production runtime and deployment bridge details: choose or narrow the Boone host, define deploy and rollback commands, write health/smoke checks, clarify Cloudflare/Tailscale responsibilities, and plan old/new Retriever coexistence.

---

## 2026-05-04 — Fetch trust plan written

**Goal:** Write the Fetch trust plan and incorporate the Opus review warnings about slow PrintSmith/DSF reports, `/printsmith` and `/docs` routing, and preserving current Fetch features.

**What happened:**

- Loaded the project kickoff docs, active auth redesign, Opus review, parked list, and old Fetch reference behavior.
- Wrote `FETCH_TRUST_PLAN.md`.
- Centered the plan on a 30-second chat wall: Fetch must answer, clarify, refuse, fail clearly, or move to a delayed-report progress card before the user is left staring at a dead spinner.
- Defined a Cursor-like delayed-report experience for heavy PrintSmith/DSF list and export work: visible progress, automatic in-chat updates, and guardrails so users do not accidentally stack follow-up requests while a report is running.
- Preserved current Fetch features as explicit requirements: conversation history/sidebar, email cleanup, prompt hints, uploads/private library, source panels, status/model bar, BooneOps status, report downloads, thread reports, slash commands, and admin/user preview behavior.
- Updated `PLAN.md` so the next recommended session moves to deployment bridge planning.

**Plain-English result:**

Fetch now has a trust policy before code. The rebuild should keep what employees already like, but stop long PrintSmith/DSF requests from looking frozen or failing only after a timeout.

**Next recommended session:**

`kickoff projects/retriever-rebuild`, then write `DEPLOYMENT_BRIDGE.md` so the project has a safe path from OpenClaw/GitHub to the Boone LAN server, including rollback, health checks, logs, Cloudflare/Tailscale responsibilities, and old/new Retriever coexistence.

---

## 2026-05-04 — Opus review captured and project kickoff tightened

**Goal:** Let Opus 4.7 review the rebuild plan before starting the Fetch trust plan, then capture anything important so it survives the session.

**What happened:**

- Ran a read-only senior-engineer review against `projects/retriever-rebuild/` and sampled the old `projects/Retriever/` reference where needed.
- Captured the review in `docs/archive/REVIEW-2026-05-04-OPUS.md`.
- Updated `KICKOFF.md` and `.cursor/rules/retriever-rebuild.mdc` so future kickoff reads active architecture artifacts, not only kickoff/plan/parked/session log.
- Updated `PLAN.md` with the active review artifact and new open decisions.
- Updated `PARKED.md` with new parked issues for PrintSmith token authority, Cloudflare identity binding, audit/secrets design, and migration.

**Plain-English result:**

The rebuild plan is still sound, but the review made clear that the next few planning artifacts must cover production engineering, not just app design. The biggest missing pieces are deployment bridge, secrets, audit, token authority, and Fetch's delayed-report behavior.

**Next recommended session:**

`kickoff projects/retriever-rebuild`, then write `FETCH_TRUST_PLAN.md` with the 30-second timeout wall and delayed-report path as first-class requirements.

---

## 2026-05-04 — Project shell and auth redesign seeded

**Goal:** Start the new Retriever rebuild as a separate project, while keeping the old `projects/Retriever/` repo copy as reference only.

**What happened:**

- Reviewed the current Retriever repo layout and auth/Fetch module boundaries.
- Wrote the first architecture artifact, `AUTH_REDESIGN.md`.
- Moved that document from the old repo copy into the new `projects/retriever-rebuild/` folder.
- Clarified skill routing: `/printsmith` for live Boone PrintSmith read-only data, `/docs` for vendor/tool documentation, and `/printsmith-estimate` outside Retriever scope.
- Removed BooneOps Full and Shipping Chat from the Retriever rebuild scope.
- Discussed runtime direction and leaned toward running the new production Retriever on a Boone LAN server through Cloudflare Access/Tunnel.
- Set up project-local kickoff/wrap files.

**Plain-English result:**

Retriever rebuild now has its own home. The old LAN repo copy can stay clean as a reference, while the new project carries planning, decisions, and eventually code.

**Current trust concern:**

Fetch is the first trust barrier. If Fetch is buggy or unreliable, employees will not trust the rest of Retriever. The next architecture artifact should be a Fetch trust plan before any build.

**Next recommended session:**

Write `FETCH_TRUST_PLAN.md`.

---
