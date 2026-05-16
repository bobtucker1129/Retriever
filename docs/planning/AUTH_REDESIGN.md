# Retriever Auth Teardown And Redesign

**Status:** planning document  
**Scope:** new Retriever rebuild, starting with auth and Fetch  
**Source repo:** this workspace copy of `projects/Retriever`  
**Production note:** the live Retriever still runs on `bggol-vesko01` and should not be displaced until each module is proven.

## Executive Summary

Retriever should move from a local username/password model with broad module gates to a two-layer model:

1. **Cloudflare Access** proves the person is allowed through the front door at `retriever.boonegraphics.net`.
2. **Retriever authorization** decides what that person can see, ask, schedule, write, or administer.

The first new production version should keep things simple:

- Master Tate is the only full admin/operator at launch.
- Everyone else who passes Cloudflare can be auto-created as a pending or limited user.
- An admin assigns module access and BooneOps level before the user can do meaningful work.
- Fetch launches first.
- PrePress and DSF stay on old Retriever until the new auth model and action service pattern are proven.
- Owner/operator actions stay outside Retriever, in Cursor/Telegram/LordTate environments.
- Fetch gets an admin toggle for outside-world LLM answers.

This is not just a cleanup. The auth model is the foundation for moving employees out of Discord and into Retriever without giving an LLM uncontrolled write access to production systems.

## Current Auth: What Exists Today

Current Retriever auth is functional, but it grew as modules were added.

### Current Identity Source

The app uses `retriever_core.users` in MySQL as the sole auth source.

Key files:

- `app/auth.py`
- `app/routes/auth.py`
- `app/routes/admin.py`
- `app/database/queries/users.py`

Current behavior:

- Users log in with a local Retriever username and password.
- Session state lives in a signed cookie named `pm_session`.
- Sessions default to a 7-day TTL.
- The cookie includes username, role, email, full name, location fields, admin flag, department, and Fetch bot fields.
- `AUTH_ENABLED = false` creates a development admin user.
- `ensure_users_table()` can auto-create a default `admin/admin123` account if the user table is empty.

The current model solved a real problem: it removed dependency on Switch login and let Retriever run independently. For the rebuild, the same independence should remain, but passwords should no longer be the primary front-door control.

### Current Roles

Current roles are stored as an enum:

- `admin`
- `super`
- `project_manager`
- `sales`
- `production`
- `viewer`

Important current behavior:

- `admin` means Retriever admin.
- `super` is not a normal Retriever admin. It mainly exists for elevated BooneOps/Fetch access.
- `project_manager`, `sales`, and `production` are business roles.
- `viewer` is the lowest role.
- The `groups` field is written into session cookies, but it is not backed by a users table column today.

### Current BooneOps Mapping

Current Fetch bot IDs:

- `booneops.production`
- `booneops.admin`
- `booneops.super`

Current default mapping:

- `admin` gets `booneops.admin`
- `super` gets `booneops.super`
- `project_manager`, `sales`, `production`, and `viewer` get `booneops.production`

Current override behavior:

- Admin can set a per-user Fetch bot override.
- The override is normalized against allowed bots for that role.
- A user cannot select a bot level their role does not allow.

This exists for a reason. It separates normal app admin from BooneOps power. The rebuild should preserve that idea, but rename and explain the tiers more clearly.

## Current Module Auth Map

### Admin

Files:

- `app/routes/admin.py`
- `app/templates/admin/users.html`
- `app/templates/admin/user_form.html`

Current controls:

- Requires `is_admin` or role `admin`.
- Manages users, roles, active status, passwords, and Fetch bot overrides.
- Hidden from the sidebar unless `user.is_admin`.

Current writes:

- Writes to `retriever_core.users`.

Current issue:

- Admin power is tied to one coarse role.
- Password management is still central.
- BooneOps bot settings are mixed into the user admin form.

### Fetch

Files:

- `app/routes/fetch.py`
- `app/fetch/ask_workflow.py`
- `app/fetch/routing.py`
- `app/fetch/rag.py`
- `app/fetch/commands.py`
- `app/fetch/booneops_broker.py`
- `app/templates/fetch/index.html`
- `app/templates/fetch/partials/thread.html`
- `app/static/js/fetch-chat.js`
- `app/static/js/fetch-upload.js`

Current controls:

- Requires a logged-in Retriever user.
- Requires Fetch feature flag and Fetch config to be enabled.
- Can optionally be admin-only.
- Uses the user's effective Fetch bot to decide BooneOps capability.
- Admins can preview Fetch in user mode, but that is a UI preview and not a true permission downgrade.

Current read/write behavior:

- Reads Fetch conversations and library data.
- Writes Fetch conversations, messages, uploads, titles, and report metadata.
- Can call Claude.
- Can call `/docs` for vendor/tool documentation.
- Can call web search.
- Can call BooneOps broker.
- Can produce downloads and reports through BooneOps.
- Email cleanup is intentionally ephemeral and does not write to conversation history.

Current issue:

- Fetch is the strategic future interface, but current auth is still role and bot centric.
- Outside-world answers exist in practice, but there is no clean business policy toggle.
- BooneOps tiers need clearer names and capability boundaries.

### Inventory

Files:

- `app/routes/inventory.py`
- `app/database/queries/inventory.py`

Current controls:

- Requires a logged-in user for all routes.
- Uses `is_manager(user)` for many create/edit/import/count/tag flows.
- Manager roles are `admin`, `project_manager`, and `sales`.

Current writes:

- Writes to `retriever_inventory`.
- Creates and updates sites, zones, customers, products, transactions, imports, physical counts, approvals, and inventory audit rows.

Current issue:

- Inventory already has a useful split between view access and manager write access.
- That split should become formal capabilities instead of a hardcoded role list.

### PrePress

Files:

- `app/routes/prepress.py`
- `app/database/queries/prepress.py`
- `app/prepress/save_job_ticket.py`

Current controls:

- Requires a logged-in user.
- Does not currently have role-level gates for most actions.
- Actor names are normalized from full name or username to PrePress operator names.

Current reads:

- Reads MIS/Postgres invoice and job data.
- Reads `switch_shared` prepress operator data.
- Reads `retriever_prepress` workflow state.

Current writes:

- Writes to `retriever_prepress` invoice and job-part state.
- Updates hold, needs data, working started, completed state, invoice notes, owner history, job-part notes, and proof events.
- Can save PrintSmith job-ticket PDFs to file server job folders when enabled.
- Uses PrintSmith report/API credentials for job-ticket saving.

Current issue:

- PrePress is heavily used and mission-critical.
- Broad logged-in access may have been acceptable because the user group is small and trusted.
- It should stay on old Retriever until the new model is proven.

### DSF

Files:

- `app/routes/dsf.py`
- `app/database/queries/dsf.py`
- `app/database/mis_client.py`
- `app/templates/dsf/partials/invoice_detail.html`

Current controls:

- Requires a logged-in user.
- Does not currently have role-level gates for DSF write actions.
- Imports `is_admin_user`, but does not use it.

Current reads:

- Looks up PrintSmith/MIS invoices and job parts.
- DSF chat builds an invoice-scoped context and calls Claude.

Current writes to PrintSmith/Postgres:

- Assign project manager.
- Set proofreader to DSF.
- Auto-assign job locations.
- Clean job descriptions.
- Generate invoice title.
- Add handling fee.
- Subtract from shipping.
- Update shipping method.
- Set CHC wanted date.

Current issue:

- DSF contains deterministic if/then writes to PrintSmith.
- There is an invoice-scoped LLM chat nearby, but the LLM is not supposed to perform writes.
- DSF should become the first module behind the future LAN action service, but only after Fetch and auth are stable.

### Proofs

Files:

- `app/routes/dashboard.py`
- `app/database/queries/proofs.py`
- `database_integration_simplified.py`
- `switch_api_integration.py`

Current controls:

- Main Proofs page redirects to login when auth is enabled.
- Some detail/action endpoints use `get_current_user`, which can be `None`.
- Admin panel/test-mode endpoints require admin.
- Review webhook uses `X-Webhook-Secret`, not user login.

Current writes:

- Writes proof workflow state to MySQL `pm_review`.
- Sends data to Switch workflows.
- Can update MIS proof date.
- Can remove invoices from the workflow tables.

Current issue:

- Some looseness may exist for legacy HTMX fragments, Switch webhooks, and internal LAN assumptions.
- Rebuild should make machine/webhook auth explicit instead of relying on partial openness.

### Help

Files:

- `app/routes/help.py`
- `app/templates/help/*`

Current controls:

- Requires a user when auth is enabled.
- Shows module help based on current feature flags and user state.

Current writes:

- None.

## Why The Current Mess Exists

The current system is not random. It reflects the order Retriever grew:

- Proofs began as a PM workflow dashboard tied to Switch and MIS.
- Local auth was added to remove dependency on Switch login.
- Admin user management was added later.
- PrePress became a real production tracker with MySQL workflow state.
- Inventory added stronger manager-style write controls.
- Fetch added LLMs, conversation memory, uploads, source retrieval, web search, and BooneOps routing.
- BooneOps bot levels were layered into the existing user table to avoid a separate permission system.

The rebuild should preserve the working ideas:

- One internal app shell.
- Feature/module visibility.
- Role-based differences.
- BooneOps tiers.
- Manager-only inventory writes.
- PrePress actor attribution.
- Machine auth for webhooks.
- Read-only LLM data access by default.

But it should replace accidental coupling:

- Local passwords as the main front door.
- Role names that mix job function, app admin, and BooneOps power.
- Broad logged-in write access for DSF and PrePress.
- Proofs routes with inconsistent auth expectations.
- Fetch bot override as the main capability model.

## Target Auth Model

### Layer 1: Cloudflare Access

Cloudflare Access should protect `retriever.boonegraphics.net`.

Recommended settings:

- Require Boone email.
- Require MFA for everyone, including Master Tate.
- Use a practical session duration, such as 24 hours.
- Consider trusted-device posture later, but do not make that a launch blocker.

Cloudflare answers one question:

> Is this person allowed to reach Retriever at all?

Cloudflare should not decide DSF, PrePress, Fetch, or BooneOps permissions.

### Layer 2: Retriever Profile

After a person passes Cloudflare, Retriever should look up or create a local profile.

The profile should store business authorization data:

- email
- display name
- active/pending/blocked status
- department
- job role
- module access
- capabilities
- BooneOps level
- cost/LLM policy flags if needed
- audit metadata

Retriever answers the business question:

> What can this person see, ask, schedule, or change?

### Recommended User Bootstrap

Keep it simple at launch:

1. Seed Master Tate as the only full admin/operator.
2. When another Boone email passes Cloudflare for the first time, auto-create a **pending user** profile.
3. Pending users see a simple "Access pending" page.
4. Admin assigns module access and BooneOps level.
5. User becomes active.

This avoids building a full user group import on day one. It also avoids letting every Boone email user into Fetch by accident.

### User States

Use explicit states:

- **Pending:** passed Cloudflare, no Retriever permissions yet.
- **Active:** allowed to use assigned modules.
- **Suspended:** known user, temporarily disabled.
- **Blocked:** known user who should not be allowed in, even if Cloudflare allows the email.

### Passwords

For the new Retriever, passwords should not be the normal login path.

Recommended:

- Use Cloudflare identity as the login.
- Keep emergency local admin login only if truly needed, disabled by default or LAN-only.
- Do not require ordinary employees to remember a Retriever password.

## Roles, Capabilities, And BooneOps Levels

Separate these concepts:

### Job Role

Who the person is in the business:

- Owner/admin
- Project manager
- Sales
- Production
- PrePress
- DSF operator
- Shipping
- Viewer

### Module Access

What parts of Retriever they can open:

- Fetch
- Proofs
- DSF
- PrePress
- Inventory
- Admin
- Help

### Capability

The exact thing they can do:

- `fetch.ask_internal`
- `fetch.ask_general`
- `fetch.email_cleanup`
- `fetch.upload`
- `fetch.schedule_report`
- `inventory.view`
- `inventory.adjust_stock`
- `prepress.view_wip`
- `prepress.update_wip`
- `dsf.view_invoice`
- `dsf.run_actions`
- `admin.manage_users`

### BooneOps Level

How powerful the AI/operator layer is:

- **None:** no BooneOps broker access.
- **Light:** current Discord PrintSmith-channel style behavior, slightly tightened.
- **Medium:** Light plus scheduled reports inside Retriever.

Owner/operator work beyond Medium is not a Retriever web-app permission. It belongs in Cursor, Telegram, or other LordTate operator environments.

## BooneOps Levels In Plain English

### BooneOps Light

Default employee AI helper for Boone work.

Allowed:

- answer read-only PrintSmith-style questions
- use `/printsmith` for live Boone PrintSmith operational questions
- summarize invoice/job/customer facts allowed by role
- answer internal knowledge questions
- use `/docs` for vendor/tool documentation across XMPie, Enfocus, PrintSmith help/schema, DSF, MarketDirect StoreFront, SmartCanvas, and related Boone tools
- produce report-style answers
- clean up email text if Fetch capability allows it

Not allowed:

- write to databases
- change PrintSmith
- move locations
- create cron/system jobs
- deploy apps
- modify dashboards
- send messages as BooneOps without a controlled workflow

### BooneOps Medium

Trusted reporting tier.

Allowed:

- everything in Light
- create scheduled reports inside Retriever
- manage own scheduled reports
- possibly request shared scheduled reports if the user's role allows it

Not allowed at launch:

- raw cron creation
- direct server changes
- direct database writes
- production deployments
- DSF/PrePress write actions
- `/printsmith-estimate` usage. That is a separate estimating skill and outside Retriever scope.

## Fetch Policy

Fetch should be the first new module.

### Preserve Current Fetch Features

Do not lose:

- conversation sidebar/history
- email cleanup shortcut
- skill/prompt hints at the bottom
- upload support
- saved private library, if still desired
- status/model bar
- BooneOps bot label/status
- source panels
- report downloads
- thread reports
- slash commands such as `/help`, `/sources`, `/health`
- admin/user preview behavior, if still useful

### Outside-World LLM Toggle

Add a simple admin setting:

> Allow general outside-world questions.

Recommended states:

- **Off:** Fetch answers only Boone/internal/vendor/upload questions.
- **On:** Fetch can answer general questions, using web search/model knowledge as allowed.

Recommended launch default:

- On for Master Tate and early testers.
- Decide before broader employee rollout whether it is on by default.

Why allow it:

- It makes Fetch stickier.
- Employees are more likely to use one tool.
- Email help, Excel help, vendor help, and general business questions are naturally mixed.

Risks:

- token cost
- distraction
- weaker work focus
- web content risk

Mitigations:

- visible model/status bar
- per-user or per-role usage reporting
- route Boone/internal questions to cheaper models where possible
- rate limits
- admin kill switch
- no write capabilities tied to general answers

### Fetch Routing

Recommended routing:

- Boone operational PrintSmith questions use `/printsmith`.
- Vendor/tool documentation questions use `/docs`.
- Upload questions use Retriever Fetch.
- BooneOps Light/Medium questions route to BooneOps broker when needed.
- General questions use the outside-world LLM path only if enabled.
- Dangerous requests should explain that Retriever cannot perform that action from chat.

## Module And Action Matrix

Legend:

- **RO:** read-only
- **MW:** MySQL write
- **PW:** PrintSmith/Postgres write
- **LLM:** can involve model output
- **Audit:** should be logged
- **LAN:** should eventually use inside-firewall LAN action service

| Module | Action | Class | Notes |
|---|---|---:|---|
| Admin | Manage users and roles | MW, Audit | Master Tate only at first. Later limited admin capability. |
| Admin | Assign BooneOps level | MW, Audit | Should be separate from app admin where possible. |
| Fetch | Ask Boone/internal question | RO, LLM | Allowed by Fetch access. |
| Fetch | Ask general outside-world question | RO, LLM | Controlled by admin toggle and per-user capability. |
| Fetch | Clean up email | LLM | Ephemeral today. Keep available. |
| Fetch | Upload file for current conversation | MW, LLM | Writes upload metadata/extracted text. Audit lightly. |
| Fetch | Save upload to private library | MW, LLM | User-scoped, should be visible in privacy wording. |
| Fetch | Delete/rename conversation | MW | User-owned data. |
| Fetch | Download BooneOps report artifact | RO | Enforce broker policy and user access. |
| Fetch | Schedule report | MW, LLM, Audit | BooneOps Medium. Inside Retriever, not raw cron. |
| Proofs | View invoice/proof dashboard | RO | Module access required. |
| Proofs | Confirm/send to customer review | MW, Audit, LAN later | Writes workflow state and calls Switch. |
| Proofs | Reject proof | MW, Audit, LAN later | Writes workflow state and calls Switch. |
| Proofs | Save proof date to MIS | PW, Audit, LAN | PrintSmith/Postgres write. |
| Proofs | Review webhook receive customer decision | MW, Audit | Machine auth, not user login. |
| DSF | Look up invoice | RO | DSF view capability. |
| DSF | Scoped invoice chat | RO, LLM | Must not perform writes. |
| DSF | Assign PM | PW, Audit, LAN | Deterministic action. |
| DSF | Set proofreader to DSF | PW, Audit, LAN | Deterministic action. |
| DSF | Auto-assign locations | PW, Audit, LAN | Must remain rule-based. |
| DSF | Clean descriptions | PW, Audit, LAN | Deterministic string cleanup. |
| DSF | Generate invoice title | PW, Audit, LAN | Rule-based today. |
| DSF | Add handling fee | PW, Audit, LAN | Customer-specific action. |
| DSF | Subtract shipping | PW, Audit, LAN | Customer-specific action. |
| DSF | Update shipping method | PW, Audit, LAN | Rule-based, uses customer/zip/job code rules. |
| DSF | Set CHC wanted date | PW, Audit, LAN | Customer-specific action. |
| PrePress | View WIP | RO | Heavily used, keep old Retriever until proven. |
| PrePress | Toggle hold/needs data/working/completed | MW, Audit | Writes `retriever_prepress`. Not PrintSmith write. |
| PrePress | Set invoice/job notes | MW, Audit | Writes `retriever_prepress`. |
| PrePress | Add proof event | MW, Audit | Writes `retriever_prepress`. |
| PrePress | Save job ticket PDF | PW/API, file write, Audit, LAN | Uses PrintSmith token/API and file server access. Move later. |
| Inventory | View dashboard/products/customers | RO | Module access required. |
| Inventory | Manage sites/zones/customers/products | MW, Audit | Manager capability. |
| Inventory | Pull/add stock | MW, Audit | Production-impacting, keep explicit. |
| Inventory | Import CSV | MW, Audit | Manager capability. |
| Inventory | Physical counts | MW, Audit | Manager capability. |
| Help | View help | RO | Available to active users. |

## LAN Action Service Policy

The LAN action service is for sensitive work that should execute inside the Boone firewall.

It should be a sibling service on `bggol-vesko01`, not a generic SQL proxy.

Good endpoint shape:

- one endpoint per business action
- signed requests from new Retriever
- strict input validation
- known service account
- audit requested/succeeded/failed
- no LLM-generated SQL
- no generic `run_sql`

First DSF service scope should be dry-run/read actions and one low-risk write after approval.

Do not put BooneOps Light/Medium behind this action service unless they need to perform production writes. They should stay fast and simple.

## Audit Policy

Audit logs should answer:

- who requested the action
- what capability allowed it
- what module it came from
- what record was affected
- whether it was read, MySQL write, PrintSmith write, file write, LLM action, or broker action
- whether it succeeded or failed
- request ID / correlation ID

Recommended audit levels:

### Light Audit

For ordinary read/LLM interactions:

- Fetch question metadata
- route target
- model
- token counts
- user
- timestamp

Do not log sensitive full prompts everywhere by default without a retention decision.

### Standard Audit

For workflow writes:

- requested action
- before/after when practical
- target invoice/product/job
- user
- result

### Strict Audit

For PrintSmith/Postgres writes, Switch actions, LAN service actions, scheduled reports, and admin role changes:

- log requested before execution
- log succeeded or failed after execution
- include correlation ID
- include validated payload summary
- include error category

## Answering The Launch Questions

### Will Master Tate be the only person with auth at first?

Recommended: **Master Tate is the only full admin/operator at first.**

But other users can still pass Cloudflare. They should land as pending users until approved.

This gives you a clean launch path:

- you test alone
- then a few trusted users appear as pending
- you approve them one by one
- you assign Fetch only, then later more modules

### Will people show up in auth once they get past Cloudflare?

Recommended: **yes, but as pending users.**

Plain English:

- Cloudflare says, "This is a Boone email user."
- Retriever says, "I recognize this email, but it has not been assigned access yet."
- Admin sees the pending user and assigns modules/capabilities.

This is simpler than manually pre-building every user while still preventing accidental access.

### Should we build a user group first?

Recommended: **not for launch.**

Start with:

- Master Tate seeded as admin.
- Auto-created pending profiles.
- Manual approval.

Add groups later when there are enough users to justify them.

Future groups could be:

- PrePress
- Project Managers
- Sales
- DSF Operators
- Shipping
- Admins
- Fetch Beta

### Should Fetch have an Outside World LLM toggle?

Recommended: **yes.**

Make it an admin setting, not a code change.

Suggested setting:

- `fetch.general_questions_enabled`

Optional later settings:

- per-role general question access
- monthly token budget
- per-user daily soft limit
- web search enabled/disabled

## Recommended First Build Scope

For the new Retriever rebuild, auth should come before Fetch.

Minimum first version:

1. Cloudflare-protected app shell.
2. Master Tate admin profile.
3. Pending user auto-provision from Cloudflare identity.
4. Admin page to approve users.
5. Role/capability assignment.
6. Fetch access capability.
7. BooneOps level assignment: None, Light, Medium.
8. Outside-world LLM toggle.
9. Audit table for auth/admin changes and Fetch route metadata.

Do not rebuild DSF or PrePress until this foundation is stable.

## Open Decisions

These do not block the first design, but should be decided before implementation:

1. **Where should pending users be stored?**  
   Recommended: same Retriever auth database as normal users, with status `pending`.

2. **Should employee profiles be auto-created for any Boone email that passes Cloudflare?**  
   Recommended: yes, as pending only.

3. **Should general Fetch questions be enabled for all active Fetch users at launch?**  
   Recommended: enabled for beta users first, then broaden if cost/distraction is acceptable.

4. **Should local password login remain?**  
   Recommended: emergency admin only, disabled by default or restricted to LAN.

5. **Should PrePress users be split by operator identity immediately?**  
   Recommended: not for first Fetch launch. Do it before PrePress moves.

6. **Should DSF write permissions be per-action or one DSF operator bundle?**  
   Recommended: start with one DSF operator bundle, track per-action audit internally, then split if needed.

## Non-Negotiables

- Cloudflare Access required for everyone.
- LLMs do not get direct write credentials.
- No generic SQL execution endpoint.
- Owner/operator actions are not Retriever web permissions.
- PrintSmith/Postgres writes require explicit action paths and audit.
- PrePress stays on old Retriever until the new action model is proven.
- DSF is the first write module to move behind the LAN action service.
- Current Fetch product features must be preserved.

