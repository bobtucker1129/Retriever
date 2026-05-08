# retriever-rebuild: Session Log

Exit summaries, newest at top. Use project-local wrap to keep this current.

---

## 2026-05-08 — Windows deploy path corrected and first release staged

**Goal:** Deploy the auth shell to `retriever.boonegraphics.net` from the Boone runtime.

**What happened:**

- Corrected a major deployment assumption: `bggol-vesko01` is Windows Server, not Linux. Old Retriever runs there as the `Retriever` NSSM service on port `8000`.
- Replaced the failed Linux/systemd/bash deployment path with Windows PowerShell/NSSM scripts.
- Configured Cloudflare Zero Trust for `retriever.boonegraphics.net`: team domain `boonegraphics.cloudflareaccess.com`, Boone Employees Access policy, tunnel `bf859516-9782-4c53-9098-1923709b4028`, DNS route, and `cloudflared` service running.
- Created MySQL `retriever_cloudflare` schema/user access from `192.168.33.12`.
- Fixed first-deploy blockers in the Windows deploy script: PowerShell 5.1 compatibility, reserved `$Args` variable shadowing, `pyproject.toml` install, old Retriever env-var pollution, Python cwd for static/templates, and the real migration API.
- Successfully staged release `ed41f94261910256edc71d104adcabf7dd00324c`; migrations applied `0001_retriever_cloudflare.sql` and `0001_seed_auth_shell.sql`; `D:\retriever-rebuild\current` points at the staged release.

**Plain-English result:**

The hard first-deploy infrastructure is now mostly behind us. New Retriever is not running as a service yet, but the server has the code, production env, Cloudflare gate, Cloudflare Tunnel, MySQL schema, seed rows, and a staged current release.

**Next recommended session:**

Install and start `RetrieverRebuild` with `D:\retriever-rebuild\bin\install-service.ps1`, then run localhost and Cloudflare smoke checks. Do not recreate Linux deploy artifacts.

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

- Resolved runtime and token-authority details: new Retriever should stage on a sibling Boone LAN Linux VM, `retriever.boonegraphics.net` remains the final live hostname, `retriever-next.boonegraphics.net` is staging, app state belongs in MySQL `retriever_cloudflare`, and old Retriever keeps first dibs on the shared PrintSmith token until new PrePress is ready.
- Wrote the core planning/build artifacts: `RUNTIME_NOTES.md`, `PRINTSMITH_TOKEN_AUTHORITY.md`, `VM_SETUP_PLAN.md`, `RETRIEVER_CLOUDFLARE_SCHEMA.md`, `CONFIG_AND_HEALTH_CONTRACT.md`, `AUTH_SHELL_BUILD_PLAN.md`, `LOCAL_RUNBOOK.md`, `PRODUCT.md`, and `SHARED_LAYOUT_SHAPE.md`.
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
- Captured the review in `REVIEW-2026-05-04-OPUS.md`.
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

