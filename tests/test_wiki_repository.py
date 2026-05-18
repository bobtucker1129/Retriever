from __future__ import annotations

from app.db.repositories.wiki import WikiRepository


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
