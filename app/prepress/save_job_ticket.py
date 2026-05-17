"""
Orchestrate PrePress job ticket PDF fetch + write under invoice .../Remote/.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from config import Config
from app.database.queries import prepress as prepress_queries
from app.prepress.job_ticket_paths import find_remote_directory_for_invoice, parse_search_roots_from_config
from app.prepress.printsmith_job_ticket import (
    fetch_invoice_ticket_pdf,
    fetch_job_ticket_pdf,
    merge_pdf_bytes,
)

logger = logging.getLogger(__name__)


@dataclass
class JobTicketSaveResult:
    ok: bool
    message: str
    path: Optional[str] = None


def _safe_filename_segment(inv: str) -> str:
    s = str(inv or "").strip()
    if not re.match(r"^[a-zA-Z0-9_-]{1,50}$", s):
        return re.sub(r"[^a-zA-Z0-9_-]+", "_", s)[:50]
    return s


async def save_job_ticket_to_remote(
    config: Config,
    invoice_number: str,
    mode: str,
    job_part_numbers: List[str],
) -> JobTicketSaveResult:
    if not getattr(config, "PREPRESS_JOB_TICKET_SAVE_ENABLED", False):
        return JobTicketSaveResult(False, "Saving job tickets to disk is disabled (set PREPRESS_JOB_TICKET_SAVE_ENABLED).")

    if mode not in ("invoice", "parts"):
        return JobTicketSaveResult(False, "Invalid mode.")

    if not prepress_queries.is_invoice_eligible_for_job_ticket_save(invoice_number):
        return JobTicketSaveResult(False, "This invoice is not in the active PrePress WIP list.")

    roots = parse_search_roots_from_config(config)
    remote_dir, _checked = find_remote_directory_for_invoice(invoice_number, roots)
    if not remote_dir:
        return JobTicketSaveResult(
            False,
            f"No job folder matching invoice {invoice_number}_* was found under configured roots.",
        )

    try:
        os.makedirs(remote_dir, exist_ok=True)
    except OSError as e:
        logger.warning("Could not create Remote directory: %s", e)
        return JobTicketSaveResult(False, "Could not create or access the Remote folder for this job (see server logs).")

    tz = ZoneInfo(getattr(config, "PREPRESS_JOB_TICKET_TIMEZONE", "America/Los_Angeles") or "America/Los_Angeles")
    stamp = datetime.now(tz).strftime("%Y%m%d-%H%M%S")
    prefix = getattr(config, "PREPRESS_JOB_TICKET_FILE_PREFIX", "Y1") or "Y1"
    inv_seg = _safe_filename_segment(invoice_number)
    filename = f"{prefix}_JobTicket_{inv_seg}_{stamp}.pdf"
    out_path = os.path.join(remote_dir, filename)

    try:
        if mode == "invoice":
            pdf = await fetch_invoice_ticket_pdf(config, invoice_number)
        else:
            raw_parts = [str(x).strip() for x in (job_part_numbers or []) if str(x).strip()]
            if not raw_parts:
                return JobTicketSaveResult(False, "Select at least one job part.")
            seen: set[str] = set()
            ordered_keys: List[str] = []
            for p in raw_parts:
                if p not in seen:
                    seen.add(p)
                    ordered_keys.append(p)

            rows = prepress_queries.get_invoice_job_parts(invoice_number)
            by_part = {str(r.get("job_part_number") or ""): r for r in rows}
            seen_indices: set[int] = set()
            job_indices: List[int] = []
            missing: List[str] = []
            for key in ordered_keys:
                r = by_part.get(key)
                if not r or r.get("job_index") is None:
                    missing.append(key)
                else:
                    idx = int(r["job_index"])
                    if idx not in seen_indices:
                        seen_indices.add(idx)
                        job_indices.append(idx)
            if missing:
                return JobTicketSaveResult(False, f"Could not resolve job part(s): {', '.join(missing)}")

            blobs: List[bytes] = []
            for idx in job_indices:
                try:
                    blobs.append(await fetch_job_ticket_pdf(config, invoice_number, idx))
                except Exception as e:
                    logger.warning("Job ticket PDF fetch failed for invoice=%s jobIndex=%s: %s", invoice_number, idx, e)
                    return JobTicketSaveResult(
                        False,
                        f"PrintSmith did not return a PDF for one of the selected parts (job index {idx}).",
                    )
            pdf = merge_pdf_bytes(blobs)

        tmp_path = out_path + ".tmp"
        with open(tmp_path, "wb") as f:
            f.write(pdf)
        os.replace(tmp_path, out_path)
    except ValueError as e:
        return JobTicketSaveResult(False, str(e))
    except OSError as e:
        logger.warning("Job ticket PDF write failed for %s: %s", invoice_number, e)
        try:
            if os.path.isfile(out_path + ".tmp"):
                os.unlink(out_path + ".tmp")
        except OSError:
            pass
        return JobTicketSaveResult(False, "Could not write the PDF to the job folder (check server permissions).")
    except Exception as e:
        logger.exception("Unexpected error saving job ticket for %s", invoice_number)
        return JobTicketSaveResult(False, "Unexpected error while saving job ticket.")

    rel_hint = filename
    return JobTicketSaveResult(True, f"Saved {rel_hint} under Remote.", path=out_path)
