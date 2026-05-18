"""Prior Fetch table extraction for BooneOps follow-up exports."""

from __future__ import annotations

from app.db.repositories.fetch import FetchMessageRecord
from app.fetch.report_context import report_context_from_prior_assistant_table


def _assistant(content: str, *, state: str = "booneops") -> FetchMessageRecord:
    return FetchMessageRecord(
        message_id="m",
        conversation_id="c",
        user_id=1,
        role="assistant",
        content=content,
        route_key="unknown",
        context_state=state,
    )


def test_report_context_extracts_invoice_like_line_table() -> None:
    context = report_context_from_prior_assistant_table(
        [
            _assistant(
                "\n".join(
                    [
                        "Invoice",
                        "eCom Order",
                        "Items",
                        "Due",
                        "INV-10421",
                        "WO-8801",
                        "Business Cards, Envelopes",
                        "2026-05-20",
                        "INV-10435",
                        "WO-8814",
                        "Brochures (Tri-fold)",
                        "2026-05-21",
                    ]
                )
            )
        ],
        conversation_id="conv-1",
        request_id="req-1",
    )

    assert context is not None
    assert context["exportColumns"][0]["header"] == "Invoice"
    assert context["exportRows"][0]["col0"] == "INV-10421"
    assert context["exportRows"][0]["col2"] == "Business Cards, Envelopes"
    assert context["queryMeta"]["rowCount"] == 2


def test_report_context_extracts_markdown_table() -> None:
    context = report_context_from_prior_assistant_table(
        [
            _assistant(
                "| Invoice | Due |\n"
                "| --- | --- |\n"
                "| 111114 | Today |\n"
                "| 111115 | Tomorrow |"
            )
        ],
        conversation_id="conv-1",
        request_id="req-1",
    )

    assert context is not None
    assert context["exportRows"][1]["col1"] == "Tomorrow"
    assert context["tableData"][0]["label"] == "111114"


def test_report_context_extracts_html_table() -> None:
    context = report_context_from_prior_assistant_table(
        [
            _assistant(
                "<table><thead><tr><th>Invoice</th><th>eCom Order</th><th>Items</th>"
                "<th>Due</th></tr></thead><tbody><tr><td>INV-20421</td>"
                "<td>WO-8801</td><td>Business Cards (500 qty)</td>"
                "<td>2026-05-20</td></tr></tbody></table>"
            )
        ],
        conversation_id="conv-1",
        request_id="req-1",
    )

    assert context is not None
    assert context["exportColumns"][2]["header"] == "Items"
    assert context["exportRows"][0]["col0"] == "INV-20421"
    assert context["exportRows"][0]["col2"] == "Business Cards (500 qty)"
