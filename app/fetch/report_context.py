"""Build lightweight BooneOps report context from recent Fetch assistant text."""

from __future__ import annotations

from datetime import datetime, timezone
from html.parser import HTMLParser
import re
from typing import Any, Sequence

from app.db.repositories.fetch import FetchMessageRecord


_TABLE_ROW_START_RE = re.compile(r"^(?:\d{4,}|[A-Z]{2,}[-\s]?\d{3,})$", re.IGNORECASE)


class _TableTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self._table_depth = 0
        self._current_rows: list[list[str]] | None = None
        self._current_row: list[str] | None = None
        self._current_cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        low = tag.lower()
        if low == "table":
            self._table_depth += 1
            if self._table_depth == 1:
                self._current_rows = []
            return
        if self._table_depth < 1:
            return
        if low == "tr":
            self._current_row = []
        elif low in {"td", "th"}:
            self._current_cell = []

    def handle_data(self, data: str) -> None:
        if self._current_cell is not None:
            self._current_cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        low = tag.lower()
        if self._table_depth < 1:
            return
        if low in {"td", "th"} and self._current_cell is not None:
            text = re.sub(r"\s+", " ", "".join(self._current_cell)).strip()
            if self._current_row is not None:
                self._current_row.append(text)
            self._current_cell = None
        elif low == "tr" and self._current_row is not None:
            if any(cell for cell in self._current_row) and self._current_rows is not None:
                self._current_rows.append(self._current_row)
            self._current_row = None
        elif low == "table":
            if self._table_depth == 1 and self._current_rows:
                self.tables.append(self._current_rows)
            self._current_rows = None
            self._current_row = None
            self._current_cell = None
            self._table_depth -= 1


def _clean_lines(text: str) -> list[str]:
    return [line.strip() for line in (text or "").splitlines() if line.strip()]


def _sanitize_header(value: str, fallback: str) -> str:
    cleaned = re.sub(r"\s+", " ", (value or "").replace("*", " ")).strip()
    return cleaned[:80] or fallback


def _base_context(
    *,
    conversation_id: str,
    request_id: str,
    data_label: str,
    table_data: list[dict[str, Any]],
    export_columns: list[dict[str, str]],
    export_rows: list[dict[str, str]],
) -> dict[str, Any]:
    return {
        "version": 1,
        "sourceType": "prior-message-extracted",
        "conversationId": conversation_id,
        "requestId": request_id,
        "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "reportSpec": {
            "sourceType": "printsmith",
            "title": "BooneOps Report",
            "subtitle": "",
            "chartType": "bar",
            "dataLabel": data_label,
            "footerText": "Source: Fetch prior answer",
            "sql": "",
            "usePriorData": True,
            "sourceSummary": {},
            "scheduleSpec": None,
        },
        "labels": [row["label"] for row in table_data],
        "data": [row["value"] for row in table_data],
        "tableData": table_data,
        "exportColumns": export_columns,
        "exportRows": export_rows,
        "sourceSummary": {},
        "queryMeta": {
            "rowCount": len(export_rows),
            "returnedRows": len(export_rows),
            "executionMs": 0,
        },
        "artifact": None,
    }


def _markdown_table_context(
    *,
    text: str,
    conversation_id: str,
    request_id: str,
) -> dict[str, Any] | None:
    lines = _clean_lines(text)
    table_lines = [line for line in lines if line.startswith("|") and line.endswith("|")]
    if len(table_lines) < 3:
        return None
    headers = [cell.strip() for cell in table_lines[0].split("|") if cell.strip()]
    if len(headers) < 2:
        return None
    if not re.match(r"^\|[\s:\-]+\|", table_lines[1]):
        return None

    table_data: list[dict[str, Any]] = []
    export_rows: list[dict[str, str]] = []
    for row_line in table_lines[2:]:
        cells = [cell.strip() for cell in row_line.split("|") if cell.strip()]
        if len(cells) < 2:
            continue
        label = cells[0].replace("**", "").strip()
        raw_value = re.sub(r"[$,*]", "", cells[-1]).strip()
        try:
            value = float(raw_value)
        except ValueError:
            value = 1
        if not label:
            continue
        table_data.append({"label": label, "value": value})
        export_rows.append({f"col{i}": cells[i] if i < len(cells) else "" for i in range(len(headers))})

    if not export_rows:
        return None

    export_columns = [
        {"key": f"col{i}", "header": _sanitize_header(header, f"Column {i + 1}"), "kind": "string"}
        for i, header in enumerate(headers)
    ]
    return _base_context(
        conversation_id=conversation_id,
        request_id=request_id,
        data_label=_sanitize_header(headers[-1], "Value"),
        table_data=table_data,
        export_columns=export_columns,
        export_rows=export_rows,
    )


def _html_table_context(
    *,
    text: str,
    conversation_id: str,
    request_id: str,
) -> dict[str, Any] | None:
    if "<table" not in (text or "").lower():
        return None
    parser = _TableTextParser()
    parser.feed(text)
    for rows in parser.tables:
        if len(rows) < 2:
            continue
        headers = [_sanitize_header(cell, f"Column {i + 1}") for i, cell in enumerate(rows[0])]
        if len(headers) < 2:
            continue
        data_rows = [row for row in rows[1:] if any(cell.strip() for cell in row)]
        if not data_rows:
            continue

        export_rows: list[dict[str, str]] = []
        table_data: list[dict[str, Any]] = []
        for cells in data_rows:
            padded = cells + [""] * max(0, len(headers) - len(cells))
            export_rows.append({f"col{i}": padded[i] if i < len(padded) else "" for i in range(len(headers))})
            label = (padded[0] if padded else "").strip()
            if not label:
                continue
            raw_value = re.sub(r"[$,*]", "", (padded[-1] if padded else "")).strip()
            try:
                value = float(raw_value)
            except ValueError:
                value = 1
            table_data.append({"label": label, "value": value})

        if not export_rows:
            continue
        if not table_data:
            table_data = [{"label": "Rows", "value": len(export_rows)}]

        export_columns = [
            {"key": f"col{i}", "header": header, "kind": "string"}
            for i, header in enumerate(headers)
        ]
        return _base_context(
            conversation_id=conversation_id,
            request_id=request_id,
            data_label=_sanitize_header(headers[-1], "Value"),
            table_data=table_data,
            export_columns=export_columns,
            export_rows=export_rows,
        )
    return None


def _line_table_header(lines: list[str], start: int) -> tuple[int, list[str]] | None:
    window = [line.lower() for line in lines[start : start + 6]]
    invoice_index = next((i for i, line in enumerate(window) if re.match(r"^invoice\b", line)), -1)
    if invoice_index < 0:
        return None
    due_index = next((i for i, line in enumerate(window) if re.match(r"^due\b", line)), -1)
    if due_index <= invoice_index:
        return None
    headers = lines[start + invoice_index : start + due_index + 1]
    if len(headers) < 2 or len(headers) > 6:
        return None
    return invoice_index, headers


def _line_oriented_table_context(
    *,
    text: str,
    conversation_id: str,
    request_id: str,
) -> dict[str, Any] | None:
    lines = _clean_lines(text)
    for index in range(len(lines)):
        header = _line_table_header(lines, index)
        if header is None:
            continue
        offset, headers = header
        width = len(headers)
        row_start = index + offset + width
        rows: list[list[str]] = []
        pos = row_start
        while pos + width - 1 < len(lines):
            cells = lines[pos : pos + width]
            if _TABLE_ROW_START_RE.match(cells[0]) is None:
                break
            rows.append(cells)
            pos += width
        if not rows:
            continue

        due_index = next((i for i, h in enumerate(headers) if re.match(r"^due\b", h, re.IGNORECASE)), -1)
        due_counts: dict[str, int] = {}
        export_rows: list[dict[str, str]] = []
        for cells in rows:
            export_rows.append({f"col{i}": cells[i] if i < len(cells) else "" for i in range(width)})
            due = cells[due_index] if 0 <= due_index < len(cells) else "Unspecified"
            due_counts[due] = due_counts.get(due, 0) + 1

        table_data = [{"label": label, "value": value} for label, value in due_counts.items()]
        export_columns = [
            {"key": f"col{i}", "header": _sanitize_header(header, f"Column {i + 1}"), "kind": "string"}
            for i, header in enumerate(headers)
        ]
        return _base_context(
            conversation_id=conversation_id,
            request_id=request_id,
            data_label="Count",
            table_data=table_data,
            export_columns=export_columns,
            export_rows=export_rows,
        )
    return None


def report_context_from_prior_assistant_table(
    records: Sequence[FetchMessageRecord],
    *,
    conversation_id: str,
    request_id: str,
) -> dict[str, Any] | None:
    """Extract a minimal exportable report context from the latest assistant table."""
    for rec in reversed(records):
        if rec.role != "assistant":
            continue
        state = (rec.context_state or "").strip().lower()
        if state in {"stub", "booneops_error", "error"}:
            continue
        text = rec.content or ""
        context = _markdown_table_context(
            text=text,
            conversation_id=conversation_id,
            request_id=request_id,
        )
        if context is not None:
            return context
        context = _html_table_context(
            text=text,
            conversation_id=conversation_id,
            request_id=request_id,
        )
        if context is not None:
            return context
        context = _line_oriented_table_context(
            text=text,
            conversation_id=conversation_id,
            request_id=request_id,
        )
        if context is not None:
            return context
    return None
