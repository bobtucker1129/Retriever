from __future__ import annotations

import json

from app.db.repositories.wiki import WikiSourceRecord
from app.wiki.sync import (
    DriveInventoryItem,
    drive_item_to_document,
    load_drive_inventory,
    parse_internal_wiki_links,
    sync_drive_inventory,
)


def test_parse_internal_wiki_links_dedupes_sweetprocess_links() -> None:
    html = """
    <a href="https://www.sweetprocess.com/procedures/abc123/example-procedure/">Example Procedure</a>
    <a href="https://www.sweetprocess.com/procedures/abc123/example-procedure/">Duplicate</a>
    <a href="https://example.com/not-used">Ignore me</a>
    """

    links = parse_internal_wiki_links(html)

    assert len(links) == 1
    assert links[0].label == "Example Procedure"
    assert links[0].link_type == "legacy"
    assert links[0].visible_to == "employee"


def test_parse_internal_wiki_links_uses_url_when_label_is_generic() -> None:
    html = """
    <a href="https://www.sweetprocess.com/procedures/132kYCJ9J0/processing-cal-poly-dsf-am/">LINK</a>
    """

    links = parse_internal_wiki_links(html)

    assert len(links) == 1
    assert links[0].label == "Processing Cal Poly DSF"


def test_drive_item_to_document_hides_raw_source_from_employees() -> None:
    document = drive_item_to_document(
        DriveInventoryItem(
            source_document_id="drive-file-1",
            title="WI-022 Rev02 - Secure Mailing.docx",
            url="https://drive.google.com/file/d/drive-file-1/view",
            path="Final Boone/Level 3 Work Instructions",
        )
    )

    assert document.slug == "wi-022-secure-mailing"
    assert document.document_code == "WI-022"
    assert document.document_type == "work_instruction"
    assert document.category == "Work Instructions"
    assert document.summary_status == "draft"
    assert document.raw_source_visible_to == "admin"
    assert "require review" in document.summary


def test_load_drive_inventory_accepts_json_files_key(tmp_path) -> None:
    path = tmp_path / "drive.json"
    path.write_text(
        json.dumps(
            {
                "files": [
                    {
                        "id": "file-1",
                        "name": "M-001 Quality Manual.pdf",
                        "webViewLink": "https://drive.example/file-1",
                        "modifiedTime": "2026-05-18T12:00:00Z",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    items = load_drive_inventory(path)

    assert len(items) == 1
    assert items[0].source_document_id == "file-1"
    assert items[0].title == "M-001 Quality Manual.pdf"
    assert items[0].modified_at is not None


def test_sync_drive_inventory_upserts_documents_and_admin_source_links() -> None:
    class Repo:
        def __init__(self):
            self.documents = []
            self.document_links = []
            self.finished = None

        def upsert_source(self, **kwargs):
            return WikiSourceRecord(id=12, last_synced_at=None, **kwargs)

        def start_sync_run(self, source_id):
            assert source_id == 12
            return 99

        def upsert_document(self, source_id, document):
            assert source_id == 12
            self.documents.append(document)
            return 44

        def replace_document_links(self, *, document_id, source_id, links):
            self.document_links.extend(links)

        def finish_sync_run(self, **kwargs):
            self.finished = kwargs

    repo = Repo()

    result = sync_drive_inventory(
        repo,  # type: ignore[arg-type]
        [
            DriveInventoryItem(
                source_document_id="file-1",
                title="SOP-023 Secure Data Control.pdf",
                url="https://drive.example/file-1",
                path="Final Boone/Level 2 Procedures",
            )
        ],
    )

    assert result.status == "succeeded"
    assert result.scanned_count == 1
    assert repo.documents[0].document_code == "SOP-023"
    assert repo.document_links[0].visible_to == "admin"
    assert repo.finished["status"] == "succeeded"
