# retriever-rebuild: Parked List

Tangents, deferred decisions, and ideas not on the active session goal.

---

## OQ-10: RetrieverOps / Fetch-dedicated broker lane

**Parked:** 2026-05-11  
**Goal:** Long-term, give Retriever Fetch a **dedicated broker lane** (working name: RetrieverOps or Fetch-specific endpoint) with **its own logs**, **queue or concurrency limits**, **no instruction-update or write actions**, and **reduced competition** with Telegram/Discord BooneOps traffic.  
**Constraints:** Must fit the existing trust model (read-heavy employee helper); evolves after observability is in place.  
**Non-goal:** Do **not** treat this as “stand up a full **BooneOps clone** immediately.”  
**Dependency:** **Correlation logging** across Fetch ask → broker → downstream should land **before** leaning on this lane for heavy tests or broad rollout.  
**Update (2026-05-11):** BooneOps correlation + Retriever observability landed for the live pilot using the **existing** broker stack; opening a **new** Fetch-dedicated lane is still **not** the next sprint—**employee-facing docs formatting/source UX** leads first.

---

## OQ-11: Printing Press — Research for CLI / Skill Generation

**Parked:** 2026-05-11
**What it is:** printingpress.dev — a tool that takes any API spec (or website) and generates a token-efficient Go CLI, a Claude Code skill, an OpenClaw skill, and an MCP server from it in one command. Community library already has 77+ CLIs including `pp-fedex`.
**Core philosophy:** Local SQLite mirror beats remote API round trips — same pattern Retriever already uses.
**Why it's relevant:**
- Could generate OpenClaw skills for vendor APIs we interact with (FedEx, UPS, suppliers) without writing them from scratch
- The local mirror + compound query design is a direct parallel to Retriever's approach — worth studying their architecture
- `pp-fedex` could feed shipping data into Retriever or the shipping dashboard
**Research tasks (whenever we revisit integrations):**
1. Evaluate `pp-fedex` for Boone's daily shipping workflow
2. Check if PrintSmith Vision or MDSF have API specs that could be "printed"
3. Review Printing Press's SQLite mirror pattern for lessons applicable to Retriever's data layer
**Seed:** `memory/shared/seeds/2026-05-11-printing-press-agent-cli-generator.md`

---

## OQ-1: Final Production Host

**Parked:** 2026-05-04  
**Question:** Should new Retriever run on `bggol-vesko01`, another Boone LAN app server/VM, or somewhere else?  
**Current decision:** First new Retriever runtime should be a sibling Boone LAN Linux app VM. `bggol-vesko01` stays old Retriever and PrintSmith token authority during staging.
**Current hostname decision:** `retriever.boonegraphics.net` is the live hostname from first deploy. No staging subdomain is needed; old Retriever is LAN-only with no Cloudflare presence.
**Current database decision:** Use MySQL with a new `retriever_cloudflare` schema, separate from current Retriever's `retriever_core`.
**Current VM name:** Use `bggol-retriever01` unless Boone IT requires another naming convention.
**Still open:** Provisioning owner, backup expectations, and exact Cloudflare/Tailscale routing.

---

## OQ-2: General Outside-World Fetch Answers

**Parked:** 2026-05-04  
**Question:** Should general non-Boone questions be enabled for all Fetch users, beta users only, or disabled by default?  
**Current lean:** Admin toggle, enabled for Master Tate and early testers first.  
**Why parked:** Needs Fetch trust/cost policy before implementation.

---

## OQ-3: Old Fetch Reference Value

**Parked:** 2026-05-04  
**Question:** Which old Fetch ideas are worth reusing as product requirements?
**Current decision:** Old Fetch does not work well and nobody depends on it today. Do not preserve old Fetch compatibility, data, UI quirks, or routing behavior by default.
**Current lean:** Build new Fetch first. Reuse the useful product ideas: current-style left-side conversation history, current-style conversation rename, email cleanup, uploads, source visibility, report downloads, slash-command help, status/health display, visible model for all users, and visible context-window level for all users. `FETCH_UI_CONTINUITY.md` now captures the visual/layout target.
**Why parked:** Backend implementation detail still belongs to Fetch skeleton work, but these product requirements should no longer be treated as optional.

---

## OQ-4: Impeccable Product Context

**Parked:** 2026-05-04  
**Question:** When should `/impeccable teach`, `/impeccable document`, and `/impeccable shape` run?  
**Current decision:** `/impeccable teach` and `/impeccable shape` have run for the shared Retriever shell. `PRODUCT.md` and `SHARED_LAYOUT_SHAPE.md` now exist.
**Still open:** Run `/impeccable document` later if we want a formal `DESIGN.md` token/component reference, ideally after inspecting old Retriever's current UI and confirming close visual continuity.

---

## OQ-5: PrintSmith Token Authority

**Parked:** 2026-05-04  
**Question:** How does new Retriever preserve the old Retriever role as sole `LordTate` PrintSmith REST token authority?  
**Current decision:** Old Retriever on `bggol-vesko01` remains token authority during staging. New Retriever may borrow through the existing proxy but must not generate its own `LordTate` token while old Retriever owns authority.
**Current launch decision:** Old Retriever keeps first dibs through first launch. New Retriever becomes primary only when new Retriever PrePress is migrated and ready to own the shared token.
**Known current users:** old Retriever PrePress and one currently on-hold project.
**Still open:** Define the exact migration event that marks new Retriever PrePress ready to become the primary token authority.

---

## OQ-6: Cloudflare Identity Binding

**Parked:** 2026-05-04  
**Question:** Does Retriever validate Cloudflare Access JWTs directly, or trust Access headers only after firewall/tunnel-only enforcement?  
**Current lean:** Validate identity explicitly and block direct LAN access that can spoof Cloudflare headers.  
**Why parked:** `DEPLOYMENT_BRIDGE.md` now requires explicit identity validation where practical, but the implementation-level decision belongs in `RUNTIME_NOTES.md` and auth build work.

---

## OQ-7: Audit And Secrets Design

**Parked:** 2026-05-04  
**Question:** Where do audit logs and production secrets live, and how are they rotated, retained, redacted, and reviewed?  
**Current decision:** First app audit metadata lives in MySQL `retriever_cloudflare.audit_events`; deploy/app log files live under `/var/log/retriever-rebuild`; production secrets live in `/etc/retriever-rebuild/retriever.env` or another Boone-approved vault, not Git or Cursor.
**Still open:** Secret rotation owner, audit retention period, who can read sanitized logs, and whether tamper-evidence is needed for first launch.

---

## OQ-8: Legacy Data Migration

**Parked:** 2026-05-04  
**Question:** What happens to old Fetch conversations, private upload libraries, local usernames, inventory manager roles, and PrePress operator-name mappings?  
**Current lean:** Old Fetch conversations and private library data do not need migration unless explicitly requested. Other module data, local usernames, inventory manager roles, and PrePress operator-name mappings still need migration planning before those modules move.
**Why parked:** Depends on the new auth shell and build layout.

---

## OQ-9: First Code Runtime Details

**Parked:** 2026-05-06
**Question:** Which minor runtime/library details should be pinned for the first FastAPI scaffold?
**Current decision:** Use Python/FastAPI, server-rendered HTML, small HTMX-style interactions, `pydantic-settings`, and `mysql-connector-python`.
**Current local reality:** This Mac only has Python 3.9 available, so the first scaffold is Python 3.9-compatible for local verification.
**Still open:** Boone VM Python version, whether `/health/deep` requires admin session, Cloudflare service token, or both, and whether local development keeps unsigned identity fixtures or moves to a test identity middleware after real Cloudflare JWT validation lands.

