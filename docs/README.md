# retriever-rebuild — documentation map

Use this file when the project feels “too many markdowns.” It does not replace deeper docs; it tells you **which file to open first**.

**Lost on “Retriever inside Whitaker” or where files should live?** Read **[`WORKSPACE_AND_REPOS.md`](WORKSPACE_AND_REPOS.md)** first (nested repo vs LordTate workspace, broker sibling, doc folders).

## Start here (living) — repo root

| Read first | Purpose |
|------------|---------|
| [`../KICKOFF.md`](../KICKOFF.md) | Session contract: kickoff/wrap, Impeccable, test preflight |
| [`../PLAN.md`](../PLAN.md) | Current phase, next session goal, decisions |
| [`../PARKED.md`](../PARKED.md) | Deferred ideas (do not lose) |
| [`../SESSION-LOG.md`](../SESSION-LOG.md) | Newest wrap at top — what shipped and what we learned |
| [`../HANDOVER.md`](../HANDOVER.md) | Last human/agent handoff notes |

## Planning hub (`docs/planning/`)

All detailed architecture, trust, product, and local-dev prose is under **`planning/`** — see [`planning/README.md`](planning/README.md).

| Area | Files (same folder) |
|------|---------------------|
| Fetch trust + routing | `FETCH_TRUST_PLAN.md`, `FETCH_UI_CONTINUITY.md` |
| Help / Wiki orchestration | `planning/HELP_ORCHESTRATION.md` |
| Product / layout | `PRODUCT.md`, `SHARED_LAYOUT_SHAPE.md` |
| Auth + schema + secrets | `AUTH_REDESIGN.md`, `RETRIEVER_CORE_SCHEMA.md`, `WEBHOOK_AND_BROKER_AUTH.md`, `SECRETS_HANDLING.md`, `CONFIG_AND_HEALTH_CONTRACT.md`, `PRINTSMITH_TOKEN_AUTHORITY.md`, `AUDIT_LOG_DESIGN.md` |
| Deploy / runtime narrative | `DEPLOYMENT_BRIDGE.md`, `RUNTIME_NOTES.md`, `VM_SETUP_PLAN.md`, `AUTH_SHELL_BUILD_PLAN.md` |
| Code + repo shape | `BUILD_CODE_LAYOUT.md` |
| Local dev | `LOCAL_RUNBOOK.md` |

## Deploy and ops (Windows production today)

| Doc | Purpose |
|-----|---------|
| [`../deploy/WINDOWS_FETCH_RELEASE.md`](../deploy/WINDOWS_FETCH_RELEASE.md) | **`bggol-vesko01`**, `RetrieverRebuild`, port `8810`, pilot flags |
| [`../deploy/VM_SETUP_RUNBOOK.md`](../deploy/VM_SETUP_RUNBOOK.md) | Same host — operator steps, NSSM, paths |
| [`runbooks/booneops-broker-fetch-windows.md`](runbooks/booneops-broker-fetch-windows.md) | Retriever → BooneOps broker over Tailscale; env names |
| [`runbooks/github-actions-retriever-rebuild-deploy.md`](runbooks/github-actions-retriever-rebuild-deploy.md) | CI deploy contract |
| [`runbooks/automated-feedback-bridge-windows.md`](runbooks/automated-feedback-bridge-windows.md) | Post-deploy feedback / smoke wiring |
| [`runbooks/admin-user-onboarding.md`](runbooks/admin-user-onboarding.md) | Approve Cloudflare users, admin matrix, Fetch smoke |

## Pointers elsewhere

| Doc | Purpose |
|-----|---------|
| [`DISCORD_FETCH_PARITY.md`](DISCORD_FETCH_PARITY.md) | Pointer only — **canonical** parity doc lives in `projects/booneops-bots/docs/DISCORD_FETCH_PARITY.md` |
| [`archive/README.md`](archive/README.md) | Archived one-off reviews |

## Repo / broker topology (short)

- **This repo** (`Retriever` on GitHub) = FastAPI app, Fetch UI, broker **client** — folder is **nested under** the LordTate workspace; see **[`WORKSPACE_AND_REPOS.md`](WORKSPACE_AND_REPOS.md)**.
- **BooneOps broker** = sibling project **`projects/booneops-bots`** in the **LordTate** workspace (Whitaker); HTTP `POST /v1/booneops/message`; OpenClaw gateway on that host.
- **Canonical map** (hosts, ports, env split): `memory/shared/seeds/2026-05-17-fetch-broker-openclaw-topology.md` in LordTate workspace.
