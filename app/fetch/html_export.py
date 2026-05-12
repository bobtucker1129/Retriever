"""Retriever-local sanitized HTML artifacts for Fetch follow-up exports."""

from __future__ import annotations

import html
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

from app.config import AppSettings
from app.fetch.answer_render import assistant_body_html

_FETCH_HTML_SUBDIR: Final[str] = "fetch_html_exports"
_HTML_EXPORT_ROUTE_PREFIX: Final[str] = "/fetch/artifacts/html/"
_FILE_ID_RE: Final[re.Pattern[str]] = re.compile(r"^[a-f0-9]{32}$")

HTML_EXPORT_NEED_PRIOR_REPLY: Final[str] = (
    "I need a successful PrintSmith or documentation answer before I can export that as HTML. "
    "Ask your report or docs question first, then request an HTML export of that reply.\n\n"
    "Nothing was saved beyond this message."
)


def _export_dir(settings: AppSettings) -> Path:
    return settings.retriever_report_dir / _FETCH_HTML_SUBDIR


def is_safe_html_export_file_id(file_id: str) -> bool:
    """Whether ``file_id`` is a basename stem we issue (uuid4 hex)."""
    return bool(file_id) and bool(_FILE_ID_RE.fullmatch(file_id))


def artifact_download_path_for_stem(stem: str) -> str:
    """Stable same-origin ``downloadPath`` for metadata cards."""
    return f"{_HTML_EXPORT_ROUTE_PREFIX}{stem}.html"


def build_standalone_html_export_document(
    answer_plain_text: str,
    *,
    source_route_label: str,
    exported_at: datetime | None = None,
) -> str:
    """Full HTML document: prior answer rendered like assistant bubbles (markdown + nh3)."""
    when = exported_at or datetime.now(timezone.utc)
    iso = when.isoformat(timespec="seconds")
    title_safe = html.escape(f"Fetch export ({source_route_label}) — {iso}")
    route_safe = html.escape(source_route_label)
    iso_safe = html.escape(iso)
    body_markup = assistant_body_html(answer_plain_text or "")
    body_html = str(body_markup)

    doc = (
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n"
        "<meta charset=\"utf-8\">\n"
        '<meta http-equiv="Content-Security-Policy" '
        'content="default-src \'none\'; style-src \'unsafe-inline\'">\n'
        f"<title>{title_safe}</title>\n<style>\n"
        "body{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;"
        "line-height:1.45;max-width:48rem;margin:2rem auto;padding:0 1rem;color:#111;}"
        "header{border-bottom:1px solid #ccc;margin-bottom:1.5rem;padding-bottom:1rem;}"
        "header p{margin:0.25rem 0;font-size:0.875rem;color:#444;}"
        "main{overflow-wrap:anywhere}\n"
        "table{border-collapse:collapse;}th,td{border:1px solid #ccc;padding:0.35rem}\n"
        "</style>\n</head>\n<body>\n"
        "<header><h1>Exported answer</h1>"
        f"<p>Source route: <span>{route_safe}</span></p>"
        f"<p>Exported (UTC): <span>{iso_safe}</span></p></header>\n"
        f"<main>{body_html}</main>\n</body>\n</html>\n"
    )
    return doc


def write_html_export_file(settings: AppSettings, document: str) -> tuple[str, Path]:
    """Write ``document`` under the configured report subtree; return (download_path, disk_path)."""
    base = _export_dir(settings)
    base.mkdir(parents=True, exist_ok=True)
    stem = uuid.uuid4().hex
    disk_path = base / f"{stem}.html"
    disk_path.write_text(document, encoding="utf-8")
    return artifact_download_path_for_stem(stem), disk_path


def resolve_export_disk_path(settings: AppSettings, file_id: str) -> Path | None:
    """Resolved path inside the export subdirectory, or ``None`` if unsafe or missing."""
    if not is_safe_html_export_file_id(file_id):
        return None
    base = _export_dir(settings).resolve(strict=False)
    path = (base / f"{file_id}.html").resolve(strict=False)
    try:
        path.relative_to(base)
    except ValueError:
        return None
    return path


def short_html_export_confirmation() -> str:
    return (
        "I saved an HTML snapshot of your previous Fetch answer. "
        "Use the attachment link below to download it "
        "(standalone page, sanitized; no scripts or embedded tokens)."
    )
