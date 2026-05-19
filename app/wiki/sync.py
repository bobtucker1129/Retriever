"""Conservative Wiki source sync.

This module intentionally syncs metadata and draft cards only. Raw ISO/Drive
documents remain admin-only source links until a reviewed summary workflow says
otherwise.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable, Optional

import httpx

from app.config import AppSettings, get_settings
from app.db.connection import create_connection
from app.db.repositories.wiki import WikiDocumentUpsert, WikiLinkRecord, WikiRepository

INTERNAL_WIKI_URL = "https://www.boonegraphics.net/internal-wiki"


@dataclass(frozen=True)
class DriveInventoryItem:
    source_document_id: str
    title: str
    url: str
    path: str = ""
    modified_at: Optional[datetime] = None
    mime_type: str = ""


@dataclass(frozen=True)
class WikiSyncResult:
    source_key: str
    scanned_count: int
    changed_count: int
    status: str
    error_message: str = ""


class SweetProcessParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._active_href = ""
        self._active_text: list[str] = []
        self.links: list[WikiLinkRecord] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href") or ""
        if "sweetprocess.com/procedures/" not in href:
            return
        self._active_href = href.strip()
        self._active_text = []

    def handle_data(self, data: str) -> None:
        if self._active_href:
            self._active_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or not self._active_href:
            return
        label = sweetprocess_display_label(
            label=clean_label(" ".join(self._active_text)),
            url=self._active_href,
        )
        self.links.append(
            WikiLinkRecord(
                label=label,
                url=self._active_href,
                link_type="legacy",
                visible_to="employee",
            )
        )
        self._active_href = ""
        self._active_text = []


def clean_label(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def sweetprocess_display_label(*, label: str, url: str) -> str:
    cleaned = clean_label(label)
    if not cleaned or cleaned.lower() in {"link", "click here", "view", "open"}:
        return sweetprocess_label_from_url(url)
    return cleaned


def sweetprocess_label_from_url(url: str) -> str:
    slug = url.rstrip("/").split("/")[-1]
    slug = re.sub(r"-[a-z]{2}$", "", slug)
    words = clean_label(slug.replace("-", " ")).split(" ")
    acronyms = {"abi", "am", "dsf", "po", "sbcers", "st", "to", "umt", "ups", "xmpie"}
    return " ".join(word.upper() if word.lower() in acronyms else word.title() for word in words)


def parse_internal_wiki_links(html: str) -> list[WikiLinkRecord]:
    parser = SweetProcessParser()
    parser.feed(html)
    deduped: dict[str, WikiLinkRecord] = {}
    for link in parser.links:
        deduped.setdefault(link.url, link)
    return sorted(deduped.values(), key=lambda link: link.label.lower())


def load_drive_inventory(path: Path) -> list[DriveInventoryItem]:
    if not path.exists():
        raise FileNotFoundError(f"Drive inventory file not found: {path}")
    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = payload.get("files", payload) if isinstance(payload, dict) else payload
    else:
        rows = list(csv.DictReader(path.read_text(encoding="utf-8").splitlines()))
    if not isinstance(rows, list):
        raise ValueError("Drive inventory must be a JSON list, {files: [...]}, or CSV")
    return [_drive_item_from_mapping(row) for row in rows if isinstance(row, dict)]


def _drive_item_from_mapping(row: dict) -> DriveInventoryItem:
    title = str(row.get("title") or row.get("name") or row.get("filename") or "").strip()
    if not title:
        raise ValueError("Drive inventory row is missing title/name")
    modified_raw = str(
        row.get("modified_at") or row.get("modifiedTime") or row.get("modified") or ""
    ).strip()
    return DriveInventoryItem(
        source_document_id=str(row.get("id") or row.get("file_id") or row.get("url") or title),
        title=title,
        url=str(row.get("url") or row.get("webViewLink") or row.get("alternateLink") or ""),
        path=str(row.get("path") or row.get("folder") or row.get("parents") or ""),
        modified_at=parse_datetime(modified_raw) if modified_raw else None,
        mime_type=str(row.get("mimeType") or row.get("mime_type") or ""),
    )


def parse_datetime(value: str) -> Optional[datetime]:
    cleaned = value.strip()
    if not cleaned:
        return None
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(cleaned)
    except ValueError:
        return None


def drive_item_to_document(item: DriveInventoryItem) -> WikiDocumentUpsert:
    document_code = infer_document_code(item.title)
    category = infer_category(item.title, item.path)
    document_type = infer_document_type(item.title, item.path)
    title = human_document_title(item.title, document_code)
    stable_slug_base = f"{document_code} {title}" if document_code else title
    checksum = hashlib.sha256(
        "|".join([item.source_document_id, item.title, item.path, item.url]).encode("utf-8")
    ).hexdigest()
    return WikiDocumentUpsert(
        slug=WikiRepository.slugify(stable_slug_base),
        title=title,
        document_code=document_code,
        document_type=document_type,
        category=category,
        summary=build_draft_summary(title=title, code=document_code, category=category),
        source_document_id=item.source_document_id,
        source_url=item.url,
        source_modified_at=item.modified_at,
        source_checksum=checksum,
        raw_source_visible_to="admin",
    )


def infer_document_code(title: str) -> str:
    match = re.search(r"\b((?:WI|SOP|M|F|QF|QP)-\d{3,4})\b", title, flags=re.IGNORECASE)
    return match.group(1).upper() if match else ""


def infer_category(title: str, path: str) -> str:
    haystack = f"{path} {title}".lower()
    if "work instruction" in haystack or re.search(r"\bwi-\d", haystack):
        return "Work Instructions"
    if "security" in haystack or "secure" in haystack or "datalock" in haystack:
        return "Security Posture"
    if "quality" in haystack or "iso" in haystack or "sop-" in haystack or "manual" in haystack:
        return "Quality & ISO"
    if "training" in haystack:
        return "General Knowledge"
    return "General Knowledge"


def infer_document_type(title: str, path: str) -> str:
    haystack = f"{path} {title}".lower()
    if "work instruction" in haystack or re.search(r"\bwi-\d", haystack):
        return "work_instruction"
    if "manual" in haystack:
        return "quality_manual"
    if "procedure" in haystack or "sop-" in haystack:
        return "procedure"
    if "form" in haystack:
        return "form"
    return "article"


def human_document_title(title: str, document_code: str) -> str:
    stem = Path(title).stem
    if document_code:
        stem = re.sub(re.escape(document_code), "", stem, flags=re.IGNORECASE)
    stem = re.sub(r"\brev(?:ision)?\.?\s*\d+\b", "", stem, flags=re.IGNORECASE)
    stem = re.sub(r"[_-]+", " ", stem)
    return clean_label(stem).strip(" -") or document_code or title


def build_draft_summary(*, title: str, code: str, category: str) -> str:
    label = f"{code} - {title}" if code else title
    return (
        f"Draft Wiki card for {label}. The source has been inventoried from the "
        f"{category} collection; employee-facing details still require review before approval."
    )


def sync_internal_wiki_links(repository: WikiRepository, html: str) -> WikiSyncResult:
    source = repository.upsert_source(
        source_key="boone-internal-wiki",
        source_type="website",
        title="Boone internal wiki SweetProcess links",
        root_url=INTERNAL_WIKI_URL,
    )
    run_id = repository.start_sync_run(source.id)
    try:
        links = parse_internal_wiki_links(html)
        repository.replace_source_links(source_id=source.id, link_type="legacy", links=links)
        repository.finish_sync_run(
            run_id=run_id,
            source_id=source.id,
            status="succeeded",
            scanned_count=len(links),
            changed_count=len(links),
        )
        return WikiSyncResult(source.source_key, len(links), len(links), "succeeded")
    except Exception as exc:
        repository.finish_sync_run(
            run_id=run_id,
            source_id=source.id,
            status="failed",
            scanned_count=0,
            changed_count=0,
            error_message=str(exc),
        )
        raise


def sync_drive_inventory(
    repository: WikiRepository,
    items: Iterable[DriveInventoryItem],
) -> WikiSyncResult:
    source = repository.upsert_source(
        source_key="google-drive-iso",
        source_type="google_drive_inventory",
        title="Google Drive ISO and Work Instructions inventory",
        root_url="",
    )
    run_id = repository.start_sync_run(source.id)
    scanned_count = 0
    changed_count = 0
    try:
        for item in items:
            scanned_count += 1
            document = drive_item_to_document(item)
            document_id = repository.upsert_document(source.id, document)
            if document.source_url:
                repository.replace_document_links(
                    document_id=document_id,
                    source_id=source.id,
                    links=[
                        WikiLinkRecord(
                            label="Controlled source document",
                            url=document.source_url,
                            link_type="source",
                            visible_to="admin",
                        )
                    ],
                )
            changed_count += 1
        repository.finish_sync_run(
            run_id=run_id,
            source_id=source.id,
            status="succeeded",
            scanned_count=scanned_count,
            changed_count=changed_count,
        )
        return WikiSyncResult(source.source_key, scanned_count, changed_count, "succeeded")
    except Exception as exc:
        repository.finish_sync_run(
            run_id=run_id,
            source_id=source.id,
            status="failed",
            scanned_count=scanned_count,
            changed_count=changed_count,
            error_message=str(exc),
        )
        raise


def repository_from_settings(settings: AppSettings) -> WikiRepository:
    if not settings.mysql_host or not settings.mysql_user or not settings.mysql_password:
        raise RuntimeError("MySQL settings are required for Wiki sync")
    return WikiRepository(lambda: create_connection(settings))


def fetch_internal_wiki_html(url: str = INTERNAL_WIKI_URL) -> str:
    response = httpx.get(url, timeout=20, follow_redirects=True)
    response.raise_for_status()
    return response.text


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync Retriever Wiki sources.")
    parser.add_argument("--internal-wiki", action="store_true", help="Sync SweetProcess links.")
    parser.add_argument(
        "--drive-inventory",
        type=Path,
        help="Sync a Google Drive inventory export as JSON or CSV.",
    )
    args = parser.parse_args()
    if not args.internal_wiki and not args.drive_inventory:
        parser.error("select --internal-wiki and/or --drive-inventory")

    repository = repository_from_settings(get_settings())
    results: list[WikiSyncResult] = []
    if args.internal_wiki:
        results.append(sync_internal_wiki_links(repository, fetch_internal_wiki_html()))
    if args.drive_inventory:
        results.append(sync_drive_inventory(repository, load_drive_inventory(args.drive_inventory)))

    for result in results:
        print(
            f"{result.source_key}: {result.status}, "
            f"scanned={result.scanned_count}, changed={result.changed_count}"
        )


if __name__ == "__main__":
    main()
