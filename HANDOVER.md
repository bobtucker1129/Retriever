# Handover: retriever-rebuild

**Session:** 2026-05-18
**Channel:** Codex

## Plain-English State

**Wiki is now live as a small Retriever module.** It appears in the left rail as **Wiki** with a **W** sign and serves `/wiki/`. The first live shape is a Boone internal knowledge hub with prominent SweetProcess procedure links, Work Instructions, Quality & ISO, Security Posture, and General Knowledge sections. Document cards and drill-down routes exist, and the first sync command foundation now exists locally. Detailed controlled summaries still need the Google Drive/internal-wiki sync to run against real production inputs plus a review workflow.

**Wiki sync foundation:** `python3 -m app.wiki.sync` can sync the internal-wiki SweetProcess link collection and a Google Drive inventory export into `wiki_sources`, `wiki_documents`, `wiki_links`, and `wiki_sync_runs`. Drive inventory cards are draft summaries, and raw source links are stored admin-only. Direct DB sync from Whitaker/OpenClaw failed because Boone MySQL `192.168.33.243:3306` is not reachable from this machine. The intended recurring architecture is now: OpenClaw inventories Google Drive, then POSTs the inventory to Retriever, and Retriever writes its own LAN/MySQL database.

**OpenClaw cron bridge:** outer workspace script `scripts/retriever-wiki-sync.js` inventories the `Final Boone` Drive root and can POST to `https://retriever.boonegraphics.net/wiki/sync/source-inventory`. OpenClaw cron job **`retriever-wiki-sync`** / **`df821699-0a39-4b86-bb34-d6c94c8858cf`** exists but is **disabled** until the Retriever endpoint is deployed and sync secrets are installed.

**PrePress remains live in the rebuild for Scott-side testing.** Old Retriever still stays up and remains the reference/parallel production surface, but new Retriever PrePress reads the same PrePress/MIS data, uses the new auth/location matrix, shows the WIP table, expands invoice parts, and can save PrintSmith job tickets to the job folder through the old Retriever token authority.

**Fetch is still in pilot mode.** The last major Fetch arc was Discord/Fetch parity and BooneOps broker behavior. Do not widen Fetch/general flags casually; keep following `PLAN.md` and the parity docs when returning to Fetch.

**Auth/admin:** Admin → Users is the current authorization matrix. Cloudflare email auto-populates, pending users show **Pending** in Last Login until approved, admins fill Full Name + Location, then set Admin/Fetch/PrePress/DSF yes-no gates plus Inventory/Proofs **No/Viewer/Manager** placeholders. Locations come from MIS `productionlocations`.

## Latest Verified Production State

- Production host: **`bggol-vesko01`** / **`BGGOL-VESKO01`**
- New Retriever runtime: **`D:\retriever-rebuild`**, service **`RetrieverRebuild`**, app on localhost **`8810`**
- Old Retriever runtime/reference: **`D:\Repository\pm-review-dashboard-ContexEng`**, old service on **`8000`**
- Public URL: **`https://retriever.boonegraphics.net`** behind Cloudflare Access
- Current deployed SHA verified: **`777886d4d63863bfab5ccb360c5b37203dd228ed`**
- `/health/live` verified **200 OK**
- `/wiki/` verified live behind Cloudflare Access with SweetProcess links and Wiki categories visible
- Local tests after OpenClaw bridge work: **`python3 -m pytest -q` → 324 passed, 1 PyPDF2 deprecation warning**

## What Landed This Session

- Added the first Wiki sync command foundation:
  - `python3 -m app.wiki.sync --internal-wiki`
  - `python3 -m app.wiki.sync --drive-inventory path/to/export.json|csv`
- Added Retriever sync ingest endpoint:
  - `POST /wiki/sync/source-inventory`
  - gated by `WIKI_SYNC_ENABLED=true` and a strong `WIKI_SYNC_TOKEN`
- Added outer OpenClaw operator script:
  - `scripts/retriever-wiki-sync.js`
  - dry-run proved `Final Boone` inventory: **1,362 files from 1 root**
- Registered disabled OpenClaw cron job:
  - name `retriever-wiki-sync`
  - id `df821699-0a39-4b86-bb34-d6c94c8858cf`
  - schedule `30 5 * * *` America/New_York
- Added repository write methods for Wiki source upserts, sync-run tracking, document upserts, and link replacement.
- Added parsing/classification for SweetProcess links and Drive inventory rows.
- Made `/wiki/` use synced SweetProcess links when present, with the built-in list as fallback.
- Kept Google Drive/ISO source URLs admin-only in `wiki_links`.
- Added the Retriever **Wiki** module shell:
  - sidebar item **Wiki** with **W** sign;
  - `/wiki/` route;
  - active-user access through the shared Retriever shell.
- Added Wiki catalog storage/read architecture:
  - `wiki_sources`
  - `wiki_documents`
  - `wiki_document_versions`
  - `wiki_sections`
  - `wiki_links`
  - `wiki_sync_runs`
- Added controlled document drill-down route shape at `/wiki/doc/{slug}`.
- Seeded fallback cards for core ISO / Work Instruction examples including `WI-015`, `WI-018`, `WI-022`, `WI-023`, `WI-024`, `WI-030`, `M-001`, and `SOP-023`.
- Promoted the Boone internal-wiki SweetProcess procedure links to the top of the Wiki page. These are daily-use links and should remain prominent.
- Reshaped Wiki into the intended categories:
  - SweetProcess Procedures
  - Work Instructions
  - Quality & ISO
  - Security Posture
  - General Knowledge
- Inventoried the shared Google Drive ISO folder enough to identify the major source spine:
  - `Final Boone`
  - `External Documents`
  - `Training Documents`
  - `Updates & In-process`
  - `Archive`
- Confirmed architecture direction with Master Tate:
  - Google Drive/internal-wiki remain source systems.
  - Retriever stores canonical Wiki records and controlled summaries.
  - Raw ISO docs should not be exposed directly to normal Wiki readers.
  - Vector/search can be added later as an index, not the canonical source.
  - Fetch integration should later be a tiny feature-flagged read-only `search_wiki(query)` adapter, not a broad Fetch rewrite.
- Migrated/ported the PrePress shell into the rebuild.
- Wired PrePress WIP to existing MySQL/MIS data sources:
  - `retriever_prepress`
  - `switch_shared.prepress`
  - MIS invoice/job-part/location data
- Used auth locations to map operators; Scott’s location is **`100/Scott Working`**.
- Restored old PrePress invoice **parts expander** behavior.
- Restored **Ticket View + Save** behavior and old-style save banner.
- New Retriever uses the old Retriever PrintSmith token proxy instead of becoming token authority during side-by-side testing.
- Fixed Windows timezone failure by adding `tzdata`; real ticket save succeeded:
  - `D:\SwitchJobs\Jobs_26\103166_TestingForScott\Remote\Y1_JobTicket_103166_20260517-175120.pdf`
- Removed stale auth ideas from earlier attempts, including BooneOps toggles and old Fetch-level/regular-LLM toggles.
- Visual PrePress pass: tighter controls, old-style cell dividers, wider work area, compact top/footer controls.

## Secrets / Env Notes

The PrintSmith proxy URL/key were found in the general OpenClaw/workspace envelope and applied to the Windows new Retriever env. Do **not** paste, print, or commit those values.

New Retriever PrePress ticket save expects:

- `PRINTSMITH_TOKEN_AUTHORITY_MODE=using_old_authority`
- `PRINTSMITH_TOKEN_PROXY_URL` ending at the old `/api/printsmith-token` endpoint
- `PRINTSMITH_TOKEN_PROXY_KEY`
- `PREPRESS_JOB_TICKET_SAVE_ENABLED=true`

## Repo Hygiene

Tracked code tree was clean after the final pushed Wiki commits. This wrap updates tracked handoff docs. Untracked local noise still exists and should not be mixed into normal commits:

- `.DS_Store`
- `.cursor/`
- `retriever_favicon_package/`
- `timeline.md`

## Still Open / Next Session

1. Deploy the Retriever sync endpoint and enable the disabled OpenClaw cron:
   - add `WIKI_SYNC_ENABLED=true` and `WIKI_SYNC_TOKEN=<strong secret>` to `D:\retriever-rebuild\env\retriever.env`;
   - add matching `RETRIEVER_WIKI_SYNC_TOKEN` or `WIKI_SYNC_TOKEN` to OpenClaw cron's environment;
   - add `RETRIEVER_WIKI_CF_SERVICE_TOKEN` if Cloudflare Access blocks the POST;
   - run `openclaw cron run df821699-0a39-4b86-bb34-d6c94c8858cf --expect-final --timeout 900000`;
   - enable with `openclaw cron enable retriever-wiki-sync` after a clean run.
2. Verify raw ISO document links remain hidden from normal readers and mark summaries draft/review/approved before trusting them as controlled internal knowledge.
3. Add admin/operator visibility for last sync status, document freshness, and summary review state.
4. Later, add a narrow Fetch-to-Wiki lookup adapter so Fetch can answer and link into Wiki pages without destabilizing Fetch.
5. Continue live side-by-side PrePress comparison against old Retriever when Scott reports issues.

## Copy-Ready Next Kickoff

```text
read CODEX.md and continue

Goal: Continue Retriever Wiki from the deployed shell/catalog, new `python3 -m app.wiki.sync` foundation, and disabled OpenClaw cron bridge. Deploy/enable `POST /wiki/sync/source-inventory`, install the sync secrets, run the disabled OpenClaw cron once, then add review/freshness visibility before enabling the recurring schedule.

Notes: Fetch is fragile; do not change Fetch except a later feature-flagged read-only search_wiki adapter. OpenClaw cron job `retriever-wiki-sync` exists disabled (id `df821699-0a39-4b86-bb34-d6c94c8858cf`). Latest production SHA 777886d4d63863bfab5ccb360c5b37203dd228ed; /wiki/ is live behind Cloudflare Access; local tests after bridge work were 324 passed. Run tests before push and verify live after deploy.
```
