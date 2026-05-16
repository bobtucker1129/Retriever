# Workspace, repos, and where the docs live

Read this once when you are confused about **“Retriever inside Whitaker / LordTate”** or **where markdown should go**. It does not replace deploy runbooks or the broker topology seed; it explains **disk and Git layout** so you do not re-invent it every session.

## Two layers: one folder, two Git histories

| Layer | What it is | Typical path on Whitaker |
|-------|----------------|---------------------------|
| **LordTate workspace** | The big **LordTate** git checkout Master Tate uses for agents, memory, and many projects | `/Users/whitakertate/Whitaker/workspace` (example) |
| **Retriever rebuild (nested repo)** | The **new Retriever** application and its docs: **same folder** lives under the workspace as `projects/retriever-rebuild/`, but that folder has **its own `.git`** and its **own remote** (GitHub **`Retriever`**) | `…/workspace/projects/retriever-rebuild/` |

**Plain English:** You are almost always editing files **inside** `projects/retriever-rebuild/`. Those changes **ship** when you **commit and push the Retriever repo** (nested `git` inside that directory). The **LordTate** parent repo may **also** list those paths as tracked files, depending how the tree is configured—when in doubt, **commit where the work belongs**: app and Retriever docs → **Retriever** remote; cross-cutting workspace rules and `memory/` → **LordTate** remote. If both show dirty, **ask Master Tate** which commit should own the slice you touched.

**Broker** is **not** inside Retriever: it lives in **`projects/booneops-bots/`** in the **same** LordTate workspace. Retriever is only an **HTTP client** to the broker.

**Canonical host and env map** (who runs on which machine, ports, Tailscale, OpenClaw): `memory/shared/seeds/2026-05-17-fetch-broker-openclaw-topology.md` in the LordTate workspace.

---

## Where documentation lives in *this* project (Retriever)

| Location | Holds |
|----------|--------|
| **Repo root** (`*.md` next to `app/`) | **Session spine only:** `KICKOFF.md`, `PLAN.md`, `PARKED.md`, `SESSION-LOG.md`, `HANDOVER.md`. Kickoff reads these plus whatever `PLAN.md` lists under planning—not “every markdown ever.” |
| **`docs/README.md`** | **Map:** what to open first by role (operator vs dev vs auth). |
| **`docs/WORKSPACE_AND_REPOS.md`** | **This file:** workspace vs nested repo, sibling broker, doc taxonomy. |
| **`docs/planning/`** | Long-form **architecture, trust, product, local dev** specs (`AUTH_REDESIGN`, `FETCH_TRUST_PLAN`, `DEPLOYMENT_BRIDGE`, `LOCAL_RUNBOOK`, etc.). See `docs/planning/README.md`. |
| **`docs/runbooks/`** | **Operator procedures** (Windows runner, broker wiring from the server, post-deploy feedback). |
| **`deploy/`** | **Deploy scripts and operator-facing release notes** (`WINDOWS_FETCH_RELEASE.md`, `smoke.ps1`, etc.)—not the same as narrative planning in `docs/planning/`, though they cross-link. |
| **`docs/archive/`** | One-off reviews and other **historical** write-ups kept for context. |
| **`.cursor/skills/`** (under this project) | Cursor-only **preflight** and helpers for this repo. |

**Old LAN Retriever reference copy** (read-only unless Master Tate asks otherwise): `projects/Retriever/` at the **workspace** level—not part of the Retriever nested repo’s source tree for shipping.

---

## Quick answers

- **“Are we in LordTate or Retriever?”** Both: **working directory** is usually `projects/retriever-rebuild/`; **ownership** of the commit is determined by **which `git`** you run (`cd` into `retriever-rebuild` for Retriever).
- **“Where do I put a new long spec?”** `docs/planning/` (and link it from `PLAN.md` *Active Architecture Artifacts* when it becomes canonical).
- **“Where do I put operator steps for Windows?”** `docs/runbooks/` and/or `deploy/` next to the scripts they describe.
- **“Where does Discord vs Fetch parity live?”** **Canonical** doc: `projects/booneops-bots/docs/DISCORD_FETCH_PARITY.md`. Retriever keeps a **pointer** at `docs/DISCORD_FETCH_PARITY.md`.
