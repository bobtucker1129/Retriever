"""
PrePress-Specific Database Queries

Retriever PrePress is a WIP tracker that:
- Reads business data from PostgreSQL MIS (source of truth)
- Reads operator list + location mapping from switch_shared (MySQL, read-only)
- Stores ONLY workflow/UI state in MySQL schema retriever_prepress
  (hold, needs_data, working/completed timestamps, proof rounds, notes, ownership)
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, date, timedelta
import logging
from typing import Any, Dict, Iterable, List, Optional, Tuple

from app.database.mis_client import get_mis_client
from app.database.mysql_client import get_mysql_client, _get_table_columns
from app.security import SecureErrorHandler

logger = logging.getLogger(__name__)

PREPRESS_DB_NAME = "retriever_prepress"
PREPRESS_REVENUE_CHARGE_DEF_IDS: Tuple[int, ...] = (
    7198,
    7199,
    7200,
    14985769,
    14985771,
    16246221,
    16246223,
    19708677,
    20695934,
    23184055,
    24152566,
    25978100,
)
PREPRESS_GRAPHIC_DESIGN_SPECIAL_DEF_ID = 7278


@dataclass(frozen=True)
class PrepressOperator:
    id: int
    name: str
    email: Optional[str]
    location_id: Optional[int]


def _parse_mysql_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return None


def _money_to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _format_currency(value: Any) -> str:
    amount = _money_to_float(value)
    if amount is None:
        return ""
    return f"${amount:,.2f}"


def _mysql_fetch_all(
    query: str,
    params: Optional[Tuple[Any, ...]],
    database: str,
) -> List[Dict[str, Any]]:
    client = get_mysql_client()
    conn = None
    cursor = None
    try:
        conn = client.get_connection(database)
        cursor = conn.cursor(dictionary=True)
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        return cursor.fetchall() or []
    except Exception as e:
        SecureErrorHandler.handle_database_error(e, f"prepress mysql query ({database})")
        return []
    finally:
        try:
            if cursor is not None:
                cursor.close()
        except Exception:
            pass
        try:
            if conn is not None:
                conn.close()
        except Exception:
            pass


def _mysql_execute(query: str, params: Tuple[Any, ...], database: str) -> bool:
    client = get_mysql_client()
    conn = None
    cursor = None
    try:
        conn = client.get_connection(database)
        cursor = conn.cursor()
        cursor.execute(query, params)
        return True
    except Exception as e:
        SecureErrorHandler.handle_database_error(e, f"prepress mysql execute ({database})")
        return False
    finally:
        try:
            if cursor is not None:
                cursor.close()
        except Exception:
            pass


def _mysql_execute_many(query: str, params_list: List[Tuple[Any, ...]], database: str) -> bool:
    """Execute a single prepared statement with many parameter tuples."""
    if not params_list:
        return True
    client = get_mysql_client()
    conn = None
    cursor = None
    try:
        conn = client.get_connection(database)
        cursor = conn.cursor()
        cursor.executemany(query, params_list)
        return True
    except Exception as e:
        SecureErrorHandler.handle_database_error(e, f"prepress mysql executemany ({database})")
        return False
    finally:
        try:
            if cursor is not None:
                cursor.close()
        except Exception:
            pass


def _mysql_try_get_lock(lock_name: str, database: str) -> bool:
    """Try to acquire a MySQL named lock immediately (timeout=0)."""
    rows = _mysql_fetch_all("SELECT GET_LOCK(%s, 0) AS got_lock", (lock_name,), database)
    try:
        return bool(rows and int(rows[0].get("got_lock") or 0) == 1)
    except Exception:
        return False


def _mysql_release_lock(lock_name: str, database: str) -> None:
    """Release a MySQL named lock (best effort)."""
    _mysql_fetch_all("SELECT RELEASE_LOCK(%s) AS released", (lock_name,), database)


def _placeholders(count: int) -> str:
    if count <= 0:
        raise ValueError("placeholders count must be > 0")
    return ",".join(["%s"] * count)


def get_prepress_operators() -> List[PrepressOperator]:
    """Load active prepress operators from switch_shared.prepress."""
    client = get_mysql_client()
    raw = client.get_prepress_operators()
    operators: List[PrepressOperator] = []
    for row in raw:
        try:
            operators.append(
                PrepressOperator(
                    id=int(row["id"]),
                    name=str(row.get("name") or ""),
                    email=row.get("email"),
                    location_id=int(row["location_id"]) if row.get("location_id") is not None else None,
                )
            )
        except Exception:
            continue
    return operators


def _name_key(value: str) -> str:
    """Normalize a person-name-like string for stable alias matching."""
    return " ".join(str(value or "").strip().lower().split())


EXPLICIT_PREPRESS_ACTOR_ALIASES: Dict[str, str] = {
    "johnny": "John Patchin",
    "jpatchin": "John Patchin",
    "admin": "Scott Tate",
    "state": "Scott Tate",
    "jnelson": "Jeff Nelson",
}


def _build_prepress_actor_alias_map(
    operators: List[PrepressOperator],
) -> Tuple[Dict[str, str], List[str]]:
    """
    Build a best-effort alias map to canonical switch_shared.prepress names.

    We prefer the authoritative PrePress operator names from switch_shared, but
    also fold in auth usernames/full names from retriever_core.users so legacy
    workflow rows like "state" can resolve to "Scott Tate".
    """
    canonical_name_by_key: Dict[str, str] = {}
    operator_names: List[str] = []
    for op in operators:
        name = str(op.name or "").strip()
        if not name:
            continue
        key = _name_key(name)
        canonical_name_by_key[key] = name
        operator_names.append(name)

    alias_by_key = dict(canonical_name_by_key)
    for alias_key, canonical_name in EXPLICIT_PREPRESS_ACTOR_ALIASES.items():
        canonical_key = _name_key(canonical_name)
        if canonical_key in canonical_name_by_key:
            alias_by_key[alias_key] = canonical_name_by_key[canonical_key]

    try:
        from app.database.queries.users import list_users

        for user in list_users():
            full_name = str(user.get("full_name") or "").strip()
            first_name = str(user.get("first_name") or "").strip()
            last_name = str(user.get("last_name") or "").strip()
            combined_name = " ".join(part for part in [first_name, last_name] if part).strip()

            canonical_name = ""
            for candidate in [full_name, combined_name]:
                candidate_key = _name_key(candidate)
                if candidate_key and candidate_key in canonical_name_by_key:
                    canonical_name = canonical_name_by_key[candidate_key]
                    break

            if not canonical_name:
                continue

            for alias in [user.get("username"), full_name, combined_name]:
                alias_key = _name_key(str(alias or ""))
                if alias_key:
                    alias_by_key.setdefault(alias_key, canonical_name)
    except Exception as e:
        logger.warning("Unable to load auth-user aliases for prepress normalization: %s", e)

    return alias_by_key, operator_names


def normalize_prepress_actor_name(
    raw: str,
    *,
    operators: Optional[List[PrepressOperator]] = None,
    alias_by_key: Optional[Dict[str, str]] = None,
    operator_names: Optional[List[str]] = None,
) -> str:
    """
    Normalize a stored actor label to the canonical switch_shared.prepress.name.

    Matching order:
    - exact auth/operator alias map match
    - unique first-token operator match
    - unique substring operator match
    - otherwise keep the original value
    """
    value = " ".join(str(raw or "").strip().split())
    if not value:
        return ""

    if operators is None:
        operators = get_prepress_operators()
    if alias_by_key is None or operator_names is None:
        alias_by_key, operator_names = _build_prepress_actor_alias_map(operators)

    value_key = _name_key(value)
    if value_key in alias_by_key:
        return alias_by_key[value_key]

    token_matches: List[str] = []
    for name in operator_names:
        parts = [part for part in name.split(" ") if part]
        if parts and _name_key(parts[0]) == value_key:
            token_matches.append(name)
    if len(token_matches) == 1:
        return token_matches[0]

    substr_matches = [name for name in operator_names if value_key in _name_key(name)]
    if len(substr_matches) == 1:
        return substr_matches[0]

    return value


def _select_invoice_display_amount(header: Dict[str, Any]) -> Optional[float]:
    for key in ("GrandTotal", "AmountDue", "Subtotal"):
        amount = _money_to_float(header.get(key))
        if amount is not None:
            return amount
    return None


def _get_prepress_revenue_by_invoice(invoice_numbers: List[str]) -> Dict[str, float]:
    """
    Sum approved PrePress/PreMedia revenue by invoice from MIS charge rows.

    Includes:
    - approved charge definition IDs
    - special-case 7278 rows only when the live charge description is Graphic Design-style
    - both invoice-level and job-level charges

    Excludes:
    - deleted charges
    - zero-dollar charges
    """
    invoice_values = [str(n or "").strip() for n in invoice_numbers if str(n or "").strip()]
    if not invoice_values:
        return {}

    mis_client = get_mis_client()
    try:
        conn = mis_client.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            WITH revenue_rows AS (
              SELECT
                ib.invoicenumber::text AS invoice_number,
                c.chargedefinition_id,
                c.description,
                COALESCE(c.price, 0) AS price
              FROM public.charge c
              INNER JOIN public.invoicebase ib
                ON c.parentinvoice_id = ib.id
              WHERE ib.invoicenumber::text = ANY(%s::text[])
                AND COALESCE(c.isdeleted, FALSE) = FALSE
                AND COALESCE(c.price, 0) > 0

              UNION ALL

              SELECT
                ib.invoicenumber::text AS invoice_number,
                c.chargedefinition_id,
                c.description,
                COALESCE(c.price, 0) AS price
              FROM public.charge c
              INNER JOIN public.jobbase jb
                ON c.parentjob_id = jb.id
              INNER JOIN public.invoicebase ib
                ON jb.parentinvoice_id = ib.id
              WHERE ib.invoicenumber::text = ANY(%s::text[])
                AND COALESCE(c.isdeleted, FALSE) = FALSE
                AND COALESCE(c.price, 0) > 0
                AND COALESCE(jb.isdeleted, FALSE) = FALSE
                AND COALESCE(jb.hidden, FALSE) = FALSE
            )
            SELECT
              invoice_number,
              SUM(price) AS revenue
            FROM revenue_rows
            WHERE chargedefinition_id = ANY(%s::bigint[])
               OR (
                 chargedefinition_id = %s
                 AND COALESCE(description, '') ILIKE '%%graphic design%%'
               )
            GROUP BY invoice_number
            """,
            (
                invoice_values,
                invoice_values,
                list(PREPRESS_REVENUE_CHARGE_DEF_IDS),
                PREPRESS_GRAPHIC_DESIGN_SPECIAL_DEF_ID,
            ),
        )
        rows = cursor.fetchall() or []
        cursor.close()
        conn.close()
        out: Dict[str, float] = {}
        for invoice_number, revenue in rows:
            inv = str(invoice_number or "").strip()
            if not inv:
                continue
            amount = _money_to_float(revenue) or 0.0
            out[inv] = amount
        return out
    except Exception as e:
        SecureErrorHandler.handle_database_error(e, "getting prepress revenue by invoice from MIS")
        return {}


def get_operator_location_map(operators: List[PrepressOperator]) -> Dict[int, int]:
    """Map prepress_id -> MIS location_id (only where location_id exists)."""
    mapping: Dict[int, int] = {}
    for op in operators:
        if op.location_id is not None:
            mapping[op.id] = op.location_id
    return mapping


def _get_mis_invoice_headers_for_prepress_locations(location_ids: List[int]) -> List[Dict[str, Any]]:
    """
    Pull invoice-level data from MIS for invoices that have at least one job part
    located in one of the provided prepress location_ids.

    This is intentionally lighter than pulling all job-part rows. It returns:
    - Invoice header fields needed for the WIP list
    - Distinct prepress location IDs present on that invoice (for queue/shared detection)

    NOTE: Does not return job-part rows. Job-part details are fetched on-demand per invoice.
    """
    if not location_ids:
        return []

    # NOTE: PrintSmith MIS is PostgreSQL 9.3.x. Avoid aggregate FILTER syntax (9.4+).
    sql = """
    SELECT
      ib.id AS "InvoiceID",
      ib.invoicenumber AS "InvoiceNumber",
      a.title AS "AccountName",
      ib.takenby AS "TakenBy",
      ib.proofdate AS "ProofDate",
      ib.wanteddate AS "WantedDate",

      ARRAY_AGG(
        DISTINCT CASE
          WHEN jb.location_id = ANY(%s::int[]) THEN jb.location_id
          ELSE NULL
        END
      ) AS "PrepressLocationIDs"

    -- Invoice-only: anchor on public.invoice (estimates live in public.estimate)
    FROM public.invoice inv
    INNER JOIN public.invoicebase ib
      ON inv.id = ib.id
    INNER JOIN public.account a
      ON ib.account_id = a.id

    -- PrintSmith rule: jobbase links to invoicebase via parentinvoice_id
    LEFT JOIN public.jobbase jb
      ON ib.id = jb.parentinvoice_id

    WHERE ib.onpendinglist = TRUE
      AND ib.voided = FALSE
      AND jb.id IS NOT NULL
      AND COALESCE(jb.isdeleted, FALSE) = FALSE
      AND COALESCE(jb.hidden, FALSE) = FALSE

    GROUP BY
      ib.id, ib.invoicenumber, a.title, ib.takenby, ib.proofdate, ib.wanteddate

    HAVING SUM(CASE WHEN jb.location_id = ANY(%s::int[]) THEN 1 ELSE 0 END) > 0

    ORDER BY ib.invoicenumber::text;
    """

    client = get_mis_client()
    try:
        conn = client.get_connection()
        cursor = conn.cursor()
        cursor.execute(sql, (location_ids, location_ids))
        rows = cursor.fetchall() or []
        columns = [desc[0] for desc in cursor.description]
        cursor.close()
        conn.close()
        out = [dict(zip(columns, row)) for row in rows]
        if not out:
            logger.info("PrePress MIS invoice header query returned 0 rows for %d location_ids", len(location_ids))
        return out
    except Exception as e:
        SecureErrorHandler.handle_database_error(e, "getting prepress invoice headers from MIS")
        return []


def _get_mis_invoice_entry_candidates_for_prepress_locations(location_ids: List[int]) -> List[Dict[str, Any]]:
    """
    MIS -> candidate invoices for entering sticky PrePress WIP.

    Rules:
    - Invoice-only (join public.invoice)
    - Only active workflow items at the time of entry: invoicebase.onpendinglist = TRUE and voided = FALSE
    - Candidate if ANY job part (including child parts) is in one of the provided prepress location_ids
    - PostgreSQL 9.3 compatible (no FILTER aggregates)

    Returns:
    - InvoiceNumber
    - MatchingLocationIDs: list of location_ids (subset of location_ids) present on the invoice's job parts
    """
    if not location_ids:
        return []

    sql = """
    SELECT
      ib.invoicenumber AS "InvoiceNumber",
      ARRAY_AGG(
        DISTINCT CASE
          WHEN jb.location_id = ANY(%s::int[]) THEN jb.location_id
          ELSE NULL
        END
      ) AS "MatchingLocationIDs"

    FROM public.invoice inv
    INNER JOIN public.invoicebase ib
      ON inv.id = ib.id

    -- Parent/child job linking (supports 123456/1.1)
    LEFT JOIN public.jobbase parentjob
      ON ib.id = parentjob.parentinvoice_id
     AND parentjob.parentjob_id IS NULL

    LEFT JOIN public.jobbase jb
      ON (jb.parentjob_id = parentjob.id OR jb.id = parentjob.id)

    WHERE ib.onpendinglist = TRUE
      AND ib.voided = FALSE
      AND jb.id IS NOT NULL
      AND COALESCE(jb.isdeleted, FALSE) = FALSE
      AND COALESCE(jb.hidden, FALSE) = FALSE

    GROUP BY ib.invoicenumber

    HAVING SUM(CASE WHEN jb.location_id = ANY(%s::int[]) THEN 1 ELSE 0 END) > 0

    ORDER BY ib.invoicenumber::text;
    """

    client = get_mis_client()
    try:
        conn = client.get_connection()
        cursor = conn.cursor()
        cursor.execute(sql, (location_ids, location_ids))
        rows = cursor.fetchall() or []
        columns = [desc[0] for desc in cursor.description]
        cursor.close()
        conn.close()
        out = [dict(zip(columns, row)) for row in rows]
        # Clean None values inside arrays
        for r in out:
            r["MatchingLocationIDs"] = [x for x in (r.get("MatchingLocationIDs") or []) if x is not None]
        return out
    except Exception as e:
        SecureErrorHandler.handle_database_error(e, "getting prepress entry candidates from MIS")
        return []


def _get_mis_current_prepress_locations_for_invoices(
    invoice_numbers: List[str], location_ids: List[int]
) -> Dict[str, List[int]]:
    """
    For already-enrolled (sticky) invoices, find which PrePress location_ids are currently present on MIS job parts.

    Notes:
    - Invoice-only (join public.invoice)
    - PG 9.3 compatible (no FILTER aggregates)
    - Does NOT enforce onpendinglist; we want reassignment even after it leaves the prepress location,
      and membership is controlled by MySQL completed_at only.

    Returns mapping: invoice_number -> [location_id, ...] (only from the provided location_ids set)
    Missing invoices map to empty list.
    """
    if not invoice_numbers or not location_ids:
        return {str(n): [] for n in (invoice_numbers or []) if n}

    invoice_numbers = [str(x) for x in invoice_numbers if x]

    # Use the same parent/child job linking as the invoice expansion query.
    # Some child parts may not carry parentinvoice_id directly, so anchor on parentjob.
    sql = """
    SELECT
      ib.invoicenumber AS "InvoiceNumber",
      ARRAY_AGG(
        DISTINCT CASE
          WHEN jb.location_id = ANY(%s::int[]) THEN jb.location_id
          ELSE NULL
        END
      ) AS "MatchingLocationIDs"

    FROM public.invoice inv
    INNER JOIN public.invoicebase ib
      ON inv.id = ib.id

    LEFT JOIN public.jobbase parentjob
      ON ib.id = parentjob.parentinvoice_id
     AND parentjob.parentjob_id IS NULL

    LEFT JOIN public.jobbase jb
      ON (jb.parentjob_id = parentjob.id OR jb.id = parentjob.id)

    WHERE ib.voided = FALSE
      AND ib.invoicenumber = ANY(%s)
      AND jb.id IS NOT NULL
      AND COALESCE(jb.isdeleted, FALSE) = FALSE
      AND COALESCE(jb.hidden, FALSE) = FALSE

    GROUP BY ib.invoicenumber
    ORDER BY ib.invoicenumber::text;
    """

    out: Dict[str, List[int]] = {str(n): [] for n in invoice_numbers}
    client = get_mis_client()
    try:
        conn = client.get_connection()
        cursor = conn.cursor()
        cursor.execute(sql, (location_ids, invoice_numbers))
        rows = cursor.fetchall() or []
        columns = [desc[0] for desc in cursor.description]
        cursor.close()
        conn.close()

        idx_inv = columns.index("InvoiceNumber")
        idx_locs = columns.index("MatchingLocationIDs")
        for row in rows:
            inv_num = str(row[idx_inv] or "")
            locs = [x for x in (row[idx_locs] or []) if x is not None]
            norm: List[int] = []
            for loc in locs:
                try:
                    norm.append(int(loc))
                except Exception:
                    continue
            out[inv_num] = norm

        return out
    except Exception as e:
        SecureErrorHandler.handle_database_error(e, "getting prepress current locations for invoices from MIS")
        return out


def refresh_sticky_wip_membership_from_mis() -> int:
    """
    Detect invoices currently in PrePress MIS locations and enroll them into sticky WIP membership.

    Returns number of candidate invoices detected (enrollment is idempotent).
    """
    operators = get_prepress_operators()
    operator_locations = get_operator_location_map(operators)
    location_ids = sorted(set(operator_locations.values()))
    if not location_ids:
        return 0

    entry_candidates = _get_mis_invoice_entry_candidates_for_prepress_locations(location_ids)

    # Reverse mapping for entry assignment
    location_to_prepress: Dict[int, List[int]] = defaultdict(list)
    for prepress_id, loc_id in operator_locations.items():
        try:
            location_to_prepress[int(loc_id)].append(int(prepress_id))
        except Exception:
            continue

    entry_rows: List[Tuple[str, Optional[int], int]] = []
    for r in entry_candidates:
        inv_num = str(r.get("InvoiceNumber") or "").strip()
        if not inv_num:
            continue
        locs = [x for x in (r.get("MatchingLocationIDs") or []) if x is not None]
        op_ids: set[int] = set()
        for loc in locs:
            try:
                loc_int = int(loc)
            except Exception:
                continue
            for pid in location_to_prepress.get(loc_int, []):
                op_ids.add(int(pid))

        entered_is_shared = 1 if len(op_ids) > 1 else 0
        entered_prepress_id: Optional[int] = None
        if len(op_ids) == 1:
            entered_prepress_id = list(op_ids)[0]
        entry_rows.append((inv_num, entered_prepress_id, entered_is_shared))

    _upsert_prepress_entry_fields(entry_rows)
    return len(entry_candidates)


def reconcile_sticky_wip_assignments_from_mis() -> int:
    """
    Reconcile sticky assignment (entered_prepress_id / entered_is_shared) from current MIS locations.

    Rules:
    - If invoice has job parts in exactly 1 prepress location -> assign to that operator
    - If in >1 prepress locations -> Shared Queue (entered_is_shared=1, entered_prepress_id=NULL)
    - If in 0 prepress locations -> no change (stays last assigned)

    Returns number of invoices whose assignment was updated.
    """
    operators = get_prepress_operators()
    operator_locations = get_operator_location_map(operators)
    location_ids = sorted(set(operator_locations.values()))

    current = _load_all_open_sticky_invoice_assignments()
    if not current or not location_ids:
        return 0

    invoice_numbers = [str(r.get("invoice_number") or "") for r in current if r.get("invoice_number")]
    if not invoice_numbers:
        return 0

    # Reverse mapping location_id -> prepress_id(s)
    location_to_prepress: Dict[int, List[int]] = defaultdict(list)
    for prepress_id, loc_id in operator_locations.items():
        try:
            location_to_prepress[int(loc_id)].append(int(prepress_id))
        except Exception:
            continue

    locs_by_invoice = _get_mis_current_prepress_locations_for_invoices(invoice_numbers, location_ids)

    updates: List[Tuple[Optional[int], int, str]] = []
    updated_count = 0

    for row in current:
        inv = str(row.get("invoice_number") or "")
        if not inv:
            continue

        locs = locs_by_invoice.get(inv, [])
        op_ids: set[int] = set()
        for loc in locs:
            for pid in location_to_prepress.get(int(loc), []):
                op_ids.add(int(pid))

        # No prepress locations currently -> do not change assignment
        if len(op_ids) == 0:
            continue

        desired_is_shared = 1 if len(op_ids) > 1 else 0
        desired_prepress_id: Optional[int] = None
        if len(op_ids) == 1:
            desired_prepress_id = list(op_ids)[0]

        current_is_shared = 1 if bool(row.get("entered_is_shared") or 0) else 0
        current_prepress_id = row.get("entered_prepress_id")
        try:
            current_prepress_id_int = int(current_prepress_id) if current_prepress_id is not None else None
        except Exception:
            current_prepress_id_int = None

        if desired_is_shared != current_is_shared or desired_prepress_id != current_prepress_id_int:
            updates.append((desired_prepress_id, desired_is_shared, inv))
            updated_count += 1

    _apply_sticky_assignment_updates(updates)
    return updated_count


def refresh_and_reconcile_sticky_wip_from_mis() -> Tuple[int, int]:
    """Run enrollment + reassignment reconciliation. Returns (enrolled_candidates, reassigned_count)."""
    enrolled = refresh_sticky_wip_membership_from_mis()
    reassigned = reconcile_sticky_wip_assignments_from_mis()
    return enrolled, reassigned


def _get_mis_job_parts_for_invoice(invoice_number: str) -> List[Dict[str, Any]]:
    """
    Pull job-part rows for a single invoice from MIS.

    This is used by the invoice expansion UI. It intentionally avoids scanning
    all invoices/locations.
    """
    if not invoice_number:
        return []

    sql = """
    WITH jobs AS (
      SELECT
        ib.id AS "InvoiceID",
        ib.invoicenumber AS "InvoiceNumber",
        a.title AS "AccountName",
        ib.takenby AS "TakenBy",
        ib.proofdate AS "ProofDate",
        ib.wanteddate AS "WantedDate",

        jb.id AS "JobID",
        CASE
          WHEN jb.parentjob_id IS NULL THEN jb.jobindex
          ELSE parentjob.jobindex
        END AS "ApiJobIndex",
        jb.location_id AS "LocationID",
        pl.name AS "JobLocation",
        jb.description AS "PartDescription",

        CASE
          WHEN jb.parentjob_id IS NULL THEN jb.jobindex::text
          ELSE parentjob.jobindex::text || '.' || jb.jobindex::text
        END AS "JobPartNumber"

      -- Invoice-only: anchor on public.invoice (estimates live in public.estimate)
      FROM public.invoice inv
      INNER JOIN public.invoicebase ib
        ON inv.id = ib.id
      JOIN public.account a ON ib.account_id = a.id

      -- Parent/child job linking (supports 123456/1.1)
      LEFT JOIN public.jobbase parentjob
        ON ib.id = parentjob.parentinvoice_id
       AND parentjob.parentjob_id IS NULL

      LEFT JOIN public.jobbase jb
        ON (jb.parentjob_id = parentjob.id OR jb.id = parentjob.id)

      LEFT JOIN public.productionlocations pl ON jb.location_id = pl.id

      WHERE ib.voided = FALSE
        AND ib.invoicenumber = %s
        AND jb.id IS NOT NULL
        AND COALESCE(jb.isdeleted, FALSE) = FALSE
        AND COALESCE(jb.hidden, FALSE) = FALSE
    )
    SELECT *
    FROM jobs
    ORDER BY "JobPartNumber"::text;
    """

    client = get_mis_client()
    try:
        conn = client.get_connection()
        cursor = conn.cursor()
        cursor.execute(sql, (invoice_number,))
        rows = cursor.fetchall() or []
        columns = [desc[0] for desc in cursor.description]
        cursor.close()
        conn.close()
        return [dict(zip(columns, row)) for row in rows]
    except Exception as e:
        SecureErrorHandler.handle_database_error(e, "getting prepress invoice parts from MIS")
        return []


def _load_invoice_state(invoice_numbers: List[str]) -> Dict[str, Dict[str, Any]]:
    if not invoice_numbers:
        return {}
    ph = _placeholders(len(invoice_numbers))
    query = f"""
    SELECT
      invoice_number,
      owner_prepress_id,
      owner_set_at,
      owner_set_by,
      is_hold,
      needs_data,
      working_started_at,
      completed_at,
      notes,
      updated_at
    FROM invoice_state
    WHERE invoice_number IN ({ph})
    """
    rows = _mysql_fetch_all(query, tuple(invoice_numbers), PREPRESS_DB_NAME)
    return {str(r["invoice_number"]): r for r in rows}


def _upsert_prepress_entry_fields(entries: List[Tuple[str, Optional[int], int]]) -> None:
    """
    Record sticky WIP membership the first time an invoice is detected in a PrePress MIS location.

    Only sets entry fields once:
    - entered_at
    - entered_prepress_id
    - entered_is_shared
    """
    if not entries:
        return

    # Best effort: if DB isn't migrated yet, skip silently (ensure script should add columns).
    cols = {c.lower() for c in (_get_table_columns(PREPRESS_DB_NAME, "invoice_state") or [])}
    required = {"entered_at", "entered_prepress_id", "entered_is_shared"}
    if not required.issubset(cols):
        return

    query = """
    INSERT INTO invoice_state
      (invoice_number, entered_at, entered_prepress_id, entered_is_shared)
    VALUES
      (%s, NOW(), %s, %s)
    ON DUPLICATE KEY UPDATE
      -- Only set entry fields on first entry; after that, keep sticky assignment unchanged.
      entered_prepress_id = CASE WHEN entered_at IS NULL THEN VALUES(entered_prepress_id) ELSE entered_prepress_id END,
      entered_is_shared = CASE WHEN entered_at IS NULL THEN VALUES(entered_is_shared) ELSE entered_is_shared END,
      entered_at = COALESCE(entered_at, VALUES(entered_at))
    """
    params_list: List[Tuple[Any, ...]] = []
    for invoice_number, entered_prepress_id, entered_is_shared in entries:
        params_list.append((invoice_number, entered_prepress_id, int(entered_is_shared)))

    _mysql_execute_many(query, params_list, PREPRESS_DB_NAME)


def _load_sticky_open_invoice_state(
    *,
    view_mode: str,
    selected_prepress_id: Optional[int],
) -> List[Dict[str, Any]]:
    """
    Load open (not completed) sticky WIP invoices from MySQL only.

    Membership rules:
    - entered_at IS NOT NULL (seen at least once in prepress location)
    - completed_at IS NULL (only removed by Completed)
    - view_mode filters based on entered_prepress_id / entered_is_shared (sticky assignment)
    """
    cols = {c.lower() for c in (_get_table_columns(PREPRESS_DB_NAME, "invoice_state") or [])}
    has_sticky = {"entered_at", "entered_prepress_id", "entered_is_shared"}.issubset(cols)
    if not has_sticky:
        return []

    where: List[str] = ["entered_at IS NOT NULL", "completed_at IS NULL"]
    params: List[Any] = []

    if view_mode == "shared":
        where.append("entered_is_shared = 1")
    elif view_mode == "my":
        if selected_prepress_id is None:
            return []
        where.append("entered_is_shared = 0")
        where.append("entered_prepress_id = %s")
        params.append(int(selected_prepress_id))

    query = f"""
    SELECT
      invoice_number,
      entered_at,
      entered_prepress_id,
      entered_is_shared,
      is_hold,
      needs_data,
      working_started_at,
      completed_at,
      notes,
      updated_at
    FROM invoice_state
    WHERE {' AND '.join(where)}
    ORDER BY entered_at DESC, invoice_number
    """

    rows = _mysql_fetch_all(query, tuple(params) if params else None, PREPRESS_DB_NAME)

    return rows


def _load_all_open_sticky_invoice_assignments() -> List[Dict[str, Any]]:
    """Load open sticky invoices with their current assignment fields (MySQL only)."""
    cols = {c.lower() for c in (_get_table_columns(PREPRESS_DB_NAME, "invoice_state") or [])}
    has_sticky = {"entered_at", "entered_prepress_id", "entered_is_shared"}.issubset(cols)
    if not has_sticky:
        return []

    query = """
    SELECT
      invoice_number,
      entered_at,
      entered_prepress_id,
      entered_is_shared
    FROM invoice_state
    WHERE entered_at IS NOT NULL
      AND completed_at IS NULL
    """
    return _mysql_fetch_all(query, None, PREPRESS_DB_NAME)


def _apply_sticky_assignment_updates(
    updates: List[Tuple[Optional[int], int, str]],
) -> None:
    """
    Apply (entered_prepress_id, entered_is_shared, invoice_number) updates in bulk.
    Only updates assignment fields; does not touch entered_at.
    """
    if not updates:
        return

    cols = {c.lower() for c in (_get_table_columns(PREPRESS_DB_NAME, "invoice_state") or [])}
    if not {"entered_prepress_id", "entered_is_shared"}.issubset(cols):
        return

    query = """
    UPDATE invoice_state
    SET entered_prepress_id = %s,
        entered_is_shared = %s
    WHERE invoice_number = %s
      AND entered_at IS NOT NULL
      AND completed_at IS NULL
    """
    _mysql_execute_many(query, updates, PREPRESS_DB_NAME)


def _load_jobpart_state(invoice_numbers: List[str]) -> Dict[Tuple[str, str], Dict[str, Any]]:
    if not invoice_numbers:
        return {}
    ph = _placeholders(len(invoice_numbers))
    query = f"""
    SELECT invoice_number, job_part_number, notes, updated_at
    FROM jobpart_state
    WHERE invoice_number IN ({ph})
    """
    rows = _mysql_fetch_all(query, tuple(invoice_numbers), PREPRESS_DB_NAME)
    out: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for r in rows:
        out[(str(r["invoice_number"]), str(r["job_part_number"]))] = r
    return out


def _load_latest_proof_round(invoice_numbers: List[str]) -> Dict[Tuple[str, str], Dict[str, Any]]:
    """
    Return latest proof info per (invoice_number, job_part_number):
    - round_number (max)
    - sent_at for that round
    """
    if not invoice_numbers:
        return {}
    ph = _placeholders(len(invoice_numbers))
    query = f"""
    SELECT pe.invoice_number, pe.job_part_number, pe.round_number, pe.sent_at, pe.sent_by
    FROM proof_event pe
    INNER JOIN (
      SELECT invoice_number, job_part_number, MAX(round_number) AS max_round
      FROM proof_event
      WHERE invoice_number IN ({ph})
      GROUP BY invoice_number, job_part_number
    ) latest
      ON pe.invoice_number = latest.invoice_number
     AND pe.job_part_number = latest.job_part_number
     AND pe.round_number = latest.max_round
    """
    rows = _mysql_fetch_all(query, tuple(invoice_numbers), PREPRESS_DB_NAME)
    out: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for r in rows:
        out[(str(r["invoice_number"]), str(r["job_part_number"]))] = r
    return out


def _compute_matched_operator_ids(
    jobs: List[Dict[str, Any]],
    operator_locations: Dict[int, int],
) -> Dict[str, List[int]]:
    """
    For each invoice_number, return a de-duplicated list of prepress_ids
    that have at least one part in their MIS location.
    """
    location_to_prepress: Dict[int, List[int]] = defaultdict(list)
    for prepress_id, location_id in operator_locations.items():
        location_to_prepress[location_id].append(prepress_id)

    invoice_to_ops: Dict[str, set[int]] = defaultdict(set)
    for row in jobs:
        invoice_number = str(row.get("InvoiceNumber") or "")
        loc_id = row.get("LocationID")
        if not invoice_number or loc_id is None:
            continue
        try:
            loc_id_int = int(loc_id)
        except Exception:
            continue
        for pid in location_to_prepress.get(loc_id_int, []):
            invoice_to_ops[invoice_number].add(pid)

    return {inv: sorted(list(pids)) for inv, pids in invoice_to_ops.items()}


def get_prepress_wip(
    selected_prepress_id: Optional[int],
    view_mode: str,
    include_completed: bool,
) -> Dict[str, Any]:
    """
    Build the PrePress WIP dataset for the UI.

    view_mode:
      - 'my': show invoices relevant to selected_prepress_id (location match OR owned)
      - 'shared': show multi-operator invoices with no owner
      - 'all': show all invoices in any prepress operator location
    """
    operators = get_prepress_operators()
    operator_locations = get_operator_location_map(operators)
    location_ids = sorted(set(operator_locations.values()))


    # 1) Entry detection + reassignment reconciliation (idempotent).
    # Enrollment adds invoices when they hit a PrePress MIS location.
    # Reconciliation updates the assigned person/shared queue based on current MIS locations,
    # but membership remains sticky until completed_at is set.
    refresh_and_reconcile_sticky_wip_from_mis()

    # 2) Sticky membership list (MySQL-only): stay until Completed is set.
    sticky_rows = _load_sticky_open_invoice_state(view_mode=view_mode, selected_prepress_id=selected_prepress_id)
    if not sticky_rows:
        return {
            "operators": operators,
            "invoices": [],
            "analytics": {
                "invoice_count": 0,
                "shared_queue_count": 0,
                "hold_count": 0,
                "needs_data_count": 0,
                "open_invoice_count_all": 0,
                "open_shared_queue_count_all": 0,
            },
            "operator_counts": {},
            "shared_queue_count": 0,
        }

    sticky_invoice_numbers = [str(r.get("invoice_number") or "") for r in sticky_rows if r.get("invoice_number")]

    # 3) MIS enrichment for display (invoice-only, no jobbase join needed)
    headers = _mysql_fetch_all  # noqa: F841 (keep import grouping stable)
    mis_client = get_mis_client()
    try:
        conn = mis_client.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
              ib.id AS "InvoiceID",
              ib.invoicenumber AS "InvoiceNumber",
              a.title AS "AccountName",
              ib.takenby AS "TakenBy",
              ib.proofdate AS "ProofDate",
              ib.wanteddate AS "WantedDate",
              ib.grandtotal AS "GrandTotal",
              ib.amountdue AS "AmountDue",
              ib.subtotal AS "Subtotal"
            FROM public.invoice inv
            INNER JOIN public.invoicebase ib ON inv.id = ib.id
            INNER JOIN public.account a ON ib.account_id = a.id
            WHERE ib.invoicenumber = ANY(%s)
            """,
            (sticky_invoice_numbers,),
        )
        rows = cursor.fetchall() or []
        columns = [desc[0] for desc in cursor.description]
        cursor.close()
        conn.close()
        header_by_invoice: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            d = dict(zip(columns, row))
            inv_num = str(d.get("InvoiceNumber") or "")
            if inv_num:
                header_by_invoice[inv_num] = d
    except Exception as e:
        SecureErrorHandler.handle_database_error(e, "getting prepress sticky invoice headers from MIS")
        header_by_invoice = {}

    # Hard Copy Proof badge: best-effort MIS flag (must NOT break headers if it fails).
    try:
        conn = mis_client.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT DISTINCT
              ib.invoicenumber::text AS invoice_number
            FROM public.invoice inv
            INNER JOIN public.invoicebase ib ON inv.id = ib.id
            INNER JOIN public.jobbase jb ON jb.parentinvoice_id = ib.id
            INNER JOIN public.charge c ON jb.id = c.parentjob_id
            WHERE ib.invoicenumber::text = ANY(%s::text[])
              AND COALESCE(c.isdeleted, FALSE) = FALSE
              AND COALESCE(jb.isdeleted, FALSE) = FALSE
              AND COALESCE(jb.hidden, FALSE) = FALSE
              AND c.description ILIKE '%%Hard Copy Proof%%'
            """,
            (sticky_invoice_numbers,),
        )
        rows = cursor.fetchall() or []
        cursor.close()
        conn.close()
        hardcopy_by_invoice: Dict[str, bool] = {}
        for row in rows:
            inv_num = str(row[0] or "")
            if inv_num:
                hardcopy_by_invoice[inv_num] = True
    except Exception as e:
        SecureErrorHandler.handle_database_error(e, "getting prepress hard copy proof flags from MIS")
        hardcopy_by_invoice = {}

    invoices: List[Dict[str, Any]] = []
    for st in sticky_rows:
        inv_num = str(st.get("invoice_number") or "")
        h = header_by_invoice.get(inv_num, {})
        invoice_amount = _select_invoice_display_amount(h)

        entered_is_shared = bool(st.get("entered_is_shared") or 0)
        entered_prepress_id = st.get("entered_prepress_id")

        matched_operator_ids: List[int] = []
        if entered_is_shared:
            matched_operator_ids = [-1, -2]
        elif entered_prepress_id is not None:
            try:
                matched_operator_ids = [int(entered_prepress_id)]
            except Exception:
                matched_operator_ids = []

        invoices.append(
            {
                "invoice_number": inv_num,
                "account_name": h.get("AccountName") or "",
                "taken_by": h.get("TakenBy") or "",
                "proof_date": h.get("ProofDate"),
                "proof_date_urgency": _calculate_proof_date_urgency(h.get("ProofDate")),
                "wanted_date": h.get("WantedDate"),
                "invoice_id": h.get("InvoiceID"),
                "invoice_amount": invoice_amount,
                "invoice_amount_display": _format_currency(invoice_amount),
                "has_hard_copy_proof": bool(hardcopy_by_invoice.get(inv_num) or False),
                "matched_operator_ids": matched_operator_ids,
                "is_hold": bool(st.get("is_hold") or 0),
                "needs_data": bool(st.get("needs_data") or 0),
                "working_started_at": st.get("working_started_at"),
                "completed_at": st.get("completed_at"),
                "notes": st.get("notes") or "",
                "entered_at": st.get("entered_at"),
            }
        )

    # Open counts for dropdown labels (open-only)
    operator_counts: Dict[int, int] = defaultdict(int)
    shared_queue_count_total = 0
    open_invoice_count_all = 0
    open_shared_queue_count_all = 0
    for inv in invoices:
        if inv.get("completed_at"):
            continue
        ops = inv.get("matched_operator_ids") or []
        open_invoice_count_all += 1
        if len(ops) > 1:
            shared_queue_count_total += 1
            open_shared_queue_count_all += 1
            continue
        if len(ops) == 1:
            try:
                operator_counts[int(ops[0])] += 1
            except Exception:
                continue

    # Sort default (proof date, then invoice number) - final sort/paging may be applied at route layer.
    def _sort_key(d: Dict[str, Any]) -> Tuple[int, str]:
        proof_date = d.get("proof_date")
        return (0 if proof_date else 1, str(d.get("invoice_number")))

    invoices.sort(key=_sort_key)

    # Analytics (basic) - based on current view result
    shared_queue_count = sum(1 for d in invoices if len(d.get("matched_operator_ids") or []) > 1)
    hold_count = sum(1 for d in invoices if d.get("is_hold"))
    needs_data_count = sum(1 for d in invoices if d.get("needs_data"))

    return {
        "operators": operators,
        "invoices": invoices,
        "analytics": {
            "invoice_count": len(invoices),
            "shared_queue_count": shared_queue_count,
            "hold_count": hold_count,
            "needs_data_count": needs_data_count,
            "open_invoice_count_all": open_invoice_count_all,
            "open_shared_queue_count_all": open_shared_queue_count_all,
        },
        "operator_counts": dict(operator_counts),
        "shared_queue_count": shared_queue_count_total,
    }


def get_invoice_job_parts(invoice_number: str) -> List[Dict[str, Any]]:
    """Return job parts for an invoice with joined workflow state (notes + latest proof)."""
    parts = _get_mis_job_parts_for_invoice(invoice_number)
    if not parts:
        return []

    jobpart_state = _load_jobpart_state([invoice_number])
    latest_proof = _load_latest_proof_round([invoice_number])

    out: List[Dict[str, Any]] = []
    for r in parts:
        key = (invoice_number, str(r.get("JobPartNumber") or ""))
        st = jobpart_state.get(key, {})
        pf = latest_proof.get(key, {})
        out.append(
            {
                "invoice_number": invoice_number,
                "job_part_number": str(r.get("JobPartNumber") or ""),
                "job_id": r.get("JobID"),
                "job_index": r.get("ApiJobIndex"),
                "part_description": r.get("PartDescription") or "",
                "job_location": r.get("JobLocation") or "",
                "location_id": r.get("LocationID"),
                "notes": st.get("notes") or "",
                "proof_round": pf.get("round_number") or 0,
                "proof_sent_at": pf.get("sent_at"),
            }
        )
    return out


def is_invoice_eligible_for_job_ticket_save(invoice_number: str) -> bool:
    """
    True if invoice is in open sticky PrePress WIP (entered_at set, not completed).
    Aligns with save eligibility: WIP-only, not completed-reference list.
    """
    if not invoice_number:
        return False
    rows = _mysql_fetch_all(
        """
        SELECT 1 AS ok
        FROM invoice_state
        WHERE invoice_number = %s
          AND entered_at IS NOT NULL
          AND completed_at IS NULL
        LIMIT 1
        """,
        (invoice_number,),
        PREPRESS_DB_NAME,
    )
    return bool(rows)


def get_mis_invoice_internal_id(invoice_number: str) -> Optional[int]:
    """MIS invoicebase.id for PrintSmith reportParameter (invoice ticket)."""
    if not invoice_number:
        return None
    client = get_mis_client()
    try:
        conn = client.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT ib.id
            FROM public.invoice inv
            INNER JOIN public.invoicebase ib ON inv.id = ib.id
            WHERE ib.invoicenumber = %s
            LIMIT 1
            """,
            (invoice_number,),
        )
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        if row and row[0] is not None:
            return int(row[0])
    except Exception as e:
        SecureErrorHandler.handle_database_error(e, "getting MIS invoice id for PrePress job ticket")
    return None


def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        # HTML date input returns YYYY-MM-DD
        return date.fromisoformat(value)
    except Exception:
        return None


def _age_days(now: datetime, started_at: Optional[datetime]) -> Optional[int]:
    if not started_at:
        return None
    try:
        delta = now - started_at
        days = int(delta.total_seconds() // 86400)
        return max(days, 0)
    except Exception:
        return None


def _calculate_proof_date_urgency(value: Any) -> str:
    """
    Match Proofs urgency behavior for PrePress WIP list:
    - Today OR Tomorrow: red pulse
    - Day after tomorrow: amber
    - Otherwise: normal
    """
    d: Optional[date] = None
    if isinstance(value, datetime):
        d = value.date()
    elif isinstance(value, date):
        d = value
    else:
        d = None

    if not d:
        return ""

    today = date.today()
    if d == today or d == (today + timedelta(days=1)):
        return "today"
    if d == (today + timedelta(days=2)):
        return "day_after"
    return ""


def get_prepress_statistics(
    *,
    date_from: Optional[str],
    date_to: Optional[str],
    include_completed: bool,
) -> Dict[str, Any]:
    """
    Compute PrePress statistics (passive) for week-over-week comparisons.

    Notes:
    - Cohort and attribution come from MySQL workflow state.
    - Revenue enrichment comes from MIS charge rows for the filtered invoice cohort.
    - Date range filtering applies to:
        - working_started_at when include_completed is False
        - completed_at when include_completed is True
    """
    df = _parse_date(date_from)
    dt = _parse_date(date_to)

    # Pull workflow rows from MySQL only (migration-safe select).
    cols = {c.lower() for c in (_get_table_columns(PREPRESS_DB_NAME, "invoice_state") or [])}
    select_fields: List[str] = [
        "invoice_number",
        "working_started_at",
        "completed_at",
        ("working_set_by" if "working_set_by" in cols else "NULL AS working_set_by"),
        ("completed_set_by" if "completed_set_by" in cols else "NULL AS completed_set_by"),
        ("entered_prepress_id" if "entered_prepress_id" in cols else "NULL AS entered_prepress_id"),
        ("entered_is_shared" if "entered_is_shared" in cols else "0 AS entered_is_shared"),
    ]
    invoice_rows = _mysql_fetch_all(
        f"SELECT {', '.join(select_fields)} FROM invoice_state",
        None,
        PREPRESS_DB_NAME,
    )

    # Proof events for "most proof" (MySQL only)
    proof_rows = _mysql_fetch_all(
        """
        SELECT invoice_number, MAX(round_number) AS max_round
        FROM proof_event
        GROUP BY invoice_number
        """,
        None,
        PREPRESS_DB_NAME,
    )
    proof_max_by_invoice = {str(r["invoice_number"]): int(r.get("max_round") or 0) for r in proof_rows if r.get("invoice_number")}

    def _date_only(v: Any) -> Optional[date]:
        if isinstance(v, datetime):
            return v.date()
        if isinstance(v, date):
            return v
        return None

    # Filter rows (date range semantics depend on include_completed)
    filtered_rows: List[Dict[str, Any]] = []
    has_date_filter = bool(df or dt)
    for r in invoice_rows:
        started_at = r.get("working_started_at")
        completed_at = r.get("completed_at")

        if not include_completed and completed_at is not None:
            continue

        # Date filtering rules:
        # - include_completed=False: filter on working_started_at (open rows only)
        # - include_completed=True: filter on completed_at (completed rows); open rows are excluded
        #   when a date range is set (because they have no completed_at).
        filter_dt_value: Any = started_at
        if include_completed:
            filter_dt_value = completed_at
            if has_date_filter and completed_at is None:
                continue

        filter_date = _date_only(filter_dt_value)
        if has_date_filter and not filter_date:
            continue
        if df and filter_date and filter_date < df:
            continue
        if dt and filter_date and filter_date > dt:
            continue

        filtered_rows.append(r)

    now = datetime.now()

    # Rollup (ALL) counts regardless of attribution.
    all_open_count = 0
    all_completed_count = 0
    all_longest_days: Optional[int] = None
    all_most_proof_round = 0
    all_revenue = 0.0

    # Bucket by user (working_set_by primarily; fallback to completed_set_by).
    # Case-insensitive bucketing, but keep a stable display label.
    bucket_open_counts: Dict[str, int] = defaultdict(int)  # key = normalized user
    bucket_completed_counts: Dict[str, int] = defaultdict(int)
    bucket_longest_days: Dict[str, int] = defaultdict(int)
    bucket_most_proof: Dict[str, int] = defaultdict(int)
    bucket_revenue: Dict[str, float] = defaultdict(float)
    display_label_by_key: Dict[str, str] = {}

    # Canonical operator list comes exclusively from switch_shared.prepress (MySQL).
    # We normalize any stored usernames (working_set_by/completed_set_by) to these names
    # to avoid duplicates like "Scott" vs "Scott Tate" and "state" vs "Scott Tate".
    operators = get_prepress_operators()
    op_name_by_id: Dict[int, str] = {}
    alias_by_key, op_names = _build_prepress_actor_alias_map(operators)
    for op in operators:
        try:
            name = str(op.name or "").strip()
            if not name:
                continue
            op_name_by_id[int(op.id)] = name
            op_names.append(name)
        except Exception:
            continue

    def _normalize_prepress_name(raw: str) -> str:
        return normalize_prepress_actor_name(
            raw,
            operators=operators,
            alias_by_key=alias_by_key,
            operator_names=op_names,
        )

    def _who_key_or_none(r: Dict[str, Any]) -> Optional[str]:
        w = _normalize_prepress_name((r.get("working_set_by") or "").strip())
        c = _normalize_prepress_name((r.get("completed_set_by") or "").strip())
        label = w or c
        if not label:
            # Sticky assignment fallback (preferred for "who owns it" views)
            try:
                entered_is_shared = bool(r.get("entered_is_shared") or 0)
            except Exception:
                entered_is_shared = False

            if entered_is_shared:
                label = "Shared Queue"
            else:
                try:
                    pid = r.get("entered_prepress_id")
                    pid_int = int(pid) if pid is not None else None
                except Exception:
                    pid_int = None
                if pid_int is not None:
                    label = (op_name_by_id.get(pid_int) or "").strip()

        if not label:
            return None
        key = label.lower()
        display_label_by_key.setdefault(key, label)
        return key

    filtered_invoice_numbers = [
        str(r.get("invoice_number") or "").strip()
        for r in filtered_rows
        if str(r.get("invoice_number") or "").strip()
    ]
    revenue_by_invoice = _get_prepress_revenue_by_invoice(filtered_invoice_numbers)

    for r in filtered_rows:
        who = _who_key_or_none(r)
        inv = str(r.get("invoice_number") or "")
        started_at = r.get("working_started_at")
        completed_at = r.get("completed_at")
        if not inv:
            continue

        is_open = completed_at is None
        if is_open:
            all_open_count += 1
            end = now
        else:
            all_completed_count += 1
            end = completed_at if isinstance(completed_at, datetime) else now

        # Longest duration (end - start) in days, per user
        if isinstance(started_at, datetime):
            days = _age_days(end, started_at)
            if days is not None:
                all_longest_days = max(all_longest_days or 0, days)
                if who is not None:
                    bucket_longest_days[who] = max(bucket_longest_days.get(who, 0), days)

        # Most proof rounds for any invoice in this user's bucket
        all_most_proof_round = max(all_most_proof_round, proof_max_by_invoice.get(inv, 0))
        revenue = float(revenue_by_invoice.get(inv, 0.0) or 0.0)
        all_revenue += revenue
        if who is not None:
            if is_open:
                bucket_open_counts[who] += 1
            else:
                bucket_completed_counts[who] += 1
            bucket_most_proof[who] = max(bucket_most_proof.get(who, 0), proof_max_by_invoice.get(inv, 0))
            bucket_revenue[who] += revenue

    # Build per-person rows (only include people with activity).
    all_users = sorted(set(list(bucket_open_counts.keys()) + list(bucket_completed_counts.keys()) + list(bucket_most_proof.keys()) + list(bucket_longest_days.keys())))
    person_rows: List[Dict[str, Any]] = []
    for who in all_users:
        open_count = int(bucket_open_counts.get(who, 0) or 0)
        completed_count = int(bucket_completed_counts.get(who, 0) or 0)

        # Row visibility rules per request:
        # - include_completed=False: only show if open invoices exist in range
        # - include_completed=True: show if open OR completed invoices exist in range
        if not include_completed and open_count <= 0:
            continue
        if include_completed and (open_count <= 0 and completed_count <= 0):
            continue

        person_rows.append(
            {
                "name": display_label_by_key.get(who, who),
                "open_invoices": open_count,
                "completed_invoices": completed_count,
                "longest_days": bucket_longest_days.get(who, 0) if (open_count or completed_count) else None,
                "most_proof_round": int(bucket_most_proof.get(who, 0) or 0),
                "revenue": float(bucket_revenue.get(who, 0.0) or 0.0),
                "revenue_display": _format_currency(bucket_revenue.get(who, 0.0) or 0.0),
                "is_all": False,
            }
        )

    person_rows.sort(key=lambda x: (-int(x.get("open_invoices") or 0), str(x.get("name") or "")))

    # Prepend ALL row (includes unattributed historical rows too)
    rows: List[Dict[str, Any]] = [
        {
            "name": "All PrePress Persons",
            "open_invoices": int(all_open_count),
            "completed_invoices": int(all_completed_count),
            "longest_days": all_longest_days,
            "most_proof_round": int(all_most_proof_round),
            "revenue": all_revenue,
            "revenue_display": _format_currency(all_revenue),
            "is_all": True,
        }
    ] + person_rows

    summary_open_all = int(all_open_count)
    summary_completed_all = int(all_completed_count)

    return {
        "filters": {
            "date_from": df.isoformat() if df else "",
            "date_to": dt.isoformat() if dt else "",
            "include_completed": include_completed,
        },
        "summary": {
            "open_all": summary_open_all,
            "completed_all": summary_completed_all,
            "revenue_all": all_revenue,
            "revenue_all_display": _format_currency(all_revenue),
        },
        "rows": rows,
    }


def get_prepress_completed_reference_invoices() -> List[Dict[str, Any]]:
    """
    Completed invoices for reference/restore.

    Important:
    - Intended to let users un-complete an invoice if completed accidentally.
    - Workflow state comes from MySQL (retriever_prepress).
    - Account/taken-by headers are enriched from MIS in one batch query.
    """
    cols = {c.lower() for c in (_get_table_columns(PREPRESS_DB_NAME, "invoice_state") or [])}
    select_fields: List[str] = [
        "invoice_number",
        "working_started_at",
        "completed_at",
        ("completed_set_by" if "completed_set_by" in cols else "NULL AS completed_set_by"),
        "notes",
    ]

    invoice_rows = _mysql_fetch_all(
        f"""
        SELECT {', '.join(select_fields)}
        FROM invoice_state
        WHERE completed_at IS NOT NULL
        ORDER BY completed_at DESC, invoice_number
        """.strip(),
        None,
        PREPRESS_DB_NAME,
    )

    proof_rows = _mysql_fetch_all(
        """
        SELECT invoice_number, MAX(round_number) AS max_round
        FROM proof_event
        GROUP BY invoice_number
        """,
        None,
        PREPRESS_DB_NAME,
    )
    proof_max_by_invoice = {
        str(r["invoice_number"]): int(r.get("max_round") or 0) for r in proof_rows if r.get("invoice_number")
    }

    invoice_numbers = [
        str(r.get("invoice_number") or "").strip()
        for r in invoice_rows
        if str(r.get("invoice_number") or "").strip()
    ]
    account_header_by_invoice: Dict[str, Dict[str, Any]] = {}
    if invoice_numbers:
        mis_client = get_mis_client()
        conn = None
        cursor = None
        try:
            conn = mis_client.get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                  ib.invoicenumber::text AS "InvoiceNumber",
                  a.title AS "AccountName",
                  ib.takenby AS "TakenBy"
                FROM public.invoice inv
                INNER JOIN public.invoicebase ib
                  ON inv.id = ib.id
                INNER JOIN public.account a
                  ON ib.account_id = a.id
                WHERE ib.invoicenumber::text = ANY(%s::text[])
                """,
                (invoice_numbers,),
            )
            rows = cursor.fetchall() or []
            columns = [desc[0] for desc in cursor.description]
            for row in rows:
                d = dict(zip(columns, row))
                inv_num = str(d.get("InvoiceNumber") or "").strip()
                if not inv_num:
                    continue
                account_header_by_invoice[inv_num] = d
        except Exception as e:
            SecureErrorHandler.handle_database_error(e, "getting prepress completed invoice headers from MIS")
            account_header_by_invoice = {}
        finally:
            try:
                if cursor is not None:
                    cursor.close()
            except Exception:
                pass
            try:
                if conn is not None:
                    conn.close()
            except Exception:
                pass

    operators = get_prepress_operators()
    alias_by_key, operator_names = _build_prepress_actor_alias_map(operators)

    out: List[Dict[str, Any]] = []
    for r in invoice_rows:
        invoice_number = str(r.get("invoice_number") or "").strip()
        if not invoice_number:
            continue
        header = account_header_by_invoice.get(invoice_number, {})
        out.append(
            {
                "invoice_number": invoice_number,
                "account_name": str(header.get("AccountName") or ""),
                "taken_by": str(header.get("TakenBy") or ""),
                "working_started_at": r.get("working_started_at"),
                "completed_at": r.get("completed_at"),
                "completed_set_by": normalize_prepress_actor_name(
                    str(r.get("completed_set_by") or ""),
                    operators=operators,
                    alias_by_key=alias_by_key,
                    operator_names=operator_names,
                ),
                "notes": r.get("notes") or "",
                "most_proof_round": proof_max_by_invoice.get(invoice_number, 0),
            }
        )

    return out


def upsert_invoice_state(
    invoice_number: str,
    *,
    owner_prepress_id: Optional[int] = None,
    owner_set_by: Optional[str] = None,
    is_hold: Optional[bool] = None,
    needs_data: Optional[bool] = None,
    working_started_at: Optional[datetime] = None,
    completed_at: Optional[datetime] = None,
    notes: Optional[str] = None,
) -> bool:
    """Upsert invoice_state row in retriever_prepress."""
    query = """
    INSERT INTO invoice_state
      (invoice_number, owner_prepress_id, owner_set_at, owner_set_by,
       is_hold, needs_data, working_started_at, completed_at, notes)
    VALUES
      (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE
      owner_prepress_id = COALESCE(VALUES(owner_prepress_id), owner_prepress_id),
      owner_set_at = COALESCE(VALUES(owner_set_at), owner_set_at),
      owner_set_by = COALESCE(VALUES(owner_set_by), owner_set_by),
      is_hold = COALESCE(VALUES(is_hold), is_hold),
      needs_data = COALESCE(VALUES(needs_data), needs_data),
      working_started_at = COALESCE(VALUES(working_started_at), working_started_at),
      completed_at = COALESCE(VALUES(completed_at), completed_at),
      notes = COALESCE(VALUES(notes), notes)
    """
    now = datetime.now()
    owner_set_at = now if owner_prepress_id is not None else None
    params: Tuple[Any, ...] = (
        invoice_number,
        owner_prepress_id,
        owner_set_at,
        owner_set_by,
        1 if is_hold is True else (0 if is_hold is False else None),
        1 if needs_data is True else (0 if needs_data is False else None),
        working_started_at,
        completed_at,
        notes,
    )
    return _mysql_execute(query, params, PREPRESS_DB_NAME)


def set_invoice_hold(invoice_number: str, is_hold: bool) -> bool:
    query = """
    INSERT INTO invoice_state (invoice_number, is_hold)
    VALUES (%s, %s)
    ON DUPLICATE KEY UPDATE
      is_hold = VALUES(is_hold)
    """
    return _mysql_execute(query, (invoice_number, 1 if is_hold else 0), PREPRESS_DB_NAME)


def set_invoice_needs_data(invoice_number: str, needs_data: bool) -> bool:
    query = """
    INSERT INTO invoice_state (invoice_number, needs_data)
    VALUES (%s, %s)
    ON DUPLICATE KEY UPDATE
      needs_data = VALUES(needs_data)
    """
    return _mysql_execute(query, (invoice_number, 1 if needs_data else 0), PREPRESS_DB_NAME)


def set_invoice_working_started_at(
    invoice_number: str,
    working_started_at: Optional[datetime],
    *,
    working_set_by: Optional[str] = None,
) -> bool:
    """
    Set invoice working_started_at and optionally who set it.

    This uses a best-effort approach: if the DB is not yet migrated to include
    working_set_by, it will fall back to timestamp-only writes.
    """
    query_with_user = """
    INSERT INTO invoice_state (invoice_number, working_started_at, working_set_by)
    VALUES (%s, %s, %s)
    ON DUPLICATE KEY UPDATE
      working_started_at = VALUES(working_started_at),
      working_set_by = COALESCE(VALUES(working_set_by), working_set_by)
    """
    if working_set_by is not None:
        ok = _mysql_execute(query_with_user, (invoice_number, working_started_at, working_set_by), PREPRESS_DB_NAME)
        if ok:
            return True

    query = """
    INSERT INTO invoice_state (invoice_number, working_started_at)
    VALUES (%s, %s)
    ON DUPLICATE KEY UPDATE
      working_started_at = VALUES(working_started_at)
    """
    return _mysql_execute(query, (invoice_number, working_started_at), PREPRESS_DB_NAME)


def set_invoice_completed_at(
    invoice_number: str,
    completed_at: Optional[datetime],
    *,
    completed_set_by: Optional[str] = None,
) -> bool:
    """
    Set invoice completed_at and optionally who set it.

    Best-effort approach: falls back to timestamp-only writes if DB not migrated.
    """
    query_with_user = """
    INSERT INTO invoice_state (invoice_number, completed_at, completed_set_by)
    VALUES (%s, %s, %s)
    ON DUPLICATE KEY UPDATE
      completed_at = VALUES(completed_at),
      completed_set_by = COALESCE(VALUES(completed_set_by), completed_set_by)
    """
    if completed_set_by is not None:
        ok = _mysql_execute(query_with_user, (invoice_number, completed_at, completed_set_by), PREPRESS_DB_NAME)
        if ok:
            return True

    query = """
    INSERT INTO invoice_state (invoice_number, completed_at)
    VALUES (%s, %s)
    ON DUPLICATE KEY UPDATE
      completed_at = VALUES(completed_at)
    """
    return _mysql_execute(query, (invoice_number, completed_at), PREPRESS_DB_NAME)


def set_invoice_notes(invoice_number: str, notes: str) -> bool:
    query = """
    INSERT INTO invoice_state (invoice_number, notes)
    VALUES (%s, %s)
    ON DUPLICATE KEY UPDATE
      notes = VALUES(notes)
    """
    return _mysql_execute(query, (invoice_number, notes), PREPRESS_DB_NAME)


def set_invoice_owner(invoice_number: str, owner_prepress_id: int, owner_set_by: str) -> bool:
    query = """
    INSERT INTO invoice_state (invoice_number, owner_prepress_id, owner_set_at, owner_set_by)
    VALUES (%s, %s, NOW(), %s)
    ON DUPLICATE KEY UPDATE
      owner_prepress_id = VALUES(owner_prepress_id),
      owner_set_at = VALUES(owner_set_at),
      owner_set_by = VALUES(owner_set_by)
    """
    return _mysql_execute(query, (invoice_number, owner_prepress_id, owner_set_by), PREPRESS_DB_NAME)


def clear_invoice_owner(invoice_number: str) -> bool:
    query = """
    UPDATE invoice_state
    SET owner_prepress_id = NULL, owner_set_at = NULL, owner_set_by = NULL
    WHERE invoice_number = %s
    """
    return _mysql_execute(query, (invoice_number,), PREPRESS_DB_NAME)


def append_invoice_owner_history(invoice_number: str, owner_prepress_id: Optional[int], set_by: str) -> bool:
    query = """
    INSERT INTO invoice_owner_history (invoice_number, owner_prepress_id, set_by)
    VALUES (%s, %s, %s)
    """
    return _mysql_execute(query, (invoice_number, owner_prepress_id, set_by), PREPRESS_DB_NAME)


def upsert_jobpart_note(invoice_number: str, job_part_number: str, notes: str) -> bool:
    query = """
    INSERT INTO jobpart_state (invoice_number, job_part_number, notes)
    VALUES (%s, %s, %s)
    ON DUPLICATE KEY UPDATE
      notes = VALUES(notes)
    """
    return _mysql_execute(query, (invoice_number, job_part_number, notes), PREPRESS_DB_NAME)


def add_next_proof_event(invoice_number: str, job_part_number: str, sent_by: str) -> bool:
    """Insert next proof round (max+1) for a job part."""
    # Get current max round
    query_max = """
    SELECT COALESCE(MAX(round_number), 0) AS max_round
    FROM proof_event
    WHERE invoice_number = %s AND job_part_number = %s
    """
    rows = _mysql_fetch_all(query_max, (invoice_number, job_part_number), PREPRESS_DB_NAME)
    max_round = 0
    if rows:
        try:
            max_round = int(rows[0].get("max_round") or 0)
        except Exception:
            max_round = 0
    next_round = max_round + 1

    query = """
    INSERT INTO proof_event (invoice_number, job_part_number, round_number, sent_by)
    VALUES (%s, %s, %s, %s)
    """
    return _mysql_execute(query, (invoice_number, job_part_number, next_round, sent_by), PREPRESS_DB_NAME)

