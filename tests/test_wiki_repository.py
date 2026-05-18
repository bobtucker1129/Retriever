from __future__ import annotations

from app.db.repositories.wiki import WikiDocumentUpsert, WikiLinkRecord, WikiRepository


def test_wiki_slugify_normalizes_work_instruction_titles() -> None:
    assert WikiRepository.slugify("WI-022 Rev02 - secure mailing.docx") == (
        "wi-022-rev02-secure-mailing-docx"
    )


def test_wiki_repository_lists_documents_from_rows() -> None:
    class Cursor:
        def __init__(self):
            self.statement = ""
            self.params = ()

        def execute(self, statement, params=()):
            self.statement = statement
            self.params = params

        def fetchall(self):
            return [
                {
                    "id": 1,
                    "slug": "wi-022-secure-mailing",
                    "title": "Secure Mailing",
                    "document_code": "WI-022",
                    "document_type": "work_instruction",
                    "category": "Work Instructions",
                    "summary_status": "reviewed",
                    "summary": "Secure mailing summary.",
                    "source_url": "",
                    "source_modified_at": None,
                    "last_indexed_at": None,
                }
            ]

        def fetchone(self):
            return None

        def close(self):
            pass

    class Connection:
        def __init__(self):
            self.cursor_obj = Cursor()

        def cursor(self, dictionary=False):
            return self.cursor_obj

        def close(self):
            pass

    conn = Connection()
    repo = WikiRepository(lambda: conn)

    documents = repo.list_documents(category="Work Instructions")

    assert len(documents) == 1
    assert documents[0].slug == "wi-022-secure-mailing"
    assert documents[0].summary_status == "reviewed"
    assert conn.cursor_obj.params == ("Work Instructions",)


def test_wiki_repository_upserts_document_and_admin_source_link() -> None:
    class Cursor:
        def __init__(self):
            self.statements = []
            self.params = []

        def execute(self, statement, params=()):
            self.statements.append(statement)
            self.params.append(params)

        def fetchall(self):
            return []

        def fetchone(self):
            return {"id": 42}

        def close(self):
            pass

    class Connection:
        def __init__(self):
            self.cursor_obj = Cursor()

        def cursor(self, dictionary=False):
            return self.cursor_obj

        def close(self):
            pass

    conn = Connection()
    repo = WikiRepository(lambda: conn)

    document_id = repo.upsert_document(
        7,
        WikiDocumentUpsert(
            slug="wi-022-secure-mailing",
            title="Secure Mailing",
            document_code="WI-022",
            document_type="work_instruction",
            category="Work Instructions",
            summary="Draft summary.",
            source_url="https://drive.example/wi-022",
        ),
    )
    repo.replace_document_links(
        document_id=document_id,
        source_id=7,
        links=[
            WikiLinkRecord(
                label="Controlled source document",
                url="https://drive.example/wi-022",
                link_type="source",
                visible_to="admin",
            )
        ],
    )

    assert document_id == 42
    assert any("ON DUPLICATE KEY UPDATE" in statement for statement in conn.cursor_obj.statements)
    assert conn.cursor_obj.params[-1] == (
        42,
        7,
        "Controlled source document",
        "https://drive.example/wi-022",
        "source",
        "admin",
    )


def test_wiki_repository_lists_source_links_by_key() -> None:
    class Cursor:
        def __init__(self):
            self.params = ()

        def execute(self, statement, params=()):
            self.params = params

        def fetchall(self):
            return [
                {
                    "label": "Processing Cal Poly DSF",
                    "url": "https://www.sweetprocess.com/procedures/abc/example/",
                    "link_type": "legacy",
                    "visible_to": "employee",
                }
            ]

        def fetchone(self):
            return None

        def close(self):
            pass

    class Connection:
        def __init__(self):
            self.cursor_obj = Cursor()

        def cursor(self, dictionary=False):
            return self.cursor_obj

        def close(self):
            pass

    conn = Connection()
    repo = WikiRepository(lambda: conn)

    links = repo.list_source_links("boone-internal-wiki")

    assert len(links) == 1
    assert links[0].label == "Processing Cal Poly DSF"
    assert conn.cursor_obj.params == ("boone-internal-wiki", "legacy", "employee")
