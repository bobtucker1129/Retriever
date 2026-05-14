# retriever-rebuild: Session Log

Exit summaries, newest at top. Use project-local wrap to keep this current.

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
- Created MySQL `retriever_cloudflare` schema/user access from `192.168.33.12`.
- Fixed first-deploy blockers in the Windows deploy script: PowerShell 5.1 compatibility, reserved `$Args` variable shadowing, `pyproject.toml` install, old Retriever env-var pollution, Python cwd for static/templates, and the real migration API.
- Successfully staged release `ed41f94261910256edc71d104adcabf7dd00324c`; migrations applied `0001_retriever_cloudflare.sql` and `0001_seed_auth_shell.sql`; `D:\retriever-rebuild\current` points at the staged release.
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

