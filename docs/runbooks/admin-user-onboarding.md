# Admin — onboard a new Retriever user (Cloudflare → Fetch)

Use this when someone signs in through Cloudflare Access for the first time and needs Retriever modules.

## Order: lifecycle first, then entitlements

1. **Lifecycle:** The person must become **`active`** (Approve on `/admin/users`) before Retriever treats them as a full user (session cookie, home shell, module gates).
2. **Profile:** Enter their **Full Name** and choose their **Location** before approval.
3. **Entitlements:** Use **Save** on their line to set Admin, Fetch, PrePress, DSF, Inventory, Proofs, and BooneOps. You can adjust entitlements while they are still **pending** to pre-configure, then Approve.

## Operator checklist

1. Ask them to open `https://retriever.boonegraphics.net/` and complete **Cloudflare Access**.
2. They should see **“access pending”** on Home with their email — that confirms identity reached Retriever.
3. As an **admin**, open **`/admin/users`**. Find their row (status **pending**).
4. Fill in **Full Name**, choose **Location**, set module access, then click **Save**.
5. Click **Approve** (activates the account). Approval requires a full name.
6. They **refresh** or open Home again — they should get the normal shell (and Fetch in the sidebar when module + access + `FETCH_ENABLED` allow).
7. Smoke: they open **`/fetch`**, start a conversation, send a short question.
8. To remove someone, click **Remove**. This deletes their Retriever profile/access rows and revokes sessions; if they pass Cloudflare again later, they return as a fresh pending user.

## Notes

- **Health / Version** links in the sidebar are **admin-only** in the new shell so pending users are not nudged toward ops URLs.
- **General “outside world” LLM** is controlled **app-wide** by **`FETCH_GENERAL_QUESTIONS_ENABLED`** (see **`docs/planning/FETCH_TRUST_PLAN.md`**), not per user in the matrix.
- **Admin / Fetch / PrePress / DSF** are yes/no module gates.
- **Inventory / Proofs** use placeholder levels for future module work: **No**, **Viewer**, **Manager**.
- **Location** comes from MIS PostgreSQL when `MIS_DB_*` is configured:
  `SELECT id, name FROM public.productionlocations WHERE COALESCE(isdeleted, false) = false AND COALESCE(ishidden, false) = false ORDER BY name`.
- Old Retriever auth lived in MySQL schema **`retriever_core.users`** with username/password hashes, role enum, active flag, location fields, and permanent delete. New Retriever intentionally uses Cloudflare identity first and stores app authorization in **`retriever_core.users`** plus module/capability tables.
