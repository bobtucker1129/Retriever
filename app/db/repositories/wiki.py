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


@dataclass(frozen=True)
class WikiSourceRecord:
    id: int
    source_key: str
    source_type: str
    title: str
    root_url: str
    last_synced_at: Optional[datetime] = None


@dataclass(frozen=True)
class WikiDocumentUpsert:
    slug: str
    title: str
    document_code: str
    document_type: str
    category: str
    summary: str
    summary_status: str = "draft"
    source_document_id: str = ""
    source_url: str = ""
    source_modified_at: Optional[datetime] = None
    source_checksum: str = ""
    audience: str = "employee"
    raw_source_visible_to: str = "admin"


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

    def list_source_links(
        self,
        source_key: str,
        link_type: str = "legacy",
        include_admin: bool = False,
    ) -> list[WikiLinkRecord]:
        visibility = ("employee", "admin") if include_admin else ("employee",)
        placeholders = ", ".join(["%s"] * len(visibility))
        conn = self._connection_factory()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(
                f"""
                SELECT l.label, l.url, l.link_type, l.visible_to
                FROM wiki_links l
                INNER JOIN wiki_sources s ON s.id = l.source_id
                WHERE s.source_key = %s
                  AND l.document_id IS NULL
                  AND l.link_type = %s
                  AND l.visible_to IN ({placeholders})
                ORDER BY l.label ASC
                """,
                (source_key, link_type, *visibility),
            )
            rows = cursor.fetchall()
        finally:
            cursor.close()
            conn.close()
        return [self._link_from_row(row) for row in rows]

    def upsert_source(
        self,
        *,
        source_key: str,
        source_type: str,
        title: str,
        root_url: str = "",
    ) -> WikiSourceRecord:
        conn = self._connection_factory()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(
                """
                INSERT INTO wiki_sources (source_key, source_type, title, root_url)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    source_type = VALUES(source_type),
                    title = VALUES(title),
                    root_url = VALUES(root_url)
                """,
                (source_key, source_type, title, root_url),
            )
            cursor.execute(
                """
                SELECT id, source_key, source_type, title, root_url, last_synced_at
                FROM wiki_sources
                WHERE source_key = %s
                LIMIT 1
                """,
                (source_key,),
            )
            row = cursor.fetchone()
        finally:
            cursor.close()
            conn.close()
        if not row:
            raise RuntimeError(f"Wiki source was not created: {source_key}")
        return self._source_from_row(row)

    def start_sync_run(self, source_id: int) -> int:
        conn = self._connection_factory()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(
                """
                INSERT INTO wiki_sync_runs (source_id, status)
                VALUES (%s, 'running')
                """,
                (source_id,),
            )
            cursor.execute("SELECT LAST_INSERT_ID() AS id")
            row = cursor.fetchone()
        finally:
            cursor.close()
            conn.close()
        return int((row or {}).get("id") or 0)

    def finish_sync_run(
        self,
        *,
        run_id: int,
        source_id: int,
        status: str,
        scanned_count: int,
        changed_count: int,
        error_message: str = "",
    ) -> None:
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                UPDATE wiki_sync_runs
                SET status = %s,
                    finished_at = CURRENT_TIMESTAMP,
                    scanned_count = %s,
                    changed_count = %s,
                    error_message = NULLIF(%s, '')
                WHERE id = %s
                """,
                (status, scanned_count, changed_count, error_message, run_id),
            )
            if status == "succeeded":
                cursor.execute(
                    """
                    UPDATE wiki_sources
                    SET last_synced_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                    """,
                    (source_id,),
                )
        finally:
            cursor.close()
            conn.close()

    def upsert_document(self, source_id: int, document: WikiDocumentUpsert) -> int:
        conn = self._connection_factory()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(
                """
                INSERT INTO wiki_documents (
                    source_id, source_document_id, slug, title, document_code,
                    document_type, category, summary_status, summary, audience,
                    raw_source_visible_to, source_url, source_modified_at,
                    source_checksum, last_indexed_at
                )
                VALUES (%s, NULLIF(%s, ''), %s, %s, NULLIF(%s, ''), %s, %s, %s, %s,
                        %s, %s, NULLIF(%s, ''), %s, NULLIF(%s, ''), CURRENT_TIMESTAMP)
                ON DUPLICATE KEY UPDATE
                    source_id = VALUES(source_id),
                    source_document_id = VALUES(source_document_id),
                    title = VALUES(title),
                    document_code = VALUES(document_code),
                    document_type = VALUES(document_type),
                    category = VALUES(category),
                    summary_status = VALUES(summary_status),
                    summary = VALUES(summary),
                    audience = VALUES(audience),
                    raw_source_visible_to = VALUES(raw_source_visible_to),
                    source_url = VALUES(source_url),
                    source_modified_at = VALUES(source_modified_at),
                    source_checksum = VALUES(source_checksum),
                    last_indexed_at = CURRENT_TIMESTAMP
                """,
                (
                    source_id,
                    document.source_document_id,
                    document.slug,
                    document.title,
                    document.document_code,
                    document.document_type,
                    document.category,
                    document.summary_status,
                    document.summary,
                    document.audience,
                    document.raw_source_visible_to,
                    document.source_url,
                    document.source_modified_at,
                    document.source_checksum,
                ),
            )
            cursor.execute(
                "SELECT id FROM wiki_documents WHERE slug = %s LIMIT 1",
                (document.slug,),
            )
            row = cursor.fetchone()
        finally:
            cursor.close()
            conn.close()
        if not row:
            raise RuntimeError(f"Wiki document was not created: {document.slug}")
        return int(row["id"])

    def replace_document_links(
        self,
        *,
        document_id: int,
        source_id: int,
        links: list[WikiLinkRecord],
    ) -> None:
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                DELETE FROM wiki_links
                WHERE document_id = %s
                  AND source_id = %s
                """,
                (document_id, source_id),
            )
            for link in links:
                cursor.execute(
                    """
                    INSERT INTO wiki_links (document_id, source_id, label, url, link_type, visible_to)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (document_id, source_id, link.label, link.url, link.link_type, link.visible_to),
                )
        finally:
            cursor.close()
            conn.close()

    def replace_source_links(
        self,
        *,
        source_id: int,
        link_type: str,
        links: list[WikiLinkRecord],
    ) -> None:
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                DELETE FROM wiki_links
                WHERE source_id = %s
                  AND document_id IS NULL
                  AND link_type = %s
                """,
                (source_id, link_type),
            )
            for link in links:
                cursor.execute(
                    """
                    INSERT INTO wiki_links (source_id, label, url, link_type, visible_to)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (source_id, link.label, link.url, link.link_type, link.visible_to),
                )
        finally:
            cursor.close()
            conn.close()

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

    @staticmethod
    def _source_from_row(row: dict) -> WikiSourceRecord:
        return WikiSourceRecord(
            id=int(row["id"]),
            source_key=str(row.get("source_key") or ""),
            source_type=str(row.get("source_type") or ""),
            title=str(row.get("title") or ""),
            root_url=str(row.get("root_url") or ""),
            last_synced_at=row.get("last_synced_at"),
        )
