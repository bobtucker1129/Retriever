# Fetch UI Continuity

**Status:** design target  
**Source:** old `projects/Retriever/` Fetch UI inspection plus Master Tate direction on 2026-05-07  
**Scope:** first new Fetch skeleton behind the shared Retriever shell

## Plain-English Target

New Fetch should feel like current Fetch made cleaner, not like a new chat product.

The current Fetch layout is liked. Preserve the screen shape, size, left-side conversation behavior, top-logo/header feel, and rename workflow. Improve color, typography, spacing, status clarity, and component consistency without moving the furniture around.

## Preserve From Current Fetch

- Left-side conversation history inside Fetch.
- `+ New Chat` action at the top of the conversation rail.
- Collapsible conversation rail with a small expand control when hidden.
- Current-thread highlight with a colored left edge.
- Conversation title, message count, rename action, and delete action in each row.
- Rename behavior that feels like current Fetch: direct, lightweight, and available from the conversation row.
- Main chat thread to the right of the conversation rail.
- Empty thread state with Retriever logo at the top/center of the content area.
- Bottom input area with attach, email cleanup, and ask actions.
- Suggestion chips below the input.
- Status footer showing model, context usage, and mode/route state.
- Compact operational density: smaller fonts, tight spacing, and fast scanning.

## Improve Without Reinventing

- Add a little more color than the first rebuild scaffold, especially for active state, user messages, source/report labels, and status.
- Add clearer font hierarchy: title, metadata, message role, body, source/report labels, and footer status should each be distinct without feeling decorative.
- Keep the visual language sharp and operational, not playful or generic AI/SaaS.
- Make focus states and hover states clearer for keyboard and mouse users.
- Make status labels easier to read while keeping the OpenClaw-like practical footer.
- Keep component spacing consistent across sidebar rows, message bubbles, reports, sources, and input controls.

## Layout Contract

The first Fetch skeleton should use this structure:

1. Retriever app sidebar on the far left for modules such as Home, Fetch, Admin, and Help.
2. Fetch module area with its own conversation sidebar.
3. Main chat column with thread content.
4. Bottom composer area.
5. Footer status bar.

The Fetch conversation sidebar is not the same thing as the app module sidebar. It belongs inside the Fetch module and should remain visible by default.

Approximate old Fetch proportions are a good starting point:

- Conversation sidebar: around 220px wide.
- Chat thread: flexible full-height area.
- Main Fetch panel: close to viewport height, leaving room for the shared top/header shell.
- Message bubbles: up to roughly 85% width.
- Conversation row text: compact, with title and metadata.

## Status Footer Requirements

The status footer should be visible to all users.

Minimum visible fields:

- current model
- context-window usage as both a simple amount and a plain-English state
- route/source path, such as local Fetch, `/printsmith`, `/docs`, upload, BooneOps, or general
- report/job state when a delayed report is running

Context-window wording should support both numeric and operational scanning. Examples:

- `Context: 12% | low`
- `Context: 48% | medium`
- `Context: 78% | high`
- `Context: 92% | near full`

This should feel closer to OpenClaw's useful status visibility than to a hidden developer debug panel.

## Conversation Behavior

The first skeleton should include the UI shape for:

- create new conversation
- select conversation
- rename conversation
- delete conversation
- empty conversation list
- active conversation highlight
- conversation metadata such as message count or last activity
- persistence hook for current active conversation

The first implementation can use placeholder/stub data if Fetch runtime is still disabled, but the screen shape should be real enough to evaluate.

## Message And Work States

The skeleton should include visual states for:

- empty thread with logo
- user message
- Fetch/assistant message
- source panel
- upload/source badge
- report/download card
- delayed report progress card
- dependency unavailable message
- permission denied message
- model/tool failure message

Do not wait until backend routing is complete to design these states. These states are part of why Fetch will feel trustworthy.

## Slow turns and live progress (roadmap)

Heavy routes already plan for delayed-report cards with visible updates. Separately, **synchronous** asks can still take noticeable time (broker round trips, future model latency). The UI must not look idle during that wait.

- **Shipped increment:** Progressive enhancement on the HTML ask form—immediate working state (spinner, disabled Ask, plain-English “working” copy) while the navigation completes. No backend or streaming required; without JavaScript the form still posts normally.
- **Target experience:** Cursor-like muted progress or an in-thread “thinking” line that reflects ongoing work and **resolves into** the final assistant reply when the turn completes, so users do not spam duplicate messages during long work.

## Non-Goals

- Do not preserve old Fetch data shape as a compatibility requirement.
- Do not preserve old routing heuristics.
- Do not preserve backend timeout behavior.
- Do not make Fetch look like a consumer chatbot.
- Do not hide model/context status from normal users.
- Do not redesign away the left conversation rail or top-logo feel.

## Next Build Implication

The next implementation pass can start a disabled/stubbed Fetch skeleton behind the shared shell. It should prove layout, navigation, rename UI, status footer, empty states, and report/progress cards before live model routing is enabled.
