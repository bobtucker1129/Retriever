# Fetch Trust Plan

**Status:** planning document  
**Scope:** new Retriever rebuild, first Fetch implementation  
**Sources:** `AUTH_REDESIGN.md`, `REVIEW-2026-05-04-OPUS.md`, old `projects/Retriever/` Fetch reference

## Plain-English Summary

Fetch is the first thing most Boone employees should use in the new Retriever. It has to feel alive, predictable, and honest.

Old Fetch is not a compatibility target. It does not work well enough, and nobody depends on it today. That is exactly why new Fetch should be built first.

## Current rebuild slice (foundation, not full routing)

This section is what **shipping code does today** on **new Retriever** (**`RetrieverRebuild`** on Windows **`bggol-vesko01`**, **`8810`**, Cloudflare **`retriever.boonegraphics.net`**). The rest of this document is still the **target** trust and routing contract.

### BooneOps broker vs general internet answers (planned wiring)

Phase 1 product intent: **`#printsmith`-style BooneOps turns** ride the **BooneOps broker** over Tailscale (same contract as **`projects/booneops-bots/FETCH_HANDOFF.md`**). Operators hold integration **`BOONEOPS_BROKER_ENABLED=false`** until **`docs/runbooks/booneops-broker-fetch-windows.md`** Tailscale **`GET /health`** checks pass.

**Separate lane:** **`FETCH_GENERAL_QUESTIONS_ENABLED`** (**`fetch.general_questions_enabled`**) gates **general outside-world LLM** use. Leave it **`false`** until a later rollout pairs admin policy with **`fetch.ask_general`**. That general toggle does **not** need to turn on for internal BooneOps/`#printsmith`-equivalent routing.

**Combined gate:** even with the broker configured, employee-visible BooneOps replies require the normal ask gates (**active Fetch access**, **`FETCH_ENABLED`**, broker routing implementation live—not this doc’s assumption until code ships).

- **In service:** Fetch **shell** for users with Fetch module or capability access; **conversation CRUD** in **`retriever_cloudflare`** after migration **`0002_fetch_conversations`**.
- **Ask path:** **`POST /fetch/conversations/{id}/ask`** is **gated** by active user, Fetch shell access, and **`FETCH_ENABLED`**. When **`FETCH_ENABLED` is off**, the handler **redirects** without saving a user message. When on, it **persists** the user turn and appends a **fixed stub assistant reply**—**no** live **LLM**, **PrintSmith**, **docs**, **BooneOps**, **upload**, or **delayed-report** calls *(until broker/model routing replaces the stub in code)*.
- **`FETCH_ENABLED` caveat:** In code, that flag only unlocks the **stub** behavior, but **startup validation** still **requires** **`MODEL_PROVIDER`**, **`MODEL_DEFAULT`**, and (for Anthropic) **`ANTHROPIC_API_KEY`** whenever **`FETCH_ENABLED=true`**. **Production** should keep **`FETCH_ENABLED=false`** until operators follow **`deploy/WINDOWS_FETCH_RELEASE.md`** for a deliberate enablement or pilot.
- **Legacy coexistence:** **Old Retriever** on port **`8000`** remains PrintSmith token authority and PrePress/DSF host; **old Fetch** is **off**.

## Real model and tool enablement

Before employees rely on **live** routing, delayed reports, and tool calls, work through the checklist in **`deploy/WINDOWS_FETCH_RELEASE.md`** plus the failure-state tables and capability matrix later in this document.

The old implementation is still useful as a reference for product ideas: one employee-facing chat should answer Boone questions, use PrintSmith data, look up vendor/tool documentation, clean up emails, accept uploads, show sources, and return report downloads. The rebuild should keep the ideas that are actually valuable, but it does not need to preserve old code paths, old data, old UI quirks, or old routing behavior.

The rebuild must fix the trust problem: slow PrintSmith and DSF list/export requests must not sit in chat until they hit a backend timeout. If Fetch cannot confidently finish a request inside the normal chat window, it should quickly say so, turn the request into a visible report job, and keep the user informed while the work continues.

## Trust Goals

Fetch should be trusted because:

- it routes questions to the right source instead of guessing silently
- it explains what it is doing when work takes time
- it fails in plain English with a useful next step
- it launches with a focused set of useful Fetch features instead of inheriting old Fetch baggage
- it keeps customer files and Boone data away from the wrong model or service
- it never gives an LLM direct write credentials
- it makes operational readiness visible before employees depend on it

Fetch should not pretend every question is the same. A quick vendor-doc answer, a customer-file upload, and a full DSF exception report need different paths.

## Route Map

Prefer explicit routing over clever keyword guessing. The user should be able to see which route Fetch used in the status area or answer metadata.

| Request type | Route | First-version policy |
|---|---|---|
| Boone PrintSmith operational questions | `/printsmith` | Read-only live Boone PrintSmith path. |
| Vendor/tool documentation | `/docs` | Enfocus, XMPie, PrintSmith help/schema, DSF, MDSF, SmartCanvas, Switch, and related docs. |
| Uploaded files | local Fetch | Keep uploads local to the conversation/private library unless a later explicit policy allows otherwise. |
| Email cleanup | local Fetch | Ephemeral helper; do not write the cleaned email into conversation history by default. |
| Internal Fetch library/private sources | local Fetch | Use Retriever-owned retrieval and source display. |
| BooneOps Light / `#printsmith` equivalent | BooneOps broker (Tailscale) | Operational helper via OpenClaw Phase 1 contract; **`BOONEOPS_BROKER_*`** env on Fetch, **`projects/booneops-bots/BROKER.md`** on OpenClaw. |
| BooneOps Medium | BooneOps broker plus Retriever scheduled/reporting features | Trusted reporting tier, not raw cron or server access. |
| General outside-world questions | general LLM path | Only when admin setting and user capability allow it. |
| Estimating automation | out of scope | `/printsmith-estimate` is not a Retriever Fetch route. |
| Production writes | blocked from Fetch chat | DSF/PrePress/PrintSmith writes require future explicit action paths and audit. |

## Routing Rules

### `/printsmith`

Use `/printsmith` for live Boone operational data from PrintSmith and related read-only business lookups.

Examples:

- "What is the status of invoice 123456?"
- "Show open jobs for this customer."
- "Which DSF invoices need attention?"
- "Export the PrintSmith jobs matching this condition."

If the request is small and likely to finish quickly, Fetch can answer inline. If it is a list, export, broad search, or multi-record report, Fetch should use the delayed-report path before it hits a timeout.

### `/docs`

Use `/docs` for vendor and tool documentation.

Examples:

- Enfocus Switch behavior
- XMPie uPlan/uProduce/uCreate questions
- PrintSmith help or schema references
- DSF, MDSF, SmartCanvas, and related vendor/tool documentation

`/docs` should not be used as a substitute for live Boone operational data. If a question mixes documentation and live Boone facts, Fetch should say which parts came from docs and which parts came from `/printsmith`.

### Local Fetch

Use local Fetch for:

- uploaded-file questions
- private library questions
- email cleanup
- conversation summarization
- source panels from Retriever-owned retrieval
- slash commands that inspect Fetch itself

Uploads should not automatically route to BooneOps or outside-world tools. If a future feature needs to send extracted upload text to another service, that must be a separate policy decision with visible user wording.

### BooneOps Light

BooneOps Light is the normal employee operational helper.

Allowed:

- read-only PrintSmith-style questions
- internal Boone operational answers
- `/printsmith` and `/docs` lookups where appropriate
- report-style answers
- source-aware explanations

Not allowed:

- database writes
- PrintSmith changes
- location moves
- cron/system job creation
- deployments
- sending messages as BooneOps outside a controlled workflow

### BooneOps Medium

BooneOps Medium is the trusted reporting tier.

Allowed:

- everything in Light
- scheduled reports inside Retriever
- managing the user's own scheduled reports
- requesting shared scheduled reports if the user's role allows it

Not allowed at launch:

- raw cron creation
- direct server changes
- direct database writes
- production deployments
- DSF or PrePress write actions
- `/printsmith-estimate`

### General Outside-World Answers

General answers can make Fetch sticky, but they need a business policy.

First-version recommendation:

- keep an admin setting such as `fetch.general_questions_enabled`
- allow Master Tate and early testers first
- require `fetch.ask_general` for normal users
- show when an answer used the general LLM path or web search
- never attach write capabilities to general answers
- do not send uploaded customer files into general-world prompts

## 30-Second Chat Wall

The normal chat experience should have a hard wall: Fetch should not leave the user staring at a spinner for more than 30 seconds.

Within 30 seconds, Fetch must do one of these:

1. answer inline
2. ask a short clarifying question
3. refuse or redirect the request in plain English
4. turn the request into a visible delayed report
5. report that a dependency is unavailable

The important rule is that heavy work should change state before timeout. The user should never have to learn that "large reports fail after waiting a long time."

## Delayed-Report Path

Use delayed reports for slow PrintSmith/DSF list, export, and broad multi-record requests.

Triggers:

- broad list requests
- export/download requests
- multi-customer or multi-invoice scans
- DSF exception summaries
- report follow-ups that reuse a prior report context
- any route that cannot confidently finish inside the 30-second chat wall

First-version user experience:

1. Fetch acknowledges the request quickly.
2. Fetch creates a report card in the conversation.
3. The report card shows what it is working on in plain English.
4. The card updates every few seconds while work continues.
5. The card makes clear whether follow-up questions will wait for this report or start a new request.
6. When ready, the same conversation shows the result summary and download/report links.
7. If the report fails, the card explains the failure and whether retry is safe.

This should feel closer to Cursor than to a dead web form. The goal is not fake personality. The goal is visible progress.

**UI roadmap:** Plain HTML ask posts should never leave the composer looking idle while the browser waits on a slow broker or model turn. Short term that means immediate client-side working state (disabled send + clear copy) without streaming. Longer term, match Cursor-style cues: a muted in-thread progress or “thinking” line that updates during the turn and collapses into the final assistant message so people do not assume the page froze or send the same prompt again.

Useful progress messages can be simple:

- "Connecting to PrintSmith..."
- "Finding matching invoices..."
- "Checking DSF status..."
- "Building the report..."
- "Formatting the download..."
- "Still working. This is a larger report, not a frozen chat."

Light playful copy such as "making coffee" can be used sparingly if product design approves it later, but operational clarity matters more than charm.

### Follow-Up Guardrail

The old failure mode gets worse when a user thinks Fetch is dead and asks the same question again.

While a delayed report is running, Fetch should show one of these choices:

- "Wait for this report"
- "Ask a separate question"
- "Cancel this report"

If the user asks a follow-up that looks related, Fetch should attach it to the running report only when that is safe. Otherwise it should explain that it will start a separate request.

### No Email Queue For Version One

Do not make email notifications a launch dependency. Version one should keep the report status in the Fetch conversation through live progress and automatic in-chat readiness updates.

Later, app notifications or email can be added if real usage shows people leave the page during long reports.

## Failure States

Every failure should tell the user what happened, what Fetch did not do, and what they can try next.

| Failure | User-facing behavior | System behavior |
|---|---|---|
| `/printsmith` unavailable | "I cannot reach live PrintSmith data right now." | Do not invent operational facts. Offer retry or docs/local answer if relevant. |
| `/docs` unavailable | "I cannot reach the docs index right now." | Fall back only to clearly labeled local/general knowledge if allowed. |
| BooneOps broker unavailable | "BooneOps is not reachable right now." | Do not keep retrying inside the same chat turn until timeout. |
| Broker auth rejected | "Fetch is not authorized to use that BooneOps route." | Log as auth/config issue; do not expose secrets. |
| Model failure | "The model failed while generating the answer." | Preserve route metadata and correlation ID for troubleshooting. |
| Tool timeout | "That tool took too long." | If safe, convert to delayed report before timeout; otherwise mark retry state clearly. |
| Delayed report pending | "The report is still running." | Keep progress card alive; prevent duplicate stacked jobs by default. |
| Delayed report failed | "The report could not finish." | Show failed stage, safe retry option, and request ID. |
| Upload extraction weak/failed | "I could not read enough text from that file." | Do not hallucinate file contents; offer upload guidance. |
| General answers disabled | "General outside-world questions are not enabled for your account." | Route nothing to outside-world models. |
| Permission denied | "Your Retriever access does not include that Fetch capability." | Audit capability denial lightly. |

Transient broker failure messages should not be fed back into retry context as if they were useful conversation memory. The old Fetch already filtered some transient failures; the rebuild should keep that idea.

## Desired Fetch Features

These are product requirements for new Fetch, not a promise to port old Fetch line-for-line. Old Fetch can be sampled for useful behavior, but the rebuild should choose the simplest reliable version of each feature.

### Conversation Experience

Preserve:

- left-side conversation sidebar/history
- thread view
- delete/rename conversation, with rename behaving like current Fetch and treated as a core workflow rather than hidden polish
- auto-title behavior
- local continuity across refresh where appropriate
- ability to resume a prior thread

The conversation sidebar is a major part of Fetch's usefulness. Users need to see their working threads, switch between them quickly, and rename conversations when a thread turns into a real job, customer issue, or recurring operational question. Keep the same left-side behavior while improving visual polish. See `FETCH_UI_CONTINUITY.md` for the first skeleton layout target.

### Email Cleanup

Preserve:

- fast email cleanup shortcut
- rate limiting
- clear distinction from normal chat
- no default conversation-history write

Email cleanup is one of the easiest ways for employees to trust Fetch quickly. Keep it simple and fast.

### Prompt Hints And Slash Commands

Preserve:

- bottom prompt/skill hints
- `/help`
- `/sources`
- `/health` for admins
- explicit `/printsmith` route
- docs/source inspection commands if still useful

The rebuild can rename commands if needed, but it should not remove the idea that users can ask Fetch what it can do and where its sources are.

### Uploads And Private Library

Preserve:

- upload support
- file validation and size limits
- conversation-tied uploads
- optional private library behavior if retained
- user-scoped/private ownership
- warnings when text extraction is weak

Before implementation, decide the exact retention wording shown to users. The trust plan assumes uploads remain local to Fetch unless explicitly routed elsewhere.

### Status And Source Visibility

Preserve:

- status/model bar
- current model display for all users
- context-window level display for all users
- route label
- BooneOps bot label/status
- source panels
- retrieval/source counts where useful
- report status

Employees do not need all technical details, but they should know whether Fetch used live PrintSmith, docs, uploads, local library, or general model knowledge. All users should also be able to see the current model and context-window level, similar to OpenClaw's visible status pattern, so long-running or context-heavy work does not feel mysterious.

Context-window display should include both a simple amount and a plain-English state, such as a percentage plus low, medium, high, or near full.

### Reports And Downloads

Preserve:

- report downloads
- thread reports
- artifact links
- report readiness inside the conversation
- safe proxying of downloads rather than arbitrary remote URLs

Improve:

- move heavy work into delayed reports before timeout
- show live progress
- reduce duplicate report jobs caused by user confusion

### Admin/User Preview

Preserve the useful part: an admin can see what Fetch looks like for a normal user.

Clarify the security part: preview mode is not a true server-side permission downgrade unless explicitly implemented that way. The new auth model should not rely on preview UI as proof of authorization behavior.

## Capability Requirements

Fetch capabilities should be explicit in Retriever auth.

| Capability | Meaning |
|---|---|
| `fetch.ask_internal` | Ask Boone/internal/vendor/upload questions through approved internal routes. |
| `fetch.ask_general` | Ask general outside-world questions when the admin setting allows it. |
| `fetch.email_cleanup` | Use the ephemeral email cleanup helper. |
| `fetch.upload` | Upload files into a conversation or private library. |
| `fetch.schedule_report` | Create or manage scheduled reports inside Retriever; BooneOps Medium. |

BooneOps level should not be hidden inside job role names. A project manager, sales user, production user, or viewer may each have different Fetch capabilities and BooneOps levels.

## Privacy And Data Boundaries

### Uploads

Uploaded files may include customer data. First-version policy:

- keep uploads tied to the user/conversation
- make private library saves explicit
- show retention wording before or during upload
- do not send uploaded customer files to general-world LLM paths
- do not route upload contents to BooneOps by default
- log metadata, not full sensitive file text, unless a separate retention decision allows it

### General LLM

General outside-world answers are allowed only when enabled.

Policy:

- do not include live PrintSmith data in general prompts unless the route explicitly allows a mixed answer
- do not include uploaded customer files
- do not allow general answers to trigger write actions
- show a visible route/status label
- track usage enough for cost and abuse review

### PrintSmith And DSF Data

Live operational data belongs behind `/printsmith` and approved BooneOps routes. DSF write actions remain outside first-version Fetch.

If a Fetch answer uses live data, it should be clear that it used live data. If it did not, it should not imply it checked PrintSmith.

## Health Checks

Fetch health must report real readiness, not only process uptime.

Minimum health dimensions:

- app process is running
- user auth/session is valid
- local Fetch database/retrieval is available
- model provider is reachable
- upload extraction dependencies are ready
- `/printsmith` route is reachable
- `/docs` route is reachable
- BooneOps broker is reachable
- broker auth/signing is valid
- report job creation works
- report polling/readiness path works
- artifact download proxy is safe and working

The user-facing health view should be plain English. Admin health can include technical detail, route names, request IDs, and timestamps.

## Implementation Notes For Later

The plan does not require old Fetch code to be ported line-for-line. It requires the new implementation to build the intended product clearly and fix the trust failures.

Useful old ideas to keep:

- slash commands run before normal routing
- uploads force local handling
- report context survives follow-up questions
- transient broker failures are filtered out of retry context
- report downloads are proxied safely
- admin health checks inspect dependencies, not just app uptime

Old behavior to redesign:

- defaulting too many unmatched questions to BooneOps
- waiting for long broker timeouts before changing UI state
- coarse "not configured" errors that hide the real failing dependency
- status/footer drift between backend answer metadata and frontend display

Old behavior that does not need compatibility support:

- old Fetch conversations
- old private library data
- old sidebar/thread storage shape
- old routing heuristics
- old frontend state management
- old broker timeout behavior

## Open Questions

These should not block writing the first Fetch implementation plan, but they must be resolved before production cutover or broad employee rollout.

- Should general outside-world answers be enabled for all active Fetch users or only beta users?
- Which old Fetch ideas are worth reusing as product requirements, if any?
- Where will production report jobs run if BooneOps remains a Tailscale runtime dependency?
- Should old Fetch conversations/private library data be ignored, archived, or migrated only on explicit request?
- What exact retention period applies to uploaded files and extracted text?
- What is the final BooneOps Light/Medium mapping to old broker bot IDs?

## Non-Negotiables

- Fetch must show progress before the 30-second wall.
- Heavy PrintSmith/DSF list and export work must use delayed reports.
- `/printsmith` is live Boone read-only operational data.
- `/docs` is vendor/tool documentation.
- `/printsmith-estimate` is outside Retriever Fetch.
- Uploads stay local unless an explicit future policy changes that.
- Email cleanup remains ephemeral by default.
- New Fetch should not be blocked by old Fetch compatibility.
- LLMs do not get direct write credentials.
- Failures must be understandable to a normal employee.
