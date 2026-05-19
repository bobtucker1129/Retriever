"""Fetch upload intake: private disk storage plus small text previews for broker context."""

from __future__ import annotations

import csv
import re
import uuid
import zipfile
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any, Optional
from xml.etree import ElementTree

from fastapi import UploadFile
from PyPDF2 import PdfReader

from app.config import AppSettings

MAX_FETCH_UPLOAD_FILES = 4
MAX_FETCH_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_FETCH_UPLOAD_PREVIEW_CHARS = 12_000

_SAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._ -]+")
_TEXT_EXTENSIONS = {".csv", ".txt", ".tsv", ".md", ".json", ".log"}
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff"}
_EXCEL_EXTENSIONS = {".xlsx"}
_ALLOWED_EXTENSIONS = _TEXT_EXTENSIONS | _IMAGE_EXTENSIONS | _EXCEL_EXTENSIONS | {".pdf"}


class FetchUploadError(ValueError):
    """The user supplied an upload Fetch should not accept."""


def _safe_upload_filename(raw: str) -> str:
    name = Path(raw or "attachment").name.strip().replace("\\", "_")
    name = _SAFE_FILENAME_CHARS.sub("_", name)
    name = " ".join(name.split())
    if not name or name in {".", ".."}:
        return "attachment"
    return name[:160]


def _decode_text(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _trim_preview(text: str) -> str:
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if len(cleaned) <= MAX_FETCH_UPLOAD_PREVIEW_CHARS:
        return cleaned
    return cleaned[:MAX_FETCH_UPLOAD_PREVIEW_CHARS].rstrip() + "\n[preview trimmed]"


def _csv_preview(text: str) -> str:
    sample = text[:MAX_FETCH_UPLOAD_PREVIEW_CHARS * 2]
    dialect = csv.excel
    try:
        dialect = csv.Sniffer().sniff(sample)
    except csv.Error:
        pass
    out = StringIO()
    writer = csv.writer(out)
    reader = csv.reader(StringIO(sample), dialect)
    for idx, row in enumerate(reader):
        if idx >= 30:
            writer.writerow(["[preview trimmed]"])
            break
        writer.writerow(row[:20])
    return _trim_preview(out.getvalue())


def _xlsx_shared_strings(zf: zipfile.ZipFile) -> list[str]:
    try:
        raw = zf.read("xl/sharedStrings.xml")
    except KeyError:
        return []
    root = ElementTree.fromstring(raw)
    ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    strings: list[str] = []
    for si in root.findall("x:si", ns):
        parts = [node.text or "" for node in si.findall(".//x:t", ns)]
        strings.append("".join(parts))
    return strings


def _xlsx_preview(data: bytes) -> str:
    rows: list[list[str]] = []
    try:
        with zipfile.ZipFile(BytesIO(data)) as zf:
            shared = _xlsx_shared_strings(zf)
            sheet_names = sorted(
                name for name in zf.namelist() if name.startswith("xl/worksheets/sheet")
            )
            if not sheet_names:
                return ""
            root = ElementTree.fromstring(zf.read(sheet_names[0]))
    except (KeyError, zipfile.BadZipFile, ElementTree.ParseError):
        return ""

    ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    for row in root.findall(".//x:sheetData/x:row", ns)[:30]:
        values: list[str] = []
        for cell in row.findall("x:c", ns)[:20]:
            raw_value = cell.findtext("x:v", default="", namespaces=ns)
            if cell.get("t") == "s":
                try:
                    values.append(shared[int(raw_value)])
                except (ValueError, IndexError):
                    values.append(raw_value)
            else:
                values.append(raw_value)
        rows.append(values)
    out = StringIO()
    writer = csv.writer(out)
    writer.writerows(rows)
    return _trim_preview(out.getvalue())


def _pdf_preview(data: bytes) -> str:
    try:
        reader = PdfReader(BytesIO(data))
    except Exception:
        return ""

    pages: list[str] = []
    for page in reader.pages[:10]:
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        if text.strip():
            pages.append(text.strip())
        if len("\n\n".join(pages)) >= MAX_FETCH_UPLOAD_PREVIEW_CHARS:
            break
    return _trim_preview("\n\n".join(pages))


def _preview_for_upload(filename: str, data: bytes) -> tuple[str, Optional[str]]:
    ext = Path(filename).suffix.lower()
    if ext == ".csv":
        return _csv_preview(_decode_text(data)), "csv"
    if ext in {".txt", ".tsv", ".md", ".json", ".log"}:
        return _trim_preview(_decode_text(data)), "text"
    if ext == ".xlsx":
        return _xlsx_preview(data), "xlsx"
    if ext in _IMAGE_EXTENSIONS:
        return "", "image"
    if ext == ".pdf":
        return _pdf_preview(data), "pdf"
    return "", None


async def save_fetch_uploads(
    settings: AppSettings,
    *,
    user_id: int,
    conversation_id: str,
    files: Optional[list[UploadFile]],
) -> list[dict[str, Any]]:
    if not files:
        return []
    real_files = [file for file in files if file and file.filename]
    if not real_files:
        return []
    if len(real_files) > MAX_FETCH_UPLOAD_FILES:
        raise FetchUploadError(f"Attach {MAX_FETCH_UPLOAD_FILES} files or fewer at a time.")

    base_dir = settings.retriever_upload_dir / "fetch" / str(user_id) / conversation_id
    base_dir.mkdir(parents=True, exist_ok=True)

    saved: list[dict[str, Any]] = []
    total = 0
    for upload in real_files:
        filename = _safe_upload_filename(upload.filename or "attachment")
        ext = Path(filename).suffix.lower()
        if ext not in _ALLOWED_EXTENSIONS:
            raise FetchUploadError(f"{filename} is not an allowed upload type.")
        data = await upload.read()
        total += len(data)
        if total > MAX_FETCH_UPLOAD_BYTES:
            raise FetchUploadError("Uploads must be 10 MB or smaller per message.")
        upload_id = str(uuid.uuid4())
        disk_name = f"{upload_id}-{filename}"
        disk_path = base_dir / disk_name
        disk_path.write_bytes(data)
        preview, kind = _preview_for_upload(filename, data)
        saved.append(
            {
                "uploadId": upload_id,
                "filename": filename,
                "description": f"{kind or 'file'} upload, {len(data)} bytes",
                "mimeType": upload.content_type or "application/octet-stream",
                "sizeBytes": len(data),
                "kind": kind or "file",
                "diskPath": str(disk_path),
                "textPreview": preview,
            }
        )
    return saved


def upload_metadata_for_message(saved_uploads: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if not saved_uploads:
        return None
    artifacts = [
        {
            "filename": item["filename"],
            "description": item["description"],
            "uploadId": item["uploadId"],
        }
        for item in saved_uploads
    ]
    uploads = [
        {key: value for key, value in item.items() if key != "diskPath"}
        for item in saved_uploads
    ]
    return {"artifacts": artifacts, "uploads": uploads}


def broker_upload_context(saved_uploads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in saved_uploads:
        out.append(
            {
                "uploadId": item["uploadId"],
                "filename": item["filename"],
                "mimeType": item["mimeType"],
                "sizeBytes": item["sizeBytes"],
                "kind": item["kind"],
                "textPreview": item.get("textPreview") or "",
            }
        )
    return out
