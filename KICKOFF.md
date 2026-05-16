# retriever-rebuild: Kickoff

**Created:** 2026-05-04  
**Status:** Active planning project. The old `projects/Retriever/` folder is a read-only reference copy of the current LAN repo.

**Workspace vs repo:** This folder (`projects/retriever-rebuild/`) lives **inside** the LordTate **Whitaker workspace**, but it is its **own git repo** (separate **Retriever** remote). The BooneOps broker lives next door at `projects/booneops-bots/`—not inside Retriever. **Read once and stop re-explaining:** [`docs/WORKSPACE_AND_REPOS.md`](docs/WORKSPACE_AND_REPOS.md) (where every class of docs lives, which `git` to commit).

This project exists to rebuild Retriever deliberately instead of continuing to bolt new behavior onto the old application. Each session should stay narrow: read this file, then `PLAN.md`, `PARKED.md`, the active architecture artifacts listed in `PLAN.md` (paths under `docs/planning/`), and the newest `SESSION-LOG.md` entry. For orientation across many markdowns, open `docs/README.md`.

**Before substantive Retriever work** (auth, admin, Fetch, pre-press, DSF, deploy, migrations): run the test-readiness preflight in `.cursor/skills/retriever-test-ready/SKILL.md` (or say `kickoff projects/retriever-rebuild` and treat that as the cue). Goal: confirm how you will **observe** the running app (local curl, public URL, Chrome MCP, or user paste-back) *before* a long coding loop, and run **pytest** early.

## Why This Project Exists

Retriever is becoming the employee-facing front door for Boone operational help, starting with a new Fetch. Old Fetch does not work well enough and nobody depends on it today, so the rebuild should not spend effort preserving old Fetch compatibility. New Fetch is still the trust barrier: if it feels buggy, employees will distrust the rest of Retriever.

The rebuild needs to preserve what works in the current LAN Retriever while avoiding its accidental coupling:

- local username/password as the main front door
- mixed roles, app admin, and BooneOps power
- fragile Fetch-to-BooneOps routing
- large file and PrintSmith/Switch dependencies that belong near the Boone LAN
- unclear boundaries between `/printsmith`, `/docs`, and estimating automation

## Current Architecture Direction

- **Old reference:** `projects/Retriever/` stays untouched as the current LAN repo copy.
- **New project:** `projects/retriever-rebuild/` holds planning and, later, new code.
- **Production lean:** new Retriever likely runs on a Boone LAN server and is exposed through Cloudflare Access/Tunnel at `retriever.boonegraphics.net`.
- **OpenClaw role:** development, planning, code control, and agent workflow. OpenClaw should not be the single production runtime.
- **First module:** Fetch, after auth is designed.

## Source Boundaries

- `/printsmith`: live Boone PrintSmith read-only operational data.
- `/docs`: vendor/tool documentation for Enfocus, XMPie, PrintSmith help/schema, DSF, MDSF, SmartCanvas, and related tools.
- `/printsmith-estimate`: outside Retriever scope; estimate creation/modification automation only.

## Impeccable

Use `skills/impeccable` for product/UI design work, not for backend auth architecture.

Before building new Retriever UI, run the appropriate Impeccable flow:

1. `/impeccable teach` if the project lacks a real product/design context.
2. `/impeccable document` once there is enough existing UI/design material to extract.
3. `/impeccable shape` before crafting major Fetch or app-shell UI.

Do not run Impeccable as a substitute for the auth/security plan.

## Operating Rules

1. **Kickoff and wrap are reserved triggers for this project.** When Master Tate says `kickoff projects/retriever-rebuild` or is already in this project and says `kickoff`, run the narrow startup. When he says `wrap`, close the session with project-local updates.
2. **One active goal per session.** Fetch, auth, runtime, and DSF action-service design are related, but they should not all be built in the same session.
3. **Fetch is a trust barrier.** Any Fetch plan must include explicit routing, failure states, delayed-report behavior, and the useful product features new Fetch should intentionally include.
4. **Old Retriever stays reference-only.** Do not edit `projects/Retriever/` unless Master Tate explicitly asks to patch the old LAN repo copy.
5. **Plain English first.** Translate architecture choices into operational consequences before technical detail.
6. **Wrap ends with the next kickoff prompt.** Every project wrap should end with a copy-ready prompt for the next session: `kickoff projects/retriever-rebuild`, the next goal, critical notes — and **explicit instructions** for the next agent to run the Retriever test-readiness preflight (`.cursor/skills/retriever-test-ready/SKILL.md`), **open a browser** to local `http://127.0.0.1:8810/` or deployed `https://retriever.boonegraphics.net/` (Access as needed), then proceed. `wrap` is project-local; workspace-wide save is `/end`, not `wrap`.

## File Conventions

- `docs/WORKSPACE_AND_REPOS.md`: **LordTate workspace vs Retriever nested repo**, sibling broker, and **where each doc category lives** (stop re-deriving this each session).
- `docs/README.md`: **documentation map** — which markdown to open first (operators vs dev vs auth).
- `docs/planning/README.md`: what lives in the planning folder and how paths work.
- `KICKOFF.md`: this operating contract.
- `PLAN.md`: current phase, next recommended session, and active decisions.
- `docs/planning/AUTH_REDESIGN.md`: auth teardown and target model.
- `docs/archive/REVIEW-2026-05-04-OPUS.md`: read-only senior review of the initial rebuild plan.
- `PARKED.md`: deferred ideas and open questions.
- `SESSION-LOG.md`: newest-first session exits.

## First Session Goal Candidate

Write the Fetch trust plan before building code:

- define routing between local Fetch, `/printsmith`, `/docs`, BooneOps Light/Medium, uploads, email cleanup, and general questions
- define failure behavior for timeouts and unavailable services
- define delayed-report/artifact behavior for heavy PrintSmith/DSF queries
- define which Fetch product ideas are worth intentionally building

