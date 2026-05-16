# Product

## Register

product

## Users

Retriever is for Boone Graphics employees using an internal operations tool during real production work. Primary users include Master Tate as owner/admin, then project managers, sales, production, PrePress, DSF, shipping, and other employees as modules are rebuilt.

Users are usually trying to answer or act on Boone work quickly: ask Fetch for operational help, look up live PrintSmith facts, use vendor/tool docs, manage their own access-dependent workflows, and later move through rebuilt modules such as PrePress, DSF, Proofs, and Inventory.

## Product Purpose

Retriever is the employee-facing front door for Boone operational help. The first new module is Fetch, but the app shell and auth foundation must come first so every later module has a trustworthy place to live.

Success means employees feel that Retriever is one coherent internal tool: fast, sharp, understandable, and safe. Admin is a normal module in the shared shell, not a separate admin site. Fetch should eventually feel useful enough that employees choose it over Discord or ad hoc help, but without giving an LLM direct write power.

## Brand Personality

Modern, sharp, efficient.

The interface should feel like a well-run production desk: clear hierarchy, fast scanning, strong alignment, restrained color, and no fake personality. It should feel current without feeling trendy, and operational without feeling bare.

Current Fetch is a positive reference. Keep the layout, scale, left-side conversation behavior, and logo-at-top feel. Improve it with modestly more color, clearer font hierarchy, cleaner spacing, and better consistency rather than replacing the layout.

## Anti-references

- Generic AI/SaaS look: pastel gradients, rounded blobs, fake delight, empty optimism, oversized chat hero patterns.
- Consumer chatbot look: playful, loose, mascot-like, too conversational for operational production work.
- Admin island: a separate-looking backend page that does not share Retriever navigation, styling, or behavior.
- Ugly internal-tool defaults: bare forms, harsh browser styling, weak hierarchy, inconsistent spacing, and pages that look like scaffolding.
- Over-redesigning Fetch: changing the familiar layout, size, left-side conversation behavior, or logo/header feel just to make it look new.

## Design Principles

1. One Retriever shell. Admin, Fetch, Help, and future modules share the same header, left sidebar, spacing, and component vocabulary.
2. Operational clarity first. Users should always know where they are, what is enabled, what is disabled, and what action is safe.
3. Earned familiarity. Use standard app patterns where they help users move faster; do not invent affordances for flavor.
4. Sharp, not flashy. Use restrained color, strong alignment, and concise copy instead of decorative AI/SaaS patterns.
5. Trust is visible. Health, permissions, disabled states, source labels, and delayed work states should be plain and legible.
6. Familiar Fetch, improved. The Fetch rebuild should preserve the current screen's working shape while making it more polished, colorful where useful, and easier to scan.

## Accessibility & Inclusion

Target WCAG 2.1 AA for app-shell work.

Design for production employees who may be moving quickly, switching contexts, and using ordinary office displays. Use readable contrast, visible focus states, keyboard-reachable controls, non-color-only status indicators, and reduced-motion-safe interactions. Avoid dense controls without labels, tiny hit targets, and decorative motion.
