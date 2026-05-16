# Shared Layout Shape

**Status:** confirmed brief  
**Source:** Impeccable shape flow, 2026-05-06  
**Scope:** Retriever shared app shell before Fetch UI work

## Feature Summary

The shared Retriever shell is the common frame for Admin, Fetch, Help, and later modules. It preserves what current Retriever already does well: a practical internal app with left navigation, familiar operational pages, and no separate-looking admin area.

This is a cleanup and unification pass, not a reinvention.

## Primary User Action

Users should instantly understand: "I am in Retriever, these are my modules, this is the current page, and Admin is just another module I can access because I'm allowed."

## Design Direction

Color strategy: restrained, but not gray-only.

Use tinted neutrals, one sharp primary accent for active nav and primary actions, semantic colors for status, and a little more color than the current scaffold where it helps page recognition and hierarchy.

Scene: Boone employees using Retriever across office and shop-floor contexts, on normal monitors, sometimes moving quickly and needing high legibility without visual noise.

Reference direction: close visual continuity with old Retriever, refined. Keep the operational left-sidebar app feel and enough familiar structure that employees recognize it immediately, while sharpening alignment, spacing, hierarchy, and component consistency.

Current Fetch is liked. The rebuild should keep its layout, size, left-side conversation behavior, and logo-at-top feel. The improvement target is modest polish: a little more color, a few more font variations for hierarchy, cleaner spacing, and more consistent component styling.

## Scope

- Fidelity: mid-fi cleanup with production-minded choices.
- Breadth: whole shared shell, including home/app shell, Admin users page, pending page, disabled Fetch page, and health/status links.
- Interactivity: normal server-rendered app interactions, with simple hover/focus states and clear form feedback.
- Time intent: improve the scaffold enough that future Fetch UI work has a coherent home.

## Layout Strategy

Use one shared template: top header, left sidebar, main content. Sidebar carries module navigation: Fetch, Admin, Help, and future modules only when available.

Admin appears in the same nav as everything else, only for admins. Content uses page titles, short helper text, and aligned sections, not isolated standalone pages.

Fetch should keep its own left-side conversation sidebar inside the module area, separate from the app module sidebar. Conversation history, current thread selection, and rename/delete controls are core Fetch navigation, not optional polish. The left-side behavior should match current Fetch while improving the visual finish.

## Key States

- Default: active admin sees shell plus Admin nav.
- Pending: simple access-pending page that still feels like Retriever.
- Disabled module: Fetch disabled page explains it is not enabled yet.
- Forbidden: non-admin trying Admin gets a plain denial.
- Empty: no pending users shows a calm empty state, not a blank list.
- Error/degraded: health/status uses readable state labels without exposing secrets.

## Interaction Model

Sidebar navigation is stable. Admin user actions are inline forms, not modals. Primary actions like Approve are visually primary; destructive actions like Block are clearly dangerous but not visually dominant.

Focus states must be visible for keyboard use.

Fetch should expose status in the same practical spirit as OpenClaw: current model, context-window level, active route/source path, and report/job state should be visible to all users without making the interface feel like a developer console.

Context-window level should show both a simple amount and an operational state, for example a percentage plus low, medium, high, or near-full wording.

## Content Requirements

Keep copy short and operational. Avoid "AI assistant" personality in the shell.

Labels should say what actions do: Approve, Block, Grant Fetch access, Save BooneOps level.

Disabled Fetch copy should be direct: Fetch is not enabled yet because the auth shell is being proven first.

## Implementation References

- `layout.md`
- `typography.md`
- `color-and-contrast.md`
- `interaction-design.md`
- `harden.md`
- `FETCH_UI_CONTINUITY.md`

## Resolved Visual Continuity Decision

The final shell should stay close to current Retriever's visual details. The target is not a new identity; it is current Retriever made cleaner, sharper, and more consistent. Inspect old Retriever directly before freezing `DESIGN.md`.

For Fetch specifically, preserve the current layout and interaction model unless there is a clear reason to change it. Improve color, typography, spacing, and consistency; do not reinvent the screen.

The detailed Fetch continuity target is now captured in `FETCH_UI_CONTINUITY.md`.
