"""Local Fetch artifact retention: expiry metadata, disk pruning, shell-time card filtering."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.config import AppSettings
from app.fetch.html_export import (
    FETCH_HTML_ARTIFACT_PATH_PREFIX,
    FETCH_PDF_ARTIFACT_PATH_PREFIX,
    is_safe_html_export_file_id,
    resolve_export_disk_path,
    resolve_pdf_export_disk_path,
)


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_iso_datetime_utc(raw: object) -> datetime | None:
    """Parse ISO-8601 timestamps from artifact metadata; returns timezone-aware UTC."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    return _as_utc(dt)


def local_answer_snapshot_parts_from_download_path(
    download_path: object,
) -> tuple[str, str] | None:
    """Resolve ``(stem, 'html'|'pdf')`` for Retriever-local answer snapshots or ``None``."""
    if download_path is None:
        return None
    p = str(download_path).strip()
    stem: str
    suffix: str
    if p.startswith(FETCH_HTML_ARTIFACT_PATH_PREFIX) and p.endswith(".html"):
        stem = p[len(FETCH_HTML_ARTIFACT_PATH_PREFIX) : -len(".html")]
        suffix = "html"
    elif p.startswith(FETCH_PDF_ARTIFACT_PATH_PREFIX) and p.endswith(".pdf"):
        stem = p[len(FETCH_PDF_ARTIFACT_PATH_PREFIX) : -len(".pdf")]
        suffix = "pdf"
    else:
        return None
    if not is_safe_html_export_file_id(stem):
        return None
    return stem, suffix


def local_html_stem_from_download_path(download_path: object) -> str | None:
    """Return uuid stem for legacy HTML snapshots only."""
    parsed = local_answer_snapshot_parts_from_download_path(download_path)
    if parsed is None:
        return None
    stem, suffix = parsed
    return stem if suffix == "html" else None


def retention_timedelta(settings: AppSettings) -> timedelta:
    days = max(1, int(settings.fetch_local_artifact_retention_days))
    return timedelta(days=days)


def compute_local_answer_snapshot_expires_at_utc(
    artifact: dict[str, Any],
    settings: AppSettings,
    message_created_at: datetime | None,
) -> datetime | None:
    """Best-effort expiry instant for one local HTML or PDF snapshot row."""
    parsed = parse_iso_datetime_utc(artifact.get("expiresAtUtc"))
    if parsed is not None:
        return parsed
    issued = parse_iso_datetime_utc(artifact.get("issuedAtUtc"))
    if issued is not None:
        return issued + retention_timedelta(settings)
    if message_created_at is not None:
        return _as_utc(message_created_at) + retention_timedelta(settings)
    parts = local_answer_snapshot_parts_from_download_path(artifact.get("downloadPath"))
    if not parts:
        return None
    stem, suffix = parts
    if suffix == "html":
        disk = resolve_export_disk_path(settings, stem)
    else:
        disk = resolve_pdf_export_disk_path(settings, stem)
    if disk is None or not disk.is_file():
        return None
    mtime = datetime.fromtimestamp(disk.stat().st_mtime, tz=timezone.utc)
    return mtime + retention_timedelta(settings)


def compute_local_html_expires_at_utc(
    artifact: dict[str, Any],
    settings: AppSettings,
    message_created_at: datetime | None,
) -> datetime | None:
    """Best-effort expiry for local HTML snapshots (delegates shared helper)."""
    return compute_local_answer_snapshot_expires_at_utc(
        artifact,
        settings,
        message_created_at,
    )


def local_html_artifact_is_visible(
    artifact: dict[str, Any],
    settings: AppSettings,
    now_utc: datetime,
    message_created_at: datetime | None,
) -> bool:
    """Whether a local snapshot card should remain visible (silent when false)."""
    parts = local_answer_snapshot_parts_from_download_path(artifact.get("downloadPath"))
    if parts is None:
        return True
    stem, suffix = parts
    if suffix == "html":
        disk = resolve_export_disk_path(settings, stem)
    else:
        disk = resolve_pdf_export_disk_path(settings, stem)
    if disk is None or not disk.is_file():
        return False
    expires_at = compute_local_answer_snapshot_expires_at_utc(
        artifact,
        settings,
        message_created_at,
    )
    if expires_at is not None and now_utc >= _as_utc(expires_at):
        return False
    return True


def filter_message_metadata_for_local_retention(
    metadata: Optional[dict[str, Any]],
    settings: AppSettings,
    *,
    now_utc: datetime,
    message_created_at: datetime | None,
) -> Optional[dict[str, Any]]:
    """Drop expired or missing Retriever-local snapshot artifacts; leave broker metadata unchanged."""
    if not metadata:
        return metadata
    raw_artifacts = metadata.get("artifacts")
    if not isinstance(raw_artifacts, list) or not raw_artifacts:
        return metadata
    filtered: list[dict[str, Any]] = []
    changed = False
    for entry in raw_artifacts:
        if not isinstance(entry, dict):
            filtered.append(entry)
            continue
        if local_answer_snapshot_parts_from_download_path(entry.get("downloadPath")) is None:
            filtered.append(entry)
            continue
        if local_html_artifact_is_visible(entry, settings, now_utc, message_created_at):
            filtered.append(entry)
        else:
            changed = True
    if not changed:
        return metadata
    out = deepcopy(metadata)
    if filtered:
        out["artifacts"] = filtered
    else:
        out.pop("artifacts", None)
    if not out.get("source_cards") and not out.get("artifacts") and not out.get("status_cards"):
        return None
    return out


def prune_expired_local_html_exports(
    settings: AppSettings,
    *,
    now_utc: datetime | None = None,
) -> int:
    """Remove on-disk HTML/PDF snapshot files past retention (mtime + TTL). Returns count deleted."""
    when = now_utc or datetime.now(timezone.utc)
    base = (
        settings.retriever_report_dir / "fetch_html_exports"
    ).resolve(strict=False)
    if not base.is_dir():
        return 0
    ttl = retention_timedelta(settings)
    removed = 0
    for pattern in ("*.html", "*.pdf"):
        for path in base.glob(pattern):
            if not path.is_file():
                continue
            mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            if when >= mtime + ttl:
                path.unlink(missing_ok=True)
                removed += 1
    return removed
