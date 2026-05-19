# Help Orchestration And Freshness Audits

## Ownership

Retriever owns published employee Help. Help pages, Wiki cards, module copy, and approved summaries must be reviewed inside the Retriever product/admin process before employees treat them as current.

OpenClaw helps from the outside. Its job is to inventory, audit, draft report artifacts, and point humans at stale or missing Help surfaces. OpenClaw cron should not publish Help directly, rewrite controlled ISO/Wiki content, or bypass Retriever admin review.

## Current Scaffold

Outer workspace script:

```bash
cd /Users/whitakertate/Whitaker/workspace
node scripts/retriever-help-freshness.js --dry-run
```

Report artifacts:

```text
projects/retriever-rebuild/.help-freshness/help-freshness-report.md
projects/retriever-rebuild/.help-freshness/help-freshness-report.json
projects/retriever-rebuild/.help-freshness/last-run.json
```

The script is intentionally non-secret and report-only. It reads local Retriever route/template/docs metadata and any structured Help/Wiki content that exists, then writes a report under `.help-freshness/`. It does not call Retriever production, Google Drive, BooneOps, Cloudflare, model providers, or external APIs.

If structured Help content does not exist yet, the report degrades gracefully: it still scans docs, routes, templates, and Wiki scaffolding, and it records that explicit English/Spanish Help pairs have not landed.

## What The Audit Checks

- Help/Wiki/docs route and template touchpoints.
- Markdown and app files that mention Help, Wiki, docs, procedures, instructions, runbooks, or guides.
- Stale local files by modified age.
- Missing `Last reviewed: YYYY-MM-DD` style markers on Help-relevant docs.
- Draft/placeholder language such as `TODO`, `TBD`, `placeholder`, `draft`, or `summary_status: draft`.
- English/Spanish parity by filename/path markers such as `english`, `en`, `spanish`, `es`, `espanol`, or `español`.

The audit is advisory. A flagged file means "review this," not "publish a change."

## Cadence

Recommended default: **biweekly**.

Use **weekly** while Help is actively launching, while Spanish versions are being added, or after major module copy changes. Once Retriever Help stabilizes and reports are routinely clean, biweekly is enough.

Avoid daily Help audits unless there is an active migration. Daily cron noise will make stale-content signals easier to ignore.

## Disabled Cron Plan

Preferred command for an OpenClaw cron:

```bash
cd /Users/whitakertate/Whitaker/workspace && node scripts/retriever-help-freshness.js --dry-run
```

Suggested schedule:

```text
Every other Tuesday at 6:10 AM America/New_York
```

Do not enable a real cron until an operator chooses the reporting destination and review owner. The safe first step is to register it disabled, run it manually, inspect `.help-freshness/help-freshness-report.md`, and only then decide whether OpenClaw should notify a human, attach the markdown artifact, or open a draft issue/task.

## Human Review Gate

Freshness report outcomes should follow this path:

1. OpenClaw writes the report artifact.
2. A human/admin reviews flagged files and parity gaps.
3. Retriever-side Help content is edited or approved.
4. Published Help changes are verified in Retriever.
5. The next audit confirms the stale/draft/parity flag cleared.

For controlled ISO, procedure, work-instruction, or customer-sensitive material, keep the same rule as Wiki sync: source systems remain authoritative, raw source links stay admin-only unless explicitly approved, and employee-facing summaries need review before becoming trusted Help.

## English/Spanish Parity

The audit currently checks parity by explicit file/path language markers. That is enough for the scaffold and avoids inventing a schema before Help content lands.

When Retriever adds structured Help records, add a stable metadata shape such as:

```json
{
  "help_key": "fetch.asking-questions",
  "language": "en",
  "last_reviewed": "2026-05-19",
  "source_owner": "Retriever admin",
  "status": "approved"
}
```

Then update the audit to compare records by `help_key`, require both `en` and `es` where employee-facing, and flag mismatched `last_reviewed` or `status` values.

## Boundaries

- Retriever owns published Help and final employee-facing wording.
- OpenClaw cron audits/drafts only.
- No production secrets in this scaffold.
- No automatic publishing.
- No direct edits to controlled source documents.
- No Fetch/app implementation changes are required for the current scaffold.
