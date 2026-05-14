"""Retriever-local sanitized HTML artifacts for Fetch follow-up exports."""

from __future__ import annotations

import html
import logging
import re
import shutil
import subprocess
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from typing import Callable, Final, Optional, Tuple

from app.config import AppSettings
from app.fetch.answer_render import assistant_body_html

_FETCH_HTML_SUBDIR: Final[str] = "fetch_html_exports"
FETCH_HTML_ARTIFACT_PATH_PREFIX: Final[str] = "/fetch/artifacts/html/"
FETCH_PDF_ARTIFACT_PATH_PREFIX: Final[str] = "/fetch/artifacts/pdf/"
_FILE_ID_RE: Final[re.Pattern[str]] = re.compile(r"^[a-f0-9]{32}$")

_log = logging.getLogger(__name__)

HtmlToPdfFn = Callable[[str], Tuple[Optional[bytes], Optional[str]]]

HTML_EXPORT_NEED_PRIOR_REPLY: Final[str] = (
    "I need a successful PrintSmith or documentation answer before I can export that as HTML. "
    "Ask your report or docs question first, then request an HTML export of that reply.\n\n"
    "Nothing was saved beyond this message."
)

PDF_EXPORT_NEED_PRIOR_REPLY: Final[str] = (
    "I need a successful PrintSmith or documentation answer before I can save that reply as a PDF. "
    "Ask your question first, then ask to save this answer as a PDF.\n\n"
    "Nothing was saved beyond this message."
)


def _export_dir(settings: AppSettings) -> Path:
    return settings.retriever_report_dir / _FETCH_HTML_SUBDIR


def is_safe_html_export_file_id(file_id: str) -> bool:
    """Whether ``file_id`` is a basename stem we issue (uuid4 hex)."""
    return bool(file_id) and bool(_FILE_ID_RE.fullmatch(file_id))


def artifact_download_path_for_stem(stem: str) -> str:
    """Stable same-origin ``downloadPath`` for metadata cards."""
    return f"{FETCH_HTML_ARTIFACT_PATH_PREFIX}{stem}.html"


def artifact_pdf_download_path_for_stem(stem: str) -> str:
    """Same-origin ``downloadPath`` for local answer-snapshot PDF cards."""
    return f"{FETCH_PDF_ARTIFACT_PATH_PREFIX}{stem}.pdf"


def build_local_html_export_artifact_entry(
    download_path: str,
    settings: AppSettings,
    *,
    filename: str = "fetch-answer-export.html",
    description: str = "Sanitized standalone HTML snapshot of the prior answer.",
    issued_at: datetime | None = None,
) -> dict[str, str]:
    """Metadata for one Retriever-local HTML export, including honest UTC expiry for UI filtering."""
    when = issued_at or datetime.now(timezone.utc)
    ttl_days = max(1, int(settings.fetch_local_artifact_retention_days))
    expires = when + timedelta(days=ttl_days)
    return {
        "filename": filename,
        "description": description,
        "downloadPath": download_path,
        "storageScope": "retriever_local",
        "issuedAtUtc": when.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "expiresAtUtc": expires.isoformat(timespec="seconds").replace("+00:00", "Z"),
    }


def build_local_pdf_export_artifact_entry(
    download_path: str,
    settings: AppSettings,
    *,
    filename: str = "fetch-answer-export.pdf",
    description: str = "PDF snapshot of the prior answer (rendered from the same HTML export template).",
    issued_at: datetime | None = None,
) -> dict[str, str]:
    """Metadata for one Retriever-local PDF export (same TTL as HTML exports)."""
    return build_local_html_export_artifact_entry(
        download_path,
        settings,
        filename=filename,
        description=description,
        issued_at=issued_at,
    )


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


def _pdf_bytes_via_xhtml2pdf(html_document: str) -> bytes | None:
    """Optional xhtml2pdf path (``pip install .[pdf]``); returns ``None`` to try other engines."""
    try:
        from xhtml2pdf import pisa
    except ImportError:
        return None

    buffer = BytesIO()
    status = pisa.CreatePDF(html_document, dest=buffer, encoding="utf-8")
    data = buffer.getvalue()
    if status.err:
        _log.warning("xhtml2pdf reported errors for Fetch PDF export: %r", status.err)
        return None
    if not data:
        _log.warning("xhtml2pdf produced empty PDF output for Fetch export")
        return None
    return data


def _pdf_bytes_via_wkhtmltopdf(html_document: str) -> tuple[bytes | None, str | None]:
    """Use ``wkhtmltopdf`` when present on PATH (common on servers; optional on Windows)."""
    exe = shutil.which("wkhtmltopdf")
    if not exe:
        return None, None

    td = tempfile.mkdtemp(prefix="fetch_pdf_")
    try:
        html_path = Path(td) / "export.html"
        pdf_path = Path(td) / "export.pdf"
        html_path.write_text(html_document, encoding="utf-8")
        subprocess.run(
            [exe, "--quiet", str(html_path), str(pdf_path)],
            check=True,
            capture_output=True,
            timeout=120,
        )
        if not pdf_path.is_file():
            return None, "wkhtmltopdf produced no PDF file."
        data = pdf_path.read_bytes()
        if not data:
            return None, "wkhtmltopdf wrote an empty PDF."
        return data, None
    except subprocess.CalledProcessError as exc:
        stderr = getattr(exc, "stderr", None) or b""
        err = stderr.decode("utf-8", errors="replace").strip()
        tail = (" " + err[:300]) if err else ""
        return None, f"wkhtmltopdf failed while building the PDF.{tail}"
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, f"Could not run wkhtmltopdf ({exc}). Try HTML export instead."
    finally:
        shutil.rmtree(td, ignore_errors=True)


def default_html_export_document_to_pdf(html_document: str) -> tuple[bytes | None, str | None]:
    """Prefer optional xhtml2pdf, then ``wkhtmltopdf`` on PATH; otherwise explain what is missing."""
    via_xhtml = _pdf_bytes_via_xhtml2pdf(html_document)
    if via_xhtml:
        return via_xhtml, None

    via_wk, we = _pdf_bytes_via_wkhtmltopdf(html_document)
    if via_wk is not None:
        return via_wk, None
    if we is not None:
        return None, we

    return (
        None,
        "PDF export is not available here yet. Install wkhtmltopdf on the server PATH "
        "(works on Windows and Linux where the binary is available), "
        "or pip install xhtml2pdf where your OS already supplies Cairo/SVG prerequisites. "
        "You can still export the same answer as HTML.",
    )


def convert_html_export_document_to_pdf(
    html_document: str,
    *,
    converter: HtmlToPdfFn | None = None,
) -> tuple[bytes | None, str | None]:
    """HTML → PDF for answer snapshots; ``converter`` is for unit tests."""
    fn = converter or default_html_export_document_to_pdf
    return fn(html_document)


def write_pdf_export_file(settings: AppSettings, pdf_bytes: bytes) -> tuple[str, Path]:
    """Write ``pdf_bytes`` next to HTML exports; return (download_path, disk_path)."""
    base = _export_dir(settings)
    base.mkdir(parents=True, exist_ok=True)
    stem = uuid.uuid4().hex
    disk_path = base / f"{stem}.pdf"
    disk_path.write_bytes(pdf_bytes)
    return artifact_pdf_download_path_for_stem(stem), disk_path


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


def resolve_pdf_export_disk_path(settings: AppSettings, file_id: str) -> Path | None:
    """Resolved ``.pdf`` path inside the export subdirectory, or ``None`` if unsafe or missing."""
    if not is_safe_html_export_file_id(file_id):
        return None
    base = _export_dir(settings).resolve(strict=False)
    path = (base / f"{file_id}.pdf").resolve(strict=False)
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


def short_pdf_export_confirmation() -> str:
    return (
        "I saved a PDF snapshot of your previous Fetch answer. "
        "Use the attachment link below to download it "
        "(generated from the same standalone HTML export layout)."
    )
