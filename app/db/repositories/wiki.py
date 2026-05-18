"""Wiki catalog repository."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional, Protocol


class CursorLike(Protocol):
    def execute(self, operation: str, params: tuple = ()) -> None:
        ...

    def fetchall(self):
        ...

    def fetchone(self):
        ...

    def close(self) -> None:
        ...


class ConnectionLike(Protocol):
    def cursor(self, dictionary: bool = False) -> CursorLike:
        ...

    def close(self) -> None:
        ...


ConnectionFactory = Callable[[], ConnectionLike]


@dataclass(frozen=True)
class WikiDocumentRecord:
    id: int
    slug: str
    title: str
    document_code: str
    document_type: str
    category: str
    summary_status: str
    summary: str
    source_url: str
    source_modified_at: Optional[datetime] = None
    last_indexed_at: Optional[datetime] = None


@dataclass(frozen=True)
class WikiSectionRecord:
    slug: str
    heading: str
    section_order: int
    summary: str
    body_status: str


@dataclass(frozen=True)
class WikiLinkRecord:
    label: str
    url: str
    link_type: str
    visible_to: str


class WikiRepository:
    def __init__(self, connection_factory: ConnectionFactory):
        self._connection_factory = connection_factory

    def list_documents(
        self,
        category: Optional[str] = None,
        limit: int = 100,
    ) -> list[WikiDocumentRecord]:
        safe_limit = max(1, min(int(limit), 250))
        where = ""
        params: tuple = ()
        if category:
            where = "WHERE d.category = %s"
            params = (category,)

        conn = self._connection_factory()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(
                f"""
                SELECT d.id, d.slug, d.title, d.document_code, d.document_type,
                       d.category, d.summary_status, d.summary, d.source_url,
                       d.source_modified_at, d.last_indexed_at
                FROM wiki_documents d
                {where}
                ORDER BY FIELD(d.category, 'Work Instructions', 'Quality & ISO',
                               'Security Posture', 'Production Knowledge',
                               'Boone Basics', 'Customer & Vendor Context'),
                         d.document_code IS NULL, d.document_code, d.title
                LIMIT {safe_limit}
                """,
                params,
            )
            rows = cursor.fetchall()
        finally:
            cursor.close()
            conn.close()
        return [self._document_from_row(row) for row in rows]

    def get_document_by_slug(self, slug: str) -> Optional[WikiDocumentRecord]:
        conn = self._connection_factory()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(
                """
                SELECT d.id, d.slug, d.title, d.document_code, d.document_type,
                       d.category, d.summary_status, d.summary, d.source_url,
                       d.source_modified_at, d.last_indexed_at
                FROM wiki_documents d
                WHERE d.slug = %s
                LIMIT 1
                """,
                (slug,),
            )
            row = cursor.fetchone()
        finally:
            cursor.close()
            conn.close()
        return self._document_from_row(row) if row else None

    def list_sections(self, document_id: int) -> list[WikiSectionRecord]:
        conn = self._connection_factory()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(
                """
                SELECT slug, heading, section_order, summary, body_status
                FROM wiki_sections
                WHERE document_id = %s
                ORDER BY section_order ASC, heading ASC
                """,
                (document_id,),
            )
            rows = cursor.fetchall()
        finally:
            cursor.close()
            conn.close()
        return [self._section_from_row(row) for row in rows]

    def list_links(self, document_id: int, include_admin: bool = False) -> list[WikiLinkRecord]:
        visibility = ("employee", "admin") if include_admin else ("employee",)
        placeholders = ", ".join(["%s"] * len(visibility))
        conn = self._connection_factory()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(
                f"""
                SELECT label, url, link_type, visible_to
                FROM wiki_links
                WHERE document_id = %s
                  AND visible_to IN ({placeholders})
                ORDER BY FIELD(link_type, 'wiki', 'legacy', 'source'), label
                """,
                (document_id, *visibility),
            )
            rows = cursor.fetchall()
        finally:
            cursor.close()
            conn.close()
        return [self._link_from_row(row) for row in rows]

    @staticmethod
    def slugify(value: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
        return slug.strip("-") or "wiki-document"

    @staticmethod
    def _document_from_row(row: dict) -> WikiDocumentRecord:
        return WikiDocumentRecord(
            id=int(row["id"]),
            slug=str(row.get("slug") or ""),
            title=str(row.get("title") or ""),
            document_code=str(row.get("document_code") or ""),
            document_type=str(row.get("document_type") or "article"),
            category=str(row.get("category") or "General"),
            summary_status=str(row.get("summary_status") or "draft"),
            summary=str(row.get("summary") or ""),
            source_url=str(row.get("source_url") or ""),
            source_modified_at=row.get("source_modified_at"),
            last_indexed_at=row.get("last_indexed_at"),
        )

    @staticmethod
    def _section_from_row(row: dict) -> WikiSectionRecord:
        return WikiSectionRecord(
            slug=str(row.get("slug") or ""),
            heading=str(row.get("heading") or ""),
            section_order=int(row.get("section_order") or 0),
            summary=str(row.get("summary") or ""),
            body_status=str(row.get("body_status") or "draft"),
        )

    @staticmethod
    def _link_from_row(row: dict) -> WikiLinkRecord:
        return WikiLinkRecord(
            label=str(row.get("label") or ""),
            url=str(row.get("url") or ""),
            link_type=str(row.get("link_type") or "source"),
            visible_to=str(row.get("visible_to") or "employee"),
        )
