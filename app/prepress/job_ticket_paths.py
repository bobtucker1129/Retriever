"""
Resolve invoice job folders and Remote/ target for PrePress job ticket PDF saves.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, List, Optional, Tuple

if TYPE_CHECKING:
    from config import Config


def _year_suffix_2digit(now_year: int) -> int:
    return now_year % 100


def build_default_search_roots(config: Config, year_2digit: Optional[int] = None) -> List[str]:
    """
    Built-in hierarchy (first match wins):
    1. D:\\Jobs_{yy}
    2. \\\\bggol-vxmpie01\\XMPie\\HIPAAJobs
    3. D:\\SwitchJobs\\Jobs_{yy}
    4. \\\\bggol-vxmpie01\\XMPie\\Switch_SECURE\\Secure_{yy}
    """
    from datetime import datetime

    y = year_2digit
    if y is None:
        y = _year_suffix_2digit(datetime.now().year)
    j = f"Jobs_{y:02d}"
    s = f"Secure_{y:02d}"
    return [
        os.path.join("D:\\", j),
        r"\\bggol-vxmpie01\XMPie\HIPAAJobs",
        os.path.join("D:\\SwitchJobs", j),
        rf"\\bggol-vxmpie01\XMPie\Switch_SECURE\{s}",
    ]


def parse_search_roots_from_config(config: Config) -> List[str]:
    raw = (
        getattr(config, "prepress_job_ticket_search_roots", None)
        or getattr(config, "PREPRESS_JOB_TICKET_SEARCH_ROOTS", None)
        or ""
    ).strip()
    if not raw:
        return build_default_search_roots(config)
    parts = [p.strip() for p in raw.split(",")]
    return [p for p in parts if p]


def find_remote_directory_for_invoice(
    invoice_number: str,
    roots: List[str],
) -> Tuple[Optional[str], List[str]]:
    """
    Under the first root that contains a child folder named like ``{invoice}_...``,
    return ``{that_folder}/Remote`` (folder may be created by caller).

    Returns (remote_dir_or_none, roots_checked_in_order).
    """
    prefix = f"{invoice_number}_"
    checked: List[str] = []
    for root in roots:
        checked.append(root)
        if not root or not os.path.isdir(root):
            continue
        try:
            for name in os.listdir(root):
                if name.startswith(prefix):
                    job_folder = os.path.join(root, name)
                    if os.path.isdir(job_folder):
                        return os.path.join(job_folder, "Remote"), checked
        except OSError:
            continue
    return None, checked
