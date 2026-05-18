# retriever-rebuild: Living Plan

This is the cross-session project dashboard. `SESSION-LOG.md` records what happened. `PARKED.md` holds side ideas. `AUTH_REDESIGN.md` is the first architecture artifact.

## Current Phase

**Wiki module live; PrePress side-by-side migration live; Fetch pilot remains narrow**

Plain English: **Retriever Wiki is live as a small new module** at `/wiki/`, with a **Wiki / W** sidebar entry, prominent SweetProcess procedure links, Work Instructions, Quality & ISO, Security Posture, and General Knowledge sections. The catalog schema and document drill-down route exist. The next piece is the dynamic sync/summarization workflow so Google Drive ISO / Work Instruction changes refresh controlled Wiki records without exposing raw ISO documents to normal readers. Final verified production SHA: **`777886d4d63863bfab5ccb360c5b37203dd228ed`** on **`BGGOL-VESKO01`**; `/health/live` returned **200 OK**; `/wiki/` was verified live behind Cloudflare Access; local tests passed **315**.

**PrePress is also live enough for Scott-side testing** while old Retriever stays up as the reference and parallel production surface. The rebuild reads the same PrePress/MIS data, uses the new auth/location matrix, shows the WIP table, expands invoice parts, and saves PrintSmith job tickets through the old Retriever token authority. Keep old Retriever PrePress live until side-by-side read/write behavior is proven.

**Fetch remains a live pilot — keep flags narrow (no broad rollout).**

Plain English: **push-to-`main` deploy** on the Windows runner is routine; **post-deploy feedback** is **green** after version stamping, broker URL, runner permissions, and related fixes. **`RetrieverRebuild`** on **`8810`** has been **verified** with **`FETCH_ENABLED`**, BooneOps **`BOONEOPS_BROKER_ENABLED`**, **`FETCH_GENERAL_QUESTIONS_ENABLED=false`**, smoke aligned to pilot expectations, **legacy `Retriever` on `8000`** read-only-checked and still serving, **`/fetch` protected** until Access session, and broker path **healthy** including **Retriever broker error observability** and BooneOps **correlation** logging.

Recent **employee-facing Fetch** work improved **readable answers** (Markdown + sanitize), **per-message status**, **metadata cards**, **viewport-stable layout**, **scroll/optimistic ask**, **CSS cache busting**, and **PrintSmith typo routing** — deployed through commits **`0e4f494`** / **`085b082`** (see **`SESSION-LOG.md`** 2026-05-12).

Latest pilot polish shipped **safe pipe tables**, **compact metadata/source cards**, **downloadable artifacts**, **context-aware report follow-ups**, **authenticated BooneOps artifact download proxying**, **local HTML exports**, and **styled Excel exports**. Live Chrome verified deployed Retriever **`8867ff6`** on **`BGGOL-VESKO01`** and BooneOps broker styled Excel commit **`8bd5db0e`** after broker restart.

**2026-05-17 (broker):** **Fetch gateway-first** — BooneOps broker defaults **`BOONEOPS_FETCH_GATEWAY_ONLY`** on so Retriever Fetch skips broker-local SQL list + chart/PDF paths and answers via the **same OpenClaw gateway agent** as other forwarded BooneOps turns; rollback = env **`false`** + broker restart. See **`projects/booneops-bots/BROKER.md`** and **`docs/DISCORD_FETCH_PARITY.md`**.

**2026-05-15 (evening):** Shipped **honest per-answer status** (friendly model + raw slug from broker when the gateway exposes structured **`gatewayModelId`**; **not recorded** when it does not), **thread load hint** (char estimate + “not a model context %” + conservative new-chat nudge), broker **`/docs` Switch grounding** prompt lines + **gateway telemetry** on broker JSON and **`booneops.message.complete`** logs, **`runGatewayPrompt`** return shape fix for report planners. **Retriever `35a5d45`** verified on production **`/version`**; **LordTate `278ec9a5`** broker on Whitaker **pulled + LaunchAgent kickstart**; operator reports pilot **“in a good place.”**

**Do not widen flags** until **`/docs`-style answers** stay **summarized and well-attributed**; **`FETCH_TRUST_PLAN.md`** pilot notes stay the guide.

Architecture artifacts remain authoritative for auth, Fetch trust, and runtime boundaries.

## Current Status

Completed:

- Added the first Wiki sync command foundation: `python3 -m app.wiki.sync --internal-wiki` and `python3 -m app.wiki.sync --drive-inventory path/to/export.json|csv`.
- Added idempotent Wiki source/document/link upserts and sync-run tracking for `wiki_sources`, `wiki_documents`, `wiki_links`, and `wiki_sync_runs`.
- Made synced internal-wiki SweetProcess links feed `/wiki/` when present, with the built-in procedure list as fallback.
- Added Drive inventory draft-card classification while keeping raw source links admin-only.
- Added `POST /wiki/sync/source-inventory`, gated by `WIKI_SYNC_ENABLED` and `WIKI_SYNC_TOKEN`, so Retriever can ingest an OpenClaw-built Drive inventory from inside the LAN/MySQL boundary.
- Added outer OpenClaw script `scripts/retriever-wiki-sync.js`; dry-run inventories the `Final Boone` Drive root into `.wiki-sync/` and found 1,362 files.
- Registered disabled OpenClaw cron job `retriever-wiki-sync` (`df821699-0a39-4b86-bb34-d6c94c8858cf`) for 5:30 AM ET daily.
- Added Retriever **Wiki** as a small shared-shell module with `/wiki/`, left-rail **W**, and active-user access.
- Added Wiki catalog migration and repository support for sources, documents, versions, sections, links, and sync runs.
- Added Wiki document drill-down routes and fallback cards for early ISO / Work Instruction examples.
- Promoted the internal-wiki **SweetProcess procedure links** to the top of Wiki because they are daily-use operational links.
- Shaped Wiki into the current intended sections: **SweetProcess Procedures**, **Work Instructions**, **Quality & ISO**, **Security Posture**, and **General Knowledge**.
- Verified production deploy of Wiki commit **`777886d4d63863bfab5ccb360c5b37203dd228ed`** and local suite **`315 passed`**.
- Created a fresh rebuild project at `projects/retriever-rebuild/`.
- Moved the auth redesign out of `projects/Retriever/` so the old repo copy remains a reference.
- Wrote `AUTH_REDESIGN.md`, covering Cloudflare Access, pending users, Retriever roles/capabilities, BooneOps Light/Medium, audit levels, and action classes.
- Clarified that `/printsmith` is the live Boone read-only PrintSmith path for Retriever, `/docs` is the vendor/tool docs path, and `/printsmith-estimate` is outside Retriever scope.
- Removed BooneOps Full and Shipping Chat from the Retriever rebuild scope.
- Reassessed runtime direction: because Proofs, DSF, PrePress, PrintSmith, Switch, and file shares are LAN-heavy, the likely production runtime is a Boone LAN server exposed via Cloudflare Access/Tunnel, not a cloud-only host.
- Ran a read-only Opus 4.7 senior-engineer review and captured the findings in `REVIEW-2026-05-04-OPUS.md`.
- Updated kickoff/rules so future sessions load active architecture artifacts, not only kickoff/plan/parked/session log.
- Wrote `FETCH_TRUST_PLAN.md`, covering explicit Fetch routing, the 30-second chat wall, Cursor-like delayed-report progress, failure states, privacy boundaries, health checks, and the useful Fetch features to build without treating old Fetch as a compatibility target.
- Added Cursor security guidance to `DEPLOYMENT_BRIDGE.md`, `SECRETS_HANDLING.md`, `AUDIT_LOG_DESIGN.md`, `WEBHOOK_AND_BROKER_AUTH.md`, and `BUILD_CODE_LAYOUT.md` so Cursor is treated as build control, not production runtime or secret storage.
- Filled in `DEPLOYMENT_BRIDGE.md` with a concrete first deployment model: Boone LAN runtime, `retriever-next.boonegraphics.net` staging hostname, `retriever-web.service`, `/opt`/`/etc`/`/var/log` layout, server-pull deploy, rollback, health/version endpoints, smoke tests, Cloudflare/Tailscale responsibilities, and old/new cutover gates.
- Wrote `RUNTIME_NOTES.md`, deciding that a sibling Boone LAN Linux app VM is the preferred first host while `bggol-vesko01` stays live old Retriever and PrintSmith token authority during staging.
- Wrote `PRINTSMITH_TOKEN_AUTHORITY.md`, preserving old Retriever's `/api/printsmith-token` and `/api/printsmith-token/invalidate` authority contract before cutover.
- Wrote `VM_SETUP_PLAN.md`, using `bggol-retriever01` as the working Boone LAN Linux app VM name and defining host ownership, Cloudflare/Tailscale, deploy, rollback, MySQL access, secrets, and backup expectations.
- Wrote `RETRIEVER_CORE_SCHEMA.md`, defining the first MySQL `retriever_core` schema for Cloudflare-linked users, roles, capabilities, module access, sessions, settings, delayed reports, artifacts, audit events, and migrations.
- Wrote `CONFIG_AND_HEALTH_CONTRACT.md`, defining the first `.env.example` shape, startup validation rules, `/health/*`, `/version`, dependency names, smoke tests, and redaction rules.
- Wrote `AUTH_SHELL_BUILD_PLAN.md`, choosing Python/FastAPI with server-rendered HTML as the first stack and breaking the auth shell into build slices.
- Updated `BUILD_CODE_LAYOUT.md` so the first code scaffold has a concrete FastAPI layout instead of an open framework choice.
- Created the first FastAPI scaffold with `pyproject.toml`, `.env.example`, `app/`, `migrations/`, `tests/`, `deploy/`, config validation, health/version routes, disabled Fetch placeholder, initial MySQL migration SQL, and smoke/systemd examples.
- Set up a local `.venv` for scaffold verification and added project `.gitignore` rules so environment/cache files stay out of Git.
- Added DB-backed repository scaffolding for users, sessions, settings, and audit events.
- Replaced the local-only user placeholder with a flow that uses `retriever_core` repositories when MySQL config is present, while keeping local scaffold fallback for development.
- Added tests for pending-user creation, seeded admin profile creation, settings/audit/session repositories, migration contents, config validation, health output, and Cloudflare local identity fixtures.
- Implemented Cloudflare Access JWT validation against configured JWKS URL and audience, with tests for valid identity, wrong audience, missing email, and spoofed-header rejection.
- Added a migration runner for SQL migrations and seed files.
- Updated DB health behavior so local missing MySQL config is `disabled`, configured reachable MySQL is `ok`, and configured unreachable MySQL is `failed`.
- Added repository methods for activating, suspending, blocking, role assignment, BooneOps level assignment, module access changes, and capability grants/revokes.
- Added admin action service methods that call those repositories, revoke sessions on suspend/block, and write strict audit events.
- Wired admin POST routes for user approval/suspend/block and role/module/capability/BooneOps assignment.
- Added tests for admin actions, audit writes, session revocation, and user assignment behavior.
- Expanded the admin users page with approve/block controls and assignment forms for role, BooneOps level, Fetch module access, and Fetch capability.
- Added route-level tests for pending user page, seeded admin access, forbidden non-admin admin access, pending-user listing, and admin activation POST.
- Updated template rendering calls to current Starlette/FastAPI style so route tests run without deprecation warnings.
- Added opaque `retriever_session` cookie issuance backed by `retriever_core.sessions`.
- Added active session reuse/touch behavior, logout/session revocation, and suspended/blocked route denial.
- Added route and repository tests for session creation, reuse, revocation, and suspended/blocked access denial.
- Wrote `LOCAL_RUNBOOK.md` for local setup, test, server start, route smoke checks, migration command, and current "do not do yet" guardrails.
- Ran first local smoke against `127.0.0.1:8810`: `/`, `/admin/users`, `/health/live`, `/health/ready`, `/health/deep`, `/version`, and expected disabled `/fetch` behavior all passed.
- Ran packaged `deploy/smoke.sh` successfully against the local server.
- Ran Impeccable teach/shape for Retriever shared layout.
- Wrote `PRODUCT.md` with product register, users, purpose, personality, anti-references, principles, and accessibility goals.
- Wrote `SHARED_LAYOUT_SHAPE.md` with the confirmed "old Retriever refined" shared-shell brief.
- Replaced standalone scaffold templates with a shared Retriever layout: header, left sidebar, content area, Admin as a normal sidebar module, disabled Fetch in the same shell, and consistent pending/admin/home pages.
- Reworked `app/static/app.css` into a restrained product UI system using OKLCH tokens, tinted neutrals, one primary accent, clear focus states, responsive shell behavior, and sharper operational spacing.
- Smoked the polished shell locally: `/`, `/admin/users`, `/fetch`, `/health/live`, `/health/ready`, `/version` all passed with expected statuses.
- Inspected old Fetch's UI structure and captured the new visual/layout target in `FETCH_UI_CONTINUITY.md`.
- Replaced the plain disabled Fetch notice with a disabled/stubbed Fetch skeleton behind the shared shell, including current-Fetch-style conversation rail, rename UI shape, thread preview, composer, suggestions, status footer, delayed-report preview, sources, and failure state cards.
- Added route coverage for the disabled Fetch skeleton and reran the full local test suite: 48 tests passed.
- Ran Impeccable critique and applied distill/clarify/polish pass: simplified disabled Fetch screen to old-Fetch empty state plus Thread Reports strip; moved trust-state examples behind progressive disclosure; clarified disabled controls with inline copy; cleaned up Impeccable anti-patterns.
- Applied Boone brand colors from brand guide page 13: sidebar Boone Blue `#5eaee0`, active nav Boone Red `#a1252b`, user message bubbles blue, Ask Fetch button red.
- Added collapsible outer module sidebar with compact initials when collapsed; added Retriever logo to main header/center pane; added light/dark theme toggle persisted to localStorage.
- Resolved deployment hostname: `retriever.boonegraphics.net` is the live hostname from first deploy. No staging subdomain needed; old Retriever is LAN-only with no Cloudflare presence.
- Created new standalone git repo for `projects/retriever-rebuild/`, added SSH remote, and pushed initial commit (`965a75c`) to `https://github.com/bobtucker1129/Retriever`.
- Corrected deployment target after inspecting the old Retriever runtime: `bggol-vesko01` is Windows Server, old Retriever runs as the `Retriever` NSSM service on port `8000`, and new Retriever deploys beside it as `RetrieverRebuild` on port `8810`.
- Replaced the discarded Linux deploy artifacts with Windows-native PowerShell/NSSM deploy scripts and pushed the proven deploy fixes through commit `ed41f94`.
- Configured Cloudflare Zero Trust for `retriever.boonegraphics.net`: team domain `boonegraphics.cloudflareaccess.com`, Access application/policy for Boone employees, tunnel `bf859516-9782-4c53-9098-1923709b4028`, and `cloudflared` Windows service running on `bggol-vesko01`.
- Created MySQL schema/user for `retriever_core` on Boone MySQL and successfully applied `0001_retriever_core_auth.sql` plus `0001_seed_auth_shell.sql` during first deploy.
- Successfully staged release `ed41f94261910256edc71d104adcabf7dd00324c` at `D:\retriever-rebuild\current`; next step is installing and starting the `RetrieverRebuild` Windows service.
- Installed `RetrieverRebuild` as an NSSM Windows service on `bggol-vesko01`; service started successfully and `/health/live` returned 200 on port `8810`.
- Local smoke passed on `bggol-vesko01`: `/health/live`, `/health/ready`, `/version`, version metadata, no secret leakage, and disabled `/fetch` all passed (`8 passed, 0 failed`).
- Fixed the `cloudflared` Windows service command so it runs `C:\cloudflared\cloudflared.exe --config C:\cloudflared\config.yml tunnel run retriever`; browser test now shows Cloudflare Access first, then reaches Retriever successfully.
- Disabled old Fetch in the old Retriever runtime, clearing the duplicate Fetch surface while old Retriever continues to own PrePress, DSF, and PrintSmith token authority.
- Built the first real new-Fetch slice: DB-backed conversation creation, listing, selection, rename, soft delete, message storage primitives, Fetch access gating, and a disabled-safe shell that keeps model/tool routing locked.
- Built the first safe ask-path skeleton: ask submission is gated by active user, Fetch shell access, and `FETCH_ENABLED`; enabled asks write a deterministic stub reply only, with no model, PrintSmith, docs, BooneOps, upload, or delayed-report calls.
- Hardened Windows deploy/smoke prep for the Fetch release: migration `0002_fetch_conversations` checks, explicit `RetrieverRebuild`/port `8810` guardrails, Fetch/model-off smoke assertions, and a read-only old Retriever port `8000` liveness check.
- Verified the new Fetch slices locally: 65 tests passed, local route smoke passed, and edited files have no linter errors.
- Added a gated **ask path** (`POST /fetch/conversations/{id}/ask`): requires active Fetch shell access plus `FETCH_ENABLED` (env). When Fetch is off, the route redirects without persisting a user message. When Fetch is on but provider routing is not wired, it saves the user turn and appends a fixed stub assistant reply—no outbound model or tool calls.
- **Fetch local routing (stub):** `classify_fetch_intent` assigns deterministic route labels (`local`, slash `help`/`sources`/`health`, `email_cleanup`, `printsmith_candidate`, `docs_candidate`, `general_candidate`, `blocked_write`, `unknown`). The ask handler persists those labels as `route_key` and returns route-specific offline copy; still no providers, PrintSmith, docs APIs, BooneOps, uploads, or web calls.
- Deployed commit `89ecd60` to `RetrieverRebuild` on `bggol-vesko01`; `smoke.ps1` passed, `RetrieverRebuild` is running, and legacy `Retriever` is still running.
- **BooneOps broker (Phase 1, default off):** Optional `BOONEOPS_BROKER_ENABLED` path calls `POST /v1/booneops/message` with bearer token and `X-BooneOps-Signature: sha256=…` over the raw JSON body per `projects/booneops-bots` contract. When enabled with `FETCH_ENABLED`, `printsmith_candidate` and `docs_candidate` ask turns use the broker; `general_candidate` stays on the stub unless `FETCH_GENERAL_QUESTIONS_ENABLED`. Retriever maps users to broker `role`/`botId` from `is_admin`, `booneops_level` (`medium` → super bot), and otherwise production bot. Tests use mocked HTTP only.
- **Live pilot (2026-05-11, constrained):** Verified deploy **`4789cc3`** (“Add Fetch broker error observability.”), GitHub Actions run **25693145755**, `/version` matches SHA, smoke with **`RETRIEVER_SMOKE_EXPECT_FETCH_ENABLED=true`** aligned to env, **broker health OK**, **`/fetch`** unauthenticated → **401**, legacy **8000** liveness OK. BooneOps **`0b21f1bb`** adds broker **correlation** logging; Whitaker broker **`.env.broker`** corrected from Linux-default OpenClaw paths to **local gateway URL + token + device identity files** (`~/.openclaw/.gateway_token` mode **600**) — schedule **gateway token rotation** after credential exposure during troubleshooting (no secret values in docs). Product gaps: raw docs answers need **summaries/sources**; long-term Cursor-like **thinking/progress UX** roadmap; persona **BooneOps**, not private LordTate.
- **Fetch pilot UX (2026-05-12):** Markdown/safe HTML for assistant bubbles, compact **model/context** status line per answer, optional **metadata** on messages for **source/artifact/status** cards, **optimistic ask** + anchored scroll, **viewport-height** resilient layout/CSS, stylesheet **cache-bust** (`?v=git_sha`) and **absolute static** mount, **PrintSmith typo + time-context** routing improvements; commits through **`085b082`** incl. layout/CSS delivery fixes (Actions e.g. **25705235002**).
- **Auto deploy via GitHub:** Self-hosted Windows runner on `bggol-vesko01` runs **`.github/workflows/deploy-retriever-rebuild-windows.yml`** on **every push to `main`** (and manual dispatch when operators need migration or legacy-probe toggles). Production secrets stay on-server; the workflow only checks out `deploy/` and invokes `D:\retriever-rebuild\bin\deploy.ps1`. Documented in **`docs/runbooks/github-actions-retriever-rebuild-deploy.md`**.
- **Fetch answer/readiness polish (2026-05-12):** Deployed **`9136fa2`**, **`8edbf72`**, **`afc2570`**, **`60dd1ad`**, **`baf1e48`**, and **`8867ff6`** to Retriever. BooneOps broker restarted on Whitaker with **`8bd5db0e`**. Results: Markdown pipe tables render as real tables; dated job/work-order questions route to PrintSmith/report handling; “export that” follow-ups inherit successful report context; HTML exports are generated locally with safe same-origin links; PDF/Excel/CSV broker artifacts download through Retriever instead of leaking broker paths or downloading JSON; fuzzy phrases like “fancy up the Excel file” now regenerate styled Excel using preserved `reportContext`.

## Active Architecture Artifacts

- `AUTH_REDESIGN.md`: current auth and capability model.
- `REVIEW-2026-05-04-OPUS.md`: risk review that must inform Fetch, deployment, runtime, secrets, audit, and migration planning.
- `FETCH_TRUST_PLAN.md`: current Fetch routing, trust, timeout, delayed-report, privacy, health, and feature-preservation policy.
- `DEPLOYMENT_BRIDGE.md`: concrete first deployment bridge from Cursor/OpenClaw to Boone runtime, including host/service layout, deploy, rollback, health, logs, Cloudflare/Tailscale, and coexistence gates.
- `SECRETS_HANDLING.md`: secret classes, Cursor visibility rules, production storage expectations, and rotation posture.
- `AUDIT_LOG_DESIGN.md`: app audit levels plus development/agent audit trail separation.
- `WEBHOOK_AND_BROKER_AUTH.md`: machine-to-machine auth rules and Cursor/MCP credential separation.
- `BUILD_CODE_LAYOUT.md`: repo/config layout rules that let Cursor agents work without production secrets.
- `RUNTIME_NOTES.md`: first runtime host decision, VM requirements, dependency map, identity/network rules, health/smoke expectations, and cutover gates.
- `PRINTSMITH_TOKEN_AUTHORITY.md`: old/new PrintSmith REST token authority contract, staging posture, cutover options, secrets, audit, and verification checklist.
- `VM_SETUP_PLAN.md`: sibling Boone LAN app VM setup plan, with `bggol-retriever01` as the working host name.
- `RETRIEVER_CORE_SCHEMA.md`: first MySQL schema plan for new Retriever app state.
- `CONFIG_AND_HEALTH_CONTRACT.md`: environment, validation, health, version, smoke, and redaction contract.
- `AUTH_SHELL_BUILD_PLAN.md`: selected first framework/runtime and build slices for the Cloudflare auth shell.
- `LOCAL_RUNBOOK.md`: local test/start/smoke instructions and first browser-smoke path.
- `deploy/WINDOWS_FETCH_RELEASE.md`: Windows production deploy for **RetrieverRebuild**, migration **0002**, **`smoke.ps1`**, coexistence with port **8000**, **`FETCH_ENABLED`** vs validation, BooneOps **`BOONEOPS_*`** / **`FETCH_GENERAL_QUESTIONS_ENABLED`** notes, plus future model enablement checklist.
- `docs/runbooks/booneops-broker-fetch-windows.md`: **`GET /health`** on broker, **`BOONEOPS_*`** / **`AppSettings`**, **`bggol-vesko01`** PowerShell smoke, **8810** vs legacy **8000**.
- `docs/runbooks/automated-feedback-bridge-windows.md`: staged **post-deploy feedback** roadmap (localhost artifact → Cloudflare Access service-token checks on-box → Fetch/broker smoke → agent-readable summaries); **Windows** and **legacy `8000`** guardrails.
- `docs/runbooks/github-actions-retriever-rebuild-deploy.md`: self-hosted runner, **push + manual** workflow, preflight, coexistence with **`deploy/WINDOWS_FETCH_RELEASE.md`**.
- `PRODUCT.md`: Impeccable product context for Retriever UI work.
- `SHARED_LAYOUT_SHAPE.md`: confirmed Impeccable shape brief for the shared app shell.
- `FETCH_UI_CONTINUITY.md`: current Fetch visual/layout continuity target for the first new Fetch skeleton.

## Active Decisions

Resolved:

- **Fetch pilot — persona:** Retriever Fetch should present as **BooneOps** (employee-facing operations identity), not private LordTate.
- `projects/Retriever/` is the old LAN repo reference copy, not the rebuild workspace.
- `projects/retriever-rebuild/` is the planning/build home for the new Retriever.
- Old Fetch on `bggol-vesko01` should be turned off via a feature flag. Nobody uses it, and disabling it clears the way for the new Fetch without confusing users.
- Automated CI/CD deployments and staging validations are a core goal. **Done for first production lane:** a self-hosted Windows GitHub Actions runner on `bggol-vesko01` deploys `RetrieverRebuild` on **push to `main`**, with optional **manual dispatch** for migrations and controlled **`skip_legacy_liveness`**. (A dedicated staging site may follow later if needed.) **Post-deploy feedback** for agents (artifact / bounded bundle: health, smoke, version lineage, legacy probe) is **green after** stamping, broker URL, and runner permission fixes (**2026-05-11 pilot**); **Phases B–D** (e.g., on-box Access-token public URL cadence—see **`docs/runbooks/automated-feedback-bridge-windows.md`**) proceed as rollout needs them.
- Cloudflare Access should protect `retriever.boonegraphics.net` for everyone.
- New Retriever should not expose old LAN modules through the new domain until they are rebuilt.
- Fetch comes first, but auth comes before Fetch.
- Old Fetch does not work well and nobody depends on it today; new Fetch should be built first without working around old Fetch compatibility.
- BooneOps levels inside Retriever stop at Light and Medium.
- Owner/operator work stays in Cursor, Telegram, or LordTate environments.
- DSF should be the first write-heavy module behind a future LAN action service.
- Heavy Fetch PrintSmith/DSF list and export work should switch to a delayed-report progress card before the 30-second chat wall, not wait for a backend timeout.
- PrePress stays on old Retriever until the new action model is proven.
- Cursor is part of the build/review chain, not the production Retriever runtime, production secret store, or direct production action path.
- New Retriever uses `retriever.boonegraphics.net` directly from first deploy. No staging subdomain needed: old Retriever runs on a LAN IP only and has no Cloudflare presence, so there is no DNS conflict.
- VM provisioning was impractical. New Retriever will run on `bggol-vesko01` alongside old Retriever. Old Retriever keeps its current port and PrintSmith token authority. New Retriever binds to `127.0.0.1:8810` only.
- `bggol-vesko01` stays on its LAN IP running old Retriever and PrintSmith token authority until new Retriever PrePress is ready to take over that token.
- New Retriever first deploy uses Windows Server/NSSM/PowerShell on `bggol-vesko01`, not Linux/systemd. Do not recreate `/opt`, `/etc`, bash, or systemd deploy paths for this launch.
- Deploy-time checks are import check, production config validation, optional migration, service health, and smoke. Tests remain a local/pre-push check because they are written for local config, not production env.
- Deploy scripts must clear inherited old Retriever env vars (`FETCH_*`, `MODEL_*`, `ANTHROPIC_*`, `BOONEOPS_*`, `PRINTSMITH_*`) before loading `D:\retriever-rebuild\env\retriever.env`.
- New Retriever must not generate its own `LordTate` PrintSmith REST token while old Retriever is still the authority.
- `retriever.boonegraphics.net` is the live hostname from first deploy. No staging subdomain is needed because old Retriever is LAN-only with no Cloudflare presence.
- New Retriever app state should live in Boone MySQL, using the existing `retriever_core` schema as the shared Retriever app-state home.
- Old Retriever keeps first dibs on the shared PrintSmith token at first launch. New Retriever becomes primary only when new Retriever PrePress is migrated and ready to own that token.
- Working VM name is `bggol-retriever01`, unless Boone IT requires a different naming convention.
- First app-state schema is `retriever_core`; old Fetch conversations/private library data do not migrate by default.
- First health contract uses `/health/live`, `/health/ready`, `/health/deep`, and `/version`.
- First app stack is Python/FastAPI with server-rendered HTML and small HTMX-style interactions.
- First config validation implementation should use `pydantic-settings`.
- Local scaffold currently runs under Python 3.9 because that is the Python available on this Mac; the Boone VM Python version remains open.
- MySQL client is `mysql-connector-python` for the first scaffold, matching the old Retriever direction and keeping the first DB layer simple.
- Admin is a normal Retriever module in the shared app shell, visible in the left sidebar for admins. It should not become a separate-looking admin site.
- Shared layout direction is "old Retriever refined": keep the operational left-sidebar app feel, clean up hierarchy, spacing, and component consistency.
- UI personality is modern, sharp, efficient. Avoid generic AI/SaaS and consumer-chatbot aesthetics.
- Visual continuity should stay close to old Retriever. The rebuild should feel like a sharper, cleaner version of the tool employees already know, not a new identity.
- Fetch must preserve a left-side conversation sidebar/history, including the ability to rename conversations.
- Fetch conversation rename should work like current Fetch.
- Fetch sidebar navigation and `/fetch` shell access gate on module `fetch` or `fetch.access` capability plus active user status. `FETCH_ENABLED` remains tied to model routing and composer unlock; conversation CRUD can use MySQL while the model stays off.
- Fetch should show the active context-window level and current model to all users, similar to OpenClaw's visible status pattern.
- Context-window display should include both a simple amount/percentage and an operational state such as low, medium, high, or near full.
- Fetch should keep the current Fetch layout, size, left-side behavior, and top-logo/header feel while improving the visuals with modestly more color and a little more font variation.
- Old Fetch visual inspection is captured in `FETCH_UI_CONTINUITY.md`; this is now the design bridge into the first Fetch skeleton.
- Fetch artifact downloads should go through Retriever-authenticated same-origin links. New BooneOps artifacts use `/fetch/artifacts/broker/{artifactId}`; existing `/v1/booneops/artifacts/{artifactId}` links are kept working through a compatibility proxy.
- Fetch can generate local sanitized HTML exports from a previous successful answer. PDF/Excel/CSV still come from BooneOps broker artifacts.
- Follow-up routing should be human-friendly when recent context is clearly report/export work. Phrases such as “fancy up the Excel file,” “make the spreadsheet prettier,” or “add colorful headers” should inherit the recent successful report context instead of going to the general stub.
- Styled Excel is now a BooneOps capability. Styling is additive and generates a new artifact; old downloaded files are not mutated in place.

Open:

- **Discord–Fetch behavioral parity (active program):** Foundation in **`projects/booneops-bots`**: shared **`isRetrieverFetchBrokerRequest`**, neutral **non-Fetch** transcript labels, MCP **`source`** metadata, **`lib/parity-outcome.cjs`** + harness tests, **`docs/DISCORD_FETCH_PARITY.md`**. **LordTate `main` commits `6ac5568b` / `88f8e2e3`:** **`booneops.message.complete`** now emits **`traceV`** + **`parity*`** fields (conversation id, session source, route, action/error fingerprint); Retriever **`BooneOps broker turn`** log line adds **gateway model slug**, **error codes**, **artifact count** for grep alignment. **Still to do:** tier/timeouts vs Discord, user-facing error copy parity, golden / live harness runs, Discord ingest if the envelope must be built there, OpenClaw **`agent.wait`** model field if **“not recorded”** persists; **operator:** pull broker on Whitaker + restart LaunchAgent; Retriever prod via **Retriever** repo deploy when ready.
- **Gateway structured model (residual):** Fetch shows **friendly name + raw slug** when the broker returns **`gatewayModelId`** from **structured** WebSocket payloads; if operators still see **“not recorded”**, extend **OpenClaw `agent.wait` / stream events** to emit a stable **`model` / `modelId`** field (no parsing answer text).
- **Fetch pilot — `/docs` presentation:** Confirmed live pilot: answers still skew **raw / hard to skim**; **summary + source cards / cleanup** is the **next engineering priority** before any broad rollout (`FETCH_TRUST_PLAN.md` pilot section).
- **OpenClaw gateway credential:** **Rotated / closed** (operator confirmation 2026-05-14); do not paste gateway tokens into chat or agent logs.
- **Fetch artifact lifecycle:** Local HTML exports and broker artifacts now work through Retriever links, but retention/cleanup policy for generated HTML files and long-lived broker artifacts still needs an operator decision.
- **Fetch answer snapshot PDF (product):** **Not this sprint.** BooneOps-owned PDFs remain chart/report/runtime exports. A separate “snapshot this assistant answer as PDF” path would be Retriever-local product work only after an explicit go decision.
- **RetrieverOps / Fetch-specific broker lane:** Deferred direction—**separate** lane (logs, limits, no instruction-update/write actions, less competition with chat surfaces)—**not** “clone BooneOps now.” See **`PARKED.md`**.
- **Automated feedback:** exact **artifact format** and size cap for Phase A; whether Phase B public URL checks run on **every push** or a slower cadence; **rotation owner** for the Cloudflare Access service token on `bggol-vesko01`.
- Whether general outside-world Fetch answers are enabled for all active users at launch or only beta users.
- How to bind Cloudflare identity safely without allowing direct LAN header spoofing.
- Tailscale is required for first Fetch launch if Fetch keeps the existing BooneOps broker/report path; later, decide whether that broker moves closer to Retriever.
- Whether Boone IT accepts `bggol-retriever01` or requires a different VM name.
- What exact event marks new Retriever PrePress ready to become the primary PrintSmith token authority.
- Whether Boone MySQL supports JSON columns for the schema as written, or whether JSON fields should be `LONGTEXT` with app validation.
- Which model provider/default model are approved for first Fetch build.
- Which Python version should be pinned on `bggol-retriever01`.
- Whether `/health/deep` requires admin session, Cloudflare service token, or both.

## Fetch foundation — operator notes (Windows)

Use **`deploy/WINDOWS_FETCH_RELEASE.md`** as the single place for deploy order, migration **`0002`**, smoke expectations, coexistence rules, and the **`FETCH_ENABLED`** warning.

- **Where it runs:** **`RetrieverRebuild`** (NSSM) on **`bggol-vesko01`**, **`127.0.0.1:8810`**, public entry **`https://retriever.boonegraphics.net`** via Cloudflare Access and Tunnel.
- **What stays on the old service:** **`Retriever`** on port **`8000`** continues PrePress, DSF, and PrintSmith REST token authority until an explicit cutover; Fetch releases must not touch that service.
- **BooneOps broker (docs-first):** **`docs/runbooks/booneops-broker-fetch-windows.md`** walks **`BOONEOPS_BROKER_ENABLED`**, **`BOONEOPS_BROKER_URL`**, **`BOONEOPS_BROKER_BEARER_TOKEN`**, **`BOONEOPS_BROKER_HMAC_SECRET`**, optional **`BOONEOPS_BROKER_REQUIRES_TAILSCALE`**, broker **`GET /health`** from **`bggol-vesko01`**, Fetch **`/health/ready`** on **`8810`**, and keeping **`FETCH_ENABLED=false`** and **`FETCH_GENERAL_QUESTIONS_ENABLED=false`** until deliberate rollout. Goal: **`#printsmith`-equivalent BooneOps** over broker, **not** general internet LLM.
- **After auto deploy:** **`docs/runbooks/automated-feedback-bridge-windows.md`** is the staged plan so agents get **health/smoke/version/legacy-probe** feedback (then public URL and Fetch smoke) **without clipboard handoff**.
- **What “Fetch foundation” means:** conversation list/create/rename/delete in MySQL (**`0002`**), optional **stub** ask only when **`FETCH_ENABLED=true`** (still no real model or tool routing). **`FETCH_ENABLED=false`** remains the recommended production default: conversation CRUD still works; the ask composer stays off; post-deploy **`smoke.ps1`** expects **`fetch`** and **`modelProvider`** **disabled** in **`/health/ready`**. If **`FETCH_ENABLED=true`**, startup validation **still requires** model env vars even though code only runs the stub—see the runbook.
- **Before real models/tools:** follow the enablement checklist at the bottom of **`deploy/WINDOWS_FETCH_RELEASE.md`** together with **`FETCH_TRUST_PLAN.md`**.

## Next Recommended Session

**Wiki sync pipeline — make the live shell dynamic and useful.**

Plain English: the Wiki shell, categories, SweetProcess links, catalog tables, drill-down routes, first sync command foundation, and disabled OpenClaw cron bridge are in place. Direct DB sync from Whitaker is not viable because Boone MySQL is LAN-only, so the intended path is OpenClaw Drive inventory -> Retriever ingest endpoint -> Retriever writes `retriever_core`. The next session should deploy/enable that bridge, then create reviewed summary workflow and freshness visibility without letting normal users click through to raw ISO documents.

Immediate checklist:

1. Verify production **`/version`** is still **`777886d4d63863bfab5ccb360c5b37203dd228ed`** or newer, then **`/health/live`**.
2. Open **`https://retriever.boonegraphics.net/wiki/`** in Chrome after Cloudflare Access.
3. Deploy the Retriever sync endpoint, then set production env:
   - `WIKI_SYNC_ENABLED=true`
   - `WIKI_SYNC_TOKEN=<strong secret>`
4. Set matching OpenClaw env for cron:
   - `RETRIEVER_WIKI_SYNC_TOKEN` or `WIKI_SYNC_TOKEN`
   - optional `RETRIEVER_WIKI_CF_SERVICE_TOKEN` if Cloudflare Access blocks the POST
5. Run the disabled cron once:
   - `openclaw cron run df821699-0a39-4b86-bb34-d6c94c8858cf --expect-final --timeout 900000`
6. Enable after a clean run:
   - `openclaw cron enable retriever-wiki-sync`
7. Treat Google Drive and `https://www.boonegraphics.net/internal-wiki` as source systems; store controlled summaries and metadata in Retriever.
8. Do **not** expose raw ISO document links to normal Wiki readers. Source file links should be admin-only/hidden unless Master Tate explicitly approves otherwise.
9. Keep Fetch untouched except for a later tiny feature-flagged read-only Wiki search adapter.
10. Run **`python3 -m pytest`** before push; push to `main`; wait for Windows deploy; verify live behavior after deploy.

**PrePress live follow-up remains active when Scott reports issues.**

Scott has the new PrePress surface open and the main interactions are working: WIP rows load, parts expand, copy buttons work, Ticket View exists, and Ticket Save writes a PDF with the old naming/banner behavior. For PrePress issues, compare directly against the old Retriever on `bggol-vesko01` and fix only the behavior or visual mismatch in front of us.

**Fetch parity remains the next non-PrePress arc.**

**Discord–Fetch parity — “same answer class as Discord,” not just shared logs.**

Plain English: **instrumentation and calmer errors helped**, but **live Fetch** can still **miss on the first `/docs` turn** (example: Enfocus Review story first, **Checkpoint via mail** only after pushback) while **Discord** was **right the first time**. **PrintSmith** can still show **generic query failed** with **footer copy that does not match the failure**. The next arc is to treat **one real Discord broker POST + one real assistant reply** as the **golden contract**, then **remove every fork** (builder, session key, MCP vs gateway, envelope extras, model policy) until **both surfaces send the same pipeline inputs** and a **shadow harness** proves **outcome-class** match before UI polish.

Keep **narrow pilot flags** unless a parity decision explicitly requires widening (**`FETCH_GENERAL_QUESTIONS_ENABLED`** still does **not** fix **`/printsmith`** routing — it only unlocks **`general_candidate`**).

**Owner eight-step program (next sessions — execute in order):**

1. **Prove what “Discord” is on the wire** — Capture **one real Discord BooneOps turn**: full redacted **`POST /v1/booneops/message`** JSON (body only) **plus** the **assistant text Discord showed**. That pair is the **contract**, not vibes or parity flags alone.
2. **Same POST from Fetch** — **One shared builder** for Discord and Fetch: same field order, defaults, **`botId` / `role`**, **`priorMessages`** shape and cap, slash handling, and **`sessionMetadata`** keys that affect routing (`source`, `routeLabel`, parity toggles, docs hints).
3. **Kill intentional path splits** — Any **`if Fetch then X, if Discord then Y`** (MCP fast path, different envelope regions, extra grounding blocks, different **sessionKey** rules) is a fork. **Match Discord’s fork** for the same message class, or **change Discord** so both use **one** pipeline.
4. **Gateway session identity** — Align Fetch’s **`conversationId`** (or whatever Retriever sends) to **Discord’s real continuity key** (e.g. channel + user) so **tool memory** matches; **do not approximate** if first-turn answers depend on it.
5. **Identical model stack** — Same **agent id**, **model policy**, **tool allowlist**, **temperature / top‑p** (whatever the gateway enforces), and **system + envelope** after the shared builder. Strip Fetch-only prompt splices **or** add the **same** splices to Discord.
6. **Same retrieval and tools** — Same **tools**, **indexes**, and **call order** as Discord; different retrieval ⇒ different answers even with identical prompts.
7. **Shadow parity harness (continuous)** — Fixed employee prompts (including **`/docs`** email checkpoint); run **Discord path** and **Fetch path** through the unified builder; compare **outcome class** (route, tools, errors, artifacts) then spot-check prose; set an **acceptable match threshold**; accept **wording** variance.
8. **UI copy last** — Status lines, **“not recorded,”** error cards: trust-critical, but **not** the lever that makes first-turn answers match Discord if steps **1–7** are still split.

**Reference (older nine-track checklist)** — Still valid as a **map**, but the **eight steps above** are the **execution spine** for the next few sessions: `projects/booneops-bots/docs/DISCORD_FETCH_PARITY.md`, **`BROKER.md`**, Retriever **`app/fetch/booneops_broker.py`**, OpenClaw gateway host for **model telemetry** if **“not recorded”** persists.

**Deploy reminders (when you cut releases):** **Whitaker** broker **`git pull` + `launchctl kickstart`** after broker commits; **Retriever prod** via **Retriever** repo **`main`** / **Windows runner** on **`bggol-vesko01`**.

**Still on the runway (not the same program):** **`/docs` summary + source UX`**, **artifact lifecycle**, **PDF snapshot product decision**, **slow-turn progress UX**, runbooks in **`deploy/`** / **`docs/runbooks/`**, **`PARKED.md` OQ-10** RetrieverOps lane **after** parity foundations exist.

## Later Work

- **Fetch slow-turn UX:** Cursor-style muted in-thread progress or “thinking” state during long broker/model turns, updating over time and collapsing into the final assistant message (companion to delayed-report cards). Near-term without streaming: keep explicit client-side working feedback on ask submit so the composer never looks idle behind a slow POST.
- Produce migration planning before production build-out, focused on real modules/data that matter; old Fetch data can be ignored or archived unless explicitly requested.
- Expand `SECRETS_HANDLING.md`, `AUDIT_LOG_DESIGN.md`, `WEBHOOK_AND_BROKER_AUTH.md`, and `BUILD_CODE_LAYOUT.md` as implementation choices become concrete.
- Produce a DSF action-service design after Fetch/auth are stable.
- Continue hardening the auth shell against a real MySQL/Cloudflare environment.
- Build Fetch.
- Add Impeccable product/design context before UI implementation.

## Pre-Build Security Checklist

Cursor's security model is now captured as development-supply-chain guidance across the active architecture artifacts. Before code, keep these checks visible:

1. **MCP capability scoping** — BooneOps Light/Medium user tiers still need an allowed-tool list per tier and per-call production audit logging before implementation.

2. **Zero Data Retention posture** — Cursor Privacy Mode helps protect development work, but Fetch runtime still needs an explicit model/provider data-retention decision for customer and financial prompts.

3. **Audit log spec** — `AUDIT_LOG_DESIGN.md` now defines a starting schema, but storage, retention, readers, redaction, and tamper-evidence decisions remain open.

Reference: `memory/shared/seeds/2026-05-05-cursor-security-model.md`

## Guardrails

- Do not edit `projects/Retriever/` unless explicitly asked.
- **Project `wrap`** (not workspace `/end`) closes a retriever-rebuild Cursor session: update PLAN/SESSION-LOG, then give a **copy-ready next-session prompt** that includes **kickoff**, **goal**, **notes**, and instructions to run **`.cursor/skills/retriever-test-ready/SKILL.md`** plus **open Retriever in a browser** before coding (see `.cursor/rules/retriever-rebuild.mdc` § Wrap).
- **Post-deploy feedback** automation must **never** stop, reinstall, or retarget legacy **`Retriever`** on **`8000`**; read-only liveness only unless an operator explicitly uses **`skip_legacy_liveness`** for controlled maintenance.
- Treat old Fetch as a reference for ideas, not a compatibility target.
- Keep LLMs away from direct write credentials.
- Prefer explicit tool routing over clever keyword guessing.
- Use delayed reports with visible progress for heavy list/export work instead of long blocking chat calls.
- Use plain English first.
