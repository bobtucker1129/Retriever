from __future__ import annotations

from io import BytesIO
import zipfile

from starlette.datastructures import UploadFile

from app.config import AppSettings
from app.fetch.uploads import broker_upload_context, save_fetch_uploads, upload_metadata_for_message


def _xlsx_bytes() -> bytes:
    out = BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        zf.writestr(
            "xl/sharedStrings.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
            <sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <si><t>Customer</t></si><si><t>Orders</t></si><si><t>Boone</t></si>
            </sst>""",
        )
        zf.writestr(
            "xl/worksheets/sheet1.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
            <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <sheetData>
                <row><c t="s"><v>0</v></c><c t="s"><v>1</v></c></row>
                <row><c t="s"><v>2</v></c><c><v>12</v></c></row>
              </sheetData>
            </worksheet>""",
        )
    return out.getvalue()


async def test_save_fetch_uploads_extracts_csv_preview(tmp_path) -> None:
    settings = AppSettings(fetch_uploads_enabled=True, retriever_upload_dir=tmp_path)
    upload = UploadFile(filename="orders.csv", file=BytesIO(b"Customer,Orders\nBoone,12\n"))

    saved = await save_fetch_uploads(
        settings,
        user_id=7,
        conversation_id="conv-1",
        files=[upload],
    )

    assert saved[0]["filename"] == "orders.csv"
    assert "Boone" in saved[0]["textPreview"]
    assert "diskPath" in saved[0]
    message_metadata = upload_metadata_for_message(saved)
    assert message_metadata["artifacts"][0]["filename"] == "orders.csv"
    assert "diskPath" not in message_metadata["uploads"][0]
    assert broker_upload_context(saved)[0]["textPreview"] == saved[0]["textPreview"]


async def test_save_fetch_uploads_extracts_xlsx_preview(tmp_path) -> None:
    settings = AppSettings(fetch_uploads_enabled=True, retriever_upload_dir=tmp_path)
    upload = UploadFile(filename="orders.xlsx", file=BytesIO(_xlsx_bytes()))

    saved = await save_fetch_uploads(
        settings,
        user_id=7,
        conversation_id="conv-1",
        files=[upload],
    )

    assert saved[0]["kind"] == "xlsx"
    assert "Customer,Orders" in saved[0]["textPreview"]
    assert "Boone,12" in saved[0]["textPreview"]


async def test_save_fetch_uploads_extracts_pdf_preview(monkeypatch, tmp_path) -> None:
    class FakePage:
        def extract_text(self) -> str:
            return "Boone PDF upload text"

    class FakePdfReader:
        def __init__(self, _stream: BytesIO) -> None:
            self.pages = [FakePage()]

    monkeypatch.setattr("app.fetch.uploads.PdfReader", FakePdfReader)
    settings = AppSettings(fetch_uploads_enabled=True, retriever_upload_dir=tmp_path)
    upload = UploadFile(filename="proof.pdf", file=BytesIO(b"%PDF-pretend"))

    saved = await save_fetch_uploads(
        settings,
        user_id=7,
        conversation_id="conv-1",
        files=[upload],
    )

    assert saved[0]["kind"] == "pdf"
    assert saved[0]["textPreview"] == "Boone PDF upload text"
