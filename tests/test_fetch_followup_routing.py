"""Export follow-up route inheritance (no HTTP)."""

from __future__ import annotations

from app.db.repositories.fetch import FetchMessageRecord
from app.fetch.followup_routing import (
    html_export_prior_assistant,
    is_answer_snapshot_pdf_followup_text,
    is_artifact_refinement_followup_text,
    is_export_download_followup_text,
    is_html_export_followup_text,
    pdf_export_prior_assistant,
    resolve_fetch_ask_route,
)


def _rec(
    role: str,
    *,
    route_key: str,
    context_state: str | None,
    content: str = "...",
    metadata: dict | None = None,
) -> FetchMessageRecord:
    return FetchMessageRecord(
        message_id="m",
        conversation_id="c",
        user_id=1,
        role=role,
        content=content,
        route_key=route_key,
        context_state=context_state,
        metadata=metadata,
    )


def test_resolve_inherits_after_success_printsmith_broker_turn() -> None:
    assert is_answer_snapshot_pdf_followup_text("please save this answer as a PDF") is True
    assert is_answer_snapshot_pdf_followup_text("download the previous answer as pdf") is True
    assert is_answer_snapshot_pdf_followup_text("export the last reply as a pdf please") is True
    assert is_answer_snapshot_pdf_followup_text("export that chart as pdf") is False
    assert is_answer_snapshot_pdf_followup_text("export that report as pdf") is False
    assert is_answer_snapshot_pdf_followup_text("save this table as pdf") is False


def test_pdf_snapshot_prior_follows_same_inherit_rules_as_html() -> None:
    prior = [
        _rec(
            "assistant",
            route_key="docs_candidate",
            context_state="ready",
            content="Doc body.",
        ),
    ]
    assert pdf_export_prior_assistant(prior, "save this answer as pdf") is not None


def test_resolve_inherits_after_success_printsmith_broker_turn() -> None:
    prior = [
        _rec("user", route_key="printsmith_candidate", context_state=None, content="How many jobs?"),
        _rec(
            "assistant",
            route_key="printsmith_candidate",
            context_state="booneops",
            content="Here is your report.",
        ),
    ]
    route, extra = resolve_fetch_ask_route(
        "can you export that as a pdf file?",
        "general_candidate",
        prior,
    )
    assert route == "printsmith_candidate"
    assert extra == {}


def test_resolve_inherits_after_docs_ready_state() -> None:
    prior = [
        _rec("assistant", route_key="docs_candidate", context_state="ready", content="Manual summary."),
    ]
    route, extra = resolve_fetch_ask_route("export that as csv", "general_candidate", prior)
    assert route == "docs_candidate"
    assert extra == {}


def test_resolve_carries_allowlisted_prior_metadata() -> None:
    prior = [
        _rec(
            "assistant",
            route_key="printsmith_candidate",
            context_state="booneops",
            content="Totals",
            metadata={"reportContext": {"session": "abc"}, "source_cards": []},
        ),
    ]
    route, extra = resolve_fetch_ask_route("download that as xlsx please", "unknown", prior)
    assert route == "printsmith_candidate"
    assert extra == {"reportContext": {"session": "abc"}}


def test_resolve_export_merges_prior_metadata_with_spreadsheet_style_hint() -> None:
    prior = [
        _rec(
            "assistant",
            route_key="printsmith_candidate",
            context_state="booneops",
            content="Totals",
            metadata={"reportContext": {"session": "abc"}, "source_cards": []},
        ),
    ]
    route, extra = resolve_fetch_ask_route(
        "download that xlsx with bold colorful headers",
        "unknown",
        prior,
    )
    assert route == "printsmith_candidate"
    assert extra == {
        "reportContext": {"session": "abc"},
        "reportStyle": "basic_styled_excel",
    }


def test_resolve_does_not_inherit_after_stub_assistant_even_if_printsmith_labeled() -> None:
    prior = [
        _rec("assistant", route_key="printsmith_candidate", context_state="stub", content="offline"),
    ]
    route, _extra = resolve_fetch_ask_route("save that as pdf", "general_candidate", prior)
    assert route == "general_candidate"


def test_resolve_does_not_inherit_vague_export_despite_successful_prior() -> None:
    prior = [
        _rec(
            "assistant",
            route_key="printsmith_candidate",
            context_state="booneops",
            content="Here is your report.",
        ),
    ]
    route, _ = resolve_fetch_ask_route("save as excel", "general_candidate", prior)
    assert route == "general_candidate"
    route2, _ = resolve_fetch_ask_route("export as pdf", "general_candidate", prior)
    assert route2 == "general_candidate"


def test_resolve_does_not_inherit_after_booneops_error() -> None:
    prior = [
        _rec(
            "assistant",
            route_key="printsmith_candidate",
            context_state="booneops_error",
            content="Network error stub",
        ),
    ]
    route, _ = resolve_fetch_ask_route("export that as csv", "general_candidate", prior)
    assert route == "general_candidate"


def test_resolve_does_not_override_blocked_write() -> None:
    prior = [
        _rec("assistant", route_key="printsmith_candidate", context_state="booneops", content="Ok"),
    ]
    route, _ = resolve_fetch_ask_route("export that as pdf", "blocked_write", prior)
    assert route == "blocked_write"


def test_is_export_followup_requires_action_format_and_referent() -> None:
    assert is_export_download_followup_text("can you export that as a pdf file?") is True
    assert is_export_download_followup_text("export that as csv") is True
    assert is_export_download_followup_text("save this as excel") is True
    assert is_export_download_followup_text("download the previous answer as csv") is True
    assert is_export_download_followup_text("make the last result an excel file") is True
    assert is_export_download_followup_text("export above as pdf") is True
    assert is_export_download_followup_text("make an excel workbook") is False
    assert is_export_download_followup_text("save as excel") is False
    assert is_export_download_followup_text("export as pdf") is False
    assert is_export_download_followup_text("the pdf format") is False
    assert is_export_download_followup_text("export something") is False


def test_is_html_export_followup_requires_action_html_and_referent() -> None:
    assert is_html_export_followup_text("can you export that as an html file?") is True
    assert is_html_export_followup_text("save that as index.html please") is True
    assert is_html_export_followup_text("save this as html") is True
    assert is_html_export_followup_text("download the previous answer as html") is True
    assert is_html_export_followup_text("export as html") is False
    assert is_html_export_followup_text("save as html") is False
    assert is_html_export_followup_text("export as pdf") is False
    assert is_html_export_followup_text("tell me about html") is False


def test_html_export_prior_requires_inheritable_assistant() -> None:
    good = [
        _rec(
            "assistant",
            route_key="printsmith_candidate",
            context_state="booneops",
            content="Totals",
        ),
    ]
    assert html_export_prior_assistant(good, "export that as html") is not None

    stub_prior = [
        _rec(
            "assistant",
            route_key="printsmith_candidate",
            context_state="stub",
            content="offline",
        ),
    ]
    assert html_export_prior_assistant(stub_prior, "download that as html") is None


def test_html_export_prior_not_triggered_without_html_format() -> None:
    prior = [
        _rec(
            "assistant",
            route_key="docs_candidate",
            context_state="ready",
            content="Docs body",
        ),
    ]
    assert html_export_prior_assistant(prior, "export that as csv") is None


def test_is_artifact_refinement_followup_detects_styling_and_rejects_trivia() -> None:
    assert is_artifact_refinement_followup_text("make the spreadsheet prettier") is True
    assert is_artifact_refinement_followup_text(
        "Can you fancy up the excel file and maybe add some bolding and colorful headers?"
    ) is True
    assert is_artifact_refinement_followup_text("why is the sky blue?") is False
    assert is_artifact_refinement_followup_text("what is the capital of France?") is False


def test_resolve_refinement_inherits_printsmith_with_exact_user_fancy_excel_phrase() -> None:
    prior = [
        _rec("user", route_key="printsmith_candidate", context_state=None, content="Sales by rep"),
        _rec(
            "assistant",
            route_key="printsmith_candidate",
            context_state="booneops",
            content="Attached: totals.xlsx",
        ),
    ]
    phrase = (
        "Can you fancy up the excel file and maybe add some bolding and colorful headers?"
    )
    route, extra = resolve_fetch_ask_route(phrase, "general_candidate", prior)
    assert route == "printsmith_candidate"
    assert extra.get("reportStyle") == "basic_styled_excel"


def test_resolve_fancy_excel_phrase_merges_prior_report_context_and_style() -> None:
    prior_ctx = {"exportRows": [{"a": 1}], "exportColumns": ["a"]}
    prior = [
        _rec(
            "assistant",
            route_key="printsmith_candidate",
            context_state="booneops",
            content="Attached: totals.xlsx",
            metadata={"reportContext": prior_ctx},
        ),
    ]
    phrase = (
        "Can you fancy up the excel file and maybe add some bolding and colorful headers?"
    )
    route, extra = resolve_fetch_ask_route(phrase, "general_candidate", prior)
    assert route == "printsmith_candidate"
    assert extra == {"reportContext": prior_ctx, "reportStyle": "basic_styled_excel"}


def test_resolve_refinement_inherits_fuzzy_phrases_with_style_hint_when_tabular() -> None:
    prior = [
        _rec(
            "assistant",
            route_key="printsmith_candidate",
            context_state="booneops",
            content="Here is your export.",
        ),
    ]
    for text in (
        "make the spreadsheet prettier",
        "add colorful headers to the workbook",
        "clean up that report",
        "make this table look nicer",
    ):
        route, extra = resolve_fetch_ask_route(text, "general_candidate", prior)
        assert route == "printsmith_candidate", text
        assert extra.get("reportStyle") == "basic_styled_excel", text


def test_resolve_refinement_pdf_clean_up_inherits_without_spreadsheet_style_hint() -> None:
    prior = [
        _rec(
            "assistant",
            route_key="docs_candidate",
            context_state="ready",
            content="Manual PDF attached.",
        ),
    ]
    route, extra = resolve_fetch_ask_route(
        "clean up that pdf layout please",
        "general_candidate",
        prior,
    )
    assert route == "docs_candidate"
    assert "reportStyle" not in extra


def test_resolve_refinement_does_not_trigger_for_unrelated_questions_after_report() -> None:
    prior = [
        _rec(
            "assistant",
            route_key="printsmith_candidate",
            context_state="booneops",
            content="January totals attached.",
        ),
    ]
    route, _ = resolve_fetch_ask_route("why is the sky blue?", "general_candidate", prior)
    assert route == "general_candidate"
    route2, _ = resolve_fetch_ask_route(
        "what is the capital of France?",
        "general_candidate",
        prior,
    )
    assert route2 == "general_candidate"


def test_resolve_refinement_definition_question_not_inherited_even_with_format_words() -> None:
    prior = [
        _rec(
            "assistant",
            route_key="printsmith_candidate",
            context_state="booneops",
            content="Report rows.",
        ),
    ]
    route, _ = resolve_fetch_ask_route(
        "what is spreadsheet formatting?",
        "general_candidate",
        prior,
    )
    assert route == "general_candidate"


def test_resolve_refinement_skips_general_stub_to_find_prior_broker_success() -> None:
    prior = [
        _rec(
            "assistant",
            route_key="printsmith_candidate",
            context_state="booneops",
            content="Totals attached.",
        ),
        _rec("user", route_key="general_candidate", context_state=None, content="thanks"),
        _rec(
            "assistant",
            route_key="general_candidate",
            context_state="stub",
            content="You're welcome.",
        ),
    ]
    route, extra = resolve_fetch_ask_route(
        "make the spreadsheet prettier",
        "general_candidate",
        prior,
    )
    assert route == "printsmith_candidate"
    assert extra.get("reportStyle") == "basic_styled_excel"


def test_malicious_script_stripped_from_standalone_export() -> None:
    from app.fetch.html_export import build_standalone_html_export_document

    doc = build_standalone_html_export_document(
        '<script>alert("x")</script>\nHello **there**.',
        source_route_label="printsmith_candidate",
    )
    low = doc.lower()
    assert "<script" not in low
    assert "<strong>there</strong>" in doc or ">there</" in doc
