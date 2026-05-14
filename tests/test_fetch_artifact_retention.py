"""Unit tests for local HTML artifact retention helpers."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.config import AppSettings
from app.db.repositories.fetch import FetchMessageRecord
from app.fetch.artifact_retention import (
    filter_message_metadata_for_local_retention,
    local_html_stem_from_download_path,
    prune_expired_local_html_exports,
    unlink_local_snapshot_files_from_messages,
)
from app.fetch.html_export import (
    artifact_download_path_for_stem,
    artifact_pdf_download_path_for_stem,
    build_local_html_export_artifact_entry,
    write_html_export_file,
)


def test_build_local_html_export_artifact_entry_includes_expiry_and_scope() -> None:
    settings = AppSettings()
    issued = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    path = artifact_download_path_for_stem(uuid.uuid4().hex)
    entry = build_local_html_export_artifact_entry(path, settings, issued_at=issued)
    assert entry["storageScope"] == "retriever_local"
    assert entry["issuedAtUtc"].startswith("2026-01-01T12:00:00")
    assert entry["expiresAtUtc"].startswith("2026-01-31T12:00:00")
    assert entry["downloadPath"] == path


def test_local_html_stem_from_download_path() -> None:
    stem = uuid.uuid4().hex
    assert local_html_stem_from_download_path(f"/fetch/artifacts/html/{stem}.html") == stem
    assert local_html_stem_from_download_path(f"/fetch/artifacts/pdf/{stem}.pdf") is None
    assert local_html_stem_from_download_path("/fetch/artifacts/broker/x") is None
    assert local_html_stem_from_download_path("") is None


def test_filter_drops_expired_local_html_artifact(tmp_path: Path) -> None:
    settings = AppSettings(retriever_report_dir=tmp_path)
    stem = uuid.uuid4().hex
    path = artifact_download_path_for_stem(stem)
    (tmp_path / "fetch_html_exports").mkdir(parents=True)
    (tmp_path / "fetch_html_exports" / f"{stem}.html").write_text("<html/>", encoding="utf-8")
    meta = {
        "artifacts": [
            {
                "filename": "fetch-answer-export.html",
                "downloadPath": path,
                "expiresAtUtc": "2000-01-01T00:00:00Z",
            }
        ]
    }
    now = datetime.now(timezone.utc)
    out = filter_message_metadata_for_local_retention(
        meta, settings, now_utc=now, message_created_at=None
    )
    assert out is None


def test_filter_keeps_broker_path_artifacts() -> None:
    settings = AppSettings(retriever_report_dir=Path("/tmp/should-not-touch"))
    meta = {
        "artifacts": [
            {
                "filename": "Q.xlsx",
                "downloadPath": "/fetch/artifacts/broker/550e8400-e29b-41d4-a716-446655440000",
            }
        ]
    }
    out = filter_message_metadata_for_local_retention(
        meta, settings, now_utc=datetime.now(timezone.utc), message_created_at=None
    )
    assert out is meta


def test_filter_drops_expired_local_pdf_artifact(tmp_path: Path) -> None:
    settings = AppSettings(retriever_report_dir=tmp_path)
    stem = uuid.uuid4().hex
    path = artifact_pdf_download_path_for_stem(stem)
    (tmp_path / "fetch_html_exports").mkdir(parents=True)
    (tmp_path / "fetch_html_exports" / f"{stem}.pdf").write_bytes(b"%PDF-1.4\n")
    meta = {
        "artifacts": [
            {
                "filename": "fetch-answer-export.pdf",
                "downloadPath": path,
                "expiresAtUtc": "2000-01-01T00:00:00Z",
            }
        ]
    }
    now = datetime.now(timezone.utc)
    out = filter_message_metadata_for_local_retention(
        meta, settings, now_utc=now, message_created_at=None
    )
    assert out is None


def test_prune_removes_files_past_retention(tmp_path: Path) -> None:
    settings = AppSettings(
        retriever_report_dir=tmp_path,
        fetch_local_artifact_retention_days=7,
    )
    export_dir = tmp_path / "fetch_html_exports"
    export_dir.mkdir(parents=True)
    old = export_dir / "old.html"
    old.write_text("a", encoding="utf-8")
    ts = (datetime.now(timezone.utc) - timedelta(days=10)).timestamp()
    os.utime(old, (ts, ts))
    fresh = export_dir / f"{uuid.uuid4().hex}.html"
    fresh.write_text("b", encoding="utf-8")
    stale_pdf = export_dir / "stale.pdf"
    stale_pdf.write_bytes(b"%PDF stale")
    ts = (datetime.now(timezone.utc) - timedelta(days=10)).timestamp()
    os.utime(stale_pdf, (ts, ts))
    now = datetime.now(timezone.utc)
    removed = prune_expired_local_html_exports(settings, now_utc=now)
    assert removed == 2
    assert not old.exists()
    assert fresh.is_file()
    assert not stale_pdf.exists()


def test_write_html_export_then_prune_does_not_remove_brand_new_file(tmp_path: Path) -> None:
    settings = AppSettings(retriever_report_dir=tmp_path, fetch_local_artifact_retention_days=7)
    doc = "<!DOCTYPE html><html><body>x</body></html>"
    write_html_export_file(settings, doc)
    prune_expired_local_html_exports(settings)
    export_dir = tmp_path / "fetch_html_exports"
    assert len(list(export_dir.glob("*.html"))) == 1


def test_unlink_local_snapshots_removes_html_and_pdf(tmp_path: Path) -> None:
    settings = AppSettings(retriever_report_dir=tmp_path)
    stem_html = uuid.uuid4().hex
    stem_pdf = uuid.uuid4().hex
    export_dir = tmp_path / "fetch_html_exports"
    export_dir.mkdir(parents=True)
    html_path = export_dir / f"{stem_html}.html"
    pdf_path = export_dir / f"{stem_pdf}.pdf"
    html_path.write_text("<html/>", encoding="utf-8")
    pdf_path.write_bytes(b"%PDF-1.4")

    msg = FetchMessageRecord(
        message_id="m1",
        conversation_id="c1",
        user_id=1,
        role="assistant",
        content="x",
        route_key="local",
        metadata={
            "artifacts": [
                {"filename": "a.html", "downloadPath": artifact_download_path_for_stem(stem_html)},
                {"filename": "b.pdf", "downloadPath": artifact_pdf_download_path_for_stem(stem_pdf)},
                {
                    "filename": "broker.xlsx",
                    "downloadPath": "/fetch/artifacts/broker/550e8400-e29b-41d4-a716-446655440000",
                },
            ]
        },
    )
    removed = unlink_local_snapshot_files_from_messages([msg], settings)
    assert removed == 2
    assert not html_path.exists()
    assert not pdf_path.exists()
