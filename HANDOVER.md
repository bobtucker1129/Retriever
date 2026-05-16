# Handover: retriever-rebuild

**Session:** 2026-05-17  
**Channel:** Cursor  

## Plain-English state

**Navigation:** Repo **root** is only the five **session spine** markdowns; long specs live in **`docs/planning/`**. If the folder feels noisy, open **`docs/README.md`** first — it is the single index (pilot, deploy, auth, archive, broker topology pointer).

The **live Fetch pilot** stays **narrow** (no broad rollout, no general-internet answers for everyone). Recent work has included **employee-readable threads** (structured assistant text, status lines, source-style cards, layout/CSS), **local routing** for vendor and invoice-style questions, and **parity with the Discord Fetch path** via the BooneOps broker (see `projects/booneops-bots` and the parity doc linked from `docs/README.md`).

**Auth/admin:** Admin → Users is being rebuilt into the real authorization matrix: Cloudflare email auto-populates, pending users show **Pending** in Last Login until approved, admins fill Full Name + Location, then set Admin/Fetch/PrePress/DSF yes-no gates plus Inventory/Proofs **No/Viewer/Manager** placeholders. Approval requires Full Name. Location options come from MIS `productionlocations` when the production DB user can see it.

**Hosts (short):** Retriever on Windows (`bggol-vesko01`); BooneOps broker on Whitaker over Tailscale. Long-form map: `memory/shared/seeds/2026-05-17-fetch-broker-openclaw-topology.md` in the LordTate workspace.

## Repo hygiene (earlier wrap, still true)

Someone’s working tree had **many core Fetch files deleted by mistake** (routes, broker, CSS, templates, tests). Recovery used **`git restore`** from **`HEAD`**. **`python3 -m pytest`** should stay green before push.

If you see that pattern again, **restore before committing**; those files are not optional test-only artifacts.

## Still open (next session)

1. **Markdown pipe tables:** answers still need safe **tabular** rendering if you want pipe tables (`tables` extension, sanitizer allow-list, `app.css` — see **`PLAN.md`**).
2. **`/docs` answers:** keep pushing **summaries + clean source attribution** (`docs/planning/FETCH_TRUST_PLAN.md`).
3. **Security:** schedule **OpenClaw gateway token rotation** after any prior exposure (no secrets in docs/logs).
4. **RetrieverOps separate broker lane:** still **parked** (`PARKED.md` OQ-10).
5. **Admin matrix deploy:** apply migration `0001_retriever_core_auth.sql`, deploy, then verify `weborders@boonegraphics.net` can be saved/approved from production `/admin/users`.

## Copy-ready next kickoff

```text
kickoff projects/retriever-rebuild

Goal: Pick up from PLAN.md next session goal (tables or trust/docs work). Open docs/README.md if you need orientation.

Notes: Verify clean tree and pytest before push. Broker parity and gateway-only defaults live in booneops-bots; Retriever is the web UI + broker client. No secrets in chat or commits.
```
