# retriever-rebuild: Living Plan

This is the cross-session project dashboard. `SESSION-LOG.md` records what happened. `PARKED.md` holds side ideas. `AUTH_REDESIGN.md` is the first architecture artifact.

## Current Phase

Phase 0: planning and architecture.

Plain English: before building new Retriever, lock the auth model, Fetch trust plan, production runtime shape, and the boundary between the new app and the old LAN repo.

## Current Status

Completed:

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
- Wrote `RETRIEVER_CLOUDFLARE_SCHEMA.md`, defining the first MySQL `retriever_cloudflare` schema for Cloudflare-linked users, roles, capabilities, module access, sessions, settings, delayed reports, artifacts, audit events, and migrations.
- Wrote `CONFIG_AND_HEALTH_CONTRACT.md`, defining the first `.env.example` shape, startup validation rules, `/health/*`, `/version`, dependency names, smoke tests, and redaction rules.
- Wrote `AUTH_SHELL_BUILD_PLAN.md`, choosing Python/FastAPI with server-rendered HTML as the first stack and breaking the auth shell into build slices.
- Updated `BUILD_CODE_LAYOUT.md` so the first code scaffold has a concrete FastAPI layout instead of an open framework choice.
- Created the first FastAPI scaffold with `pyproject.toml`, `.env.example`, `app/`, `migrations/`, `tests/`, `deploy/`, config validation, health/version routes, disabled Fetch placeholder, initial MySQL migration SQL, and smoke/systemd examples.
- Set up a local `.venv` for scaffold verification and added project `.gitignore` rules so environment/cache files stay out of Git.
- Added DB-backed repository scaffolding for users, sessions, settings, and audit events.
- Replaced the local-only user placeholder with a flow that uses `retriever_cloudflare` repositories when MySQL config is present, while keeping local scaffold fallback for development.
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
- Added opaque `retriever_session` cookie issuance backed by `retriever_cloudflare.sessions`.
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
- Created MySQL schema/user for `retriever_cloudflare` on Boone MySQL and successfully applied `0001_retriever_cloudflare.sql` plus `0001_seed_auth_shell.sql` during first deploy.
- Successfully staged release `ed41f94261910256edc71d104adcabf7dd00324c` at `D:\retriever-rebuild\current`; next step is installing and starting the `RetrieverRebuild` Windows service.
- Installed `RetrieverRebuild` as an NSSM Windows service on `bggol-vesko01`; service started successfully and `/health/live` returned 200 on port `8810`.
- Local smoke passed on `bggol-vesko01`: `/health/live`, `/health/ready`, `/version`, version metadata, no secret leakage, and disabled `/fetch` all passed (`8 passed, 0 failed`).
- Fixed the `cloudflared` Windows service command so it runs `C:\cloudflared\cloudflared.exe --config C:\cloudflared\config.yml tunnel run retriever`; browser test now shows Cloudflare Access first, then reaches Retriever successfully.
- Disabled old Fetch in the old Retriever runtime, clearing the duplicate Fetch surface while old Retriever continues to own PrePress, DSF, and PrintSmith token authority.
- Built the first real new-Fetch slice: DB-backed conversation creation, listing, selection, rename, soft delete, message storage primitives, Fetch access gating, and a disabled-safe shell that keeps model/tool routing locked.
- Built the first safe ask-path skeleton: ask submission is gated by active user, Fetch shell access, `FETCH_ENABLED`, and `fetch.ask_internal`; enabled asks write a deterministic stub reply only, with no model, PrintSmith, docs, BooneOps, upload, or delayed-report calls.
- Hardened Windows deploy/smoke prep for the Fetch release: migration `0002_fetch_conversations` checks, explicit `RetrieverRebuild`/port `8810` guardrails, Fetch/model-off smoke assertions, and a read-only old Retriever port `8000` liveness check.
- Verified the new Fetch slices locally: 65 tests passed, local route smoke passed, and edited files have no linter errors.
- Added a gated **ask path** (`POST /fetch/conversations/{id}/ask`): requires the same shell access as before, plus `FETCH_ENABLED` (env) and **`fetch.ask_internal`** (capability; admins still pass via existing `has_capability` rules). When Fetch is off, the route redirects without persisting a user message. When Fetch is on but provider routing is not wired, it saves the user turn and appends a fixed stub assistant reply—no outbound model or tool calls.
- **Fetch local routing (stub):** `classify_fetch_intent` assigns deterministic route labels (`local`, slash `help`/`sources`/`health`, `email_cleanup`, `printsmith_candidate`, `docs_candidate`, `general_candidate`, `blocked_write`, `unknown`). The ask handler persists those labels as `route_key` and returns route-specific offline copy; still no providers, PrintSmith, docs APIs, BooneOps, uploads, or web calls.

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
- `RETRIEVER_CLOUDFLARE_SCHEMA.md`: first MySQL schema plan for new Retriever app state.
- `CONFIG_AND_HEALTH_CONTRACT.md`: environment, validation, health, version, smoke, and redaction contract.
- `AUTH_SHELL_BUILD_PLAN.md`: selected first framework/runtime and build slices for the Cloudflare auth shell.
- `LOCAL_RUNBOOK.md`: local test/start/smoke instructions and first browser-smoke path.
- `deploy/WINDOWS_FETCH_RELEASE.md`: Windows production deploy for **RetrieverRebuild**, migration **0002**, **`smoke.ps1`**, coexistence with port **8000**, **`FETCH_ENABLED`** vs validation, and future model enablement checklist.
- `PRODUCT.md`: Impeccable product context for Retriever UI work.
- `SHARED_LAYOUT_SHAPE.md`: confirmed Impeccable shape brief for the shared app shell.
- `FETCH_UI_CONTINUITY.md`: current Fetch visual/layout continuity target for the first new Fetch skeleton.

## Active Decisions

Resolved:

- `projects/Retriever/` is the old LAN repo reference copy, not the rebuild workspace.
- `projects/retriever-rebuild/` is the planning/build home for the new Retriever.
- Old Fetch on `bggol-vesko01` should be turned off via a feature flag. Nobody uses it, and disabling it clears the way for the new Fetch without confusing users.
- Automated CI/CD deployments and staging validations are a core goal. We will establish a staging pipeline (`retriever-next.boonegraphics.net`) that runs tests before promoting code to `retriever.boonegraphics.net`. This will follow stabilizing the first manual deploy scripts.
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
- New Retriever app state should live in MySQL, using a new `retriever_cloudflare` schema separate from current Retriever's `retriever_core`.
- Old Retriever keeps first dibs on the shared PrintSmith token at first launch. New Retriever becomes primary only when new Retriever PrePress is migrated and ready to own that token.
- Working VM name is `bggol-retriever01`, unless Boone IT requires a different naming convention.
- First app-state schema is `retriever_cloudflare`; old Fetch conversations/private library data do not migrate by default.
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

Open:

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
- **What “Fetch foundation” means:** conversation list/create/rename/delete in MySQL (**`0002`**), optional **stub** ask only when **`FETCH_ENABLED=true`** (still no real model or tool routing). **`FETCH_ENABLED=false`** remains the recommended production default: conversation CRUD still works; the ask composer stays off; post-deploy **`smoke.ps1`** expects **`fetch`** and **`modelProvider`** **disabled** in **`/health/ready`**. If **`FETCH_ENABLED=true`**, startup validation **still requires** model env vars even though code only runs the stub—see the runbook.
- **Before real models/tools:** follow the enablement checklist at the bottom of **`deploy/WINDOWS_FETCH_RELEASE.md`** together with **`FETCH_TRUST_PLAN.md`**.

## Next Recommended Session

Close first deploy and operate the Fetch foundation safely.

Plain English goal: the auth shell runs on **`bggol-vesko01`**, Cloudflare Access protects **`retriever.boonegraphics.net`**, old Fetch is off, and new Fetch provides conversation management with **`FETCH_ENABLED=false`** in production until a deliberate stub or model enablement pass. Operators should treat **`deploy/WINDOWS_FETCH_RELEASE.md`** as the source of truth for Windows deploy, migration **`0002`**, smoke, and coexistence with port **`8000`**.

Recommended scope:

1. Confirm legacy **Retriever** on port **`8000`** still serves PrePress/DSF and PrintSmith token authority after old Fetch was disabled.
2. When shipping Fetch foundation code, apply migration **`0002`** once on **`retriever_cloudflare`**, deploy **`RetrieverRebuild`**, and run **`smoke.ps1`** (optionally with Cloudflare URL + service token vars).
3. Keep **`FETCH_ENABLED=false`** in production env until the checklist in **`deploy/WINDOWS_FETCH_RELEASE.md`** is satisfied for stub testing or real routing.
4. After the foundation is stable, start real model-routing work only as a separate, explicitly reviewed enablement step.

## Later Work

- Establish an automated CI/CD deployment pipeline to deploy to staging, run automated smoke tests, and safely promote to **`retriever.boonegraphics.net`** (a dedicated staging hostname remains optional per current host decisions).
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
- Treat old Fetch as a reference for ideas, not a compatibility target.
- Keep LLMs away from direct write credentials.
- Prefer explicit tool routing over clever keyword guessing.
- Use delayed reports with visible progress for heavy list/export work instead of long blocking chat calls.
- Use plain English first.

