"""
Retriever PrePress - WIP Tracker
Route handlers for PrePress sub-app

This sub-app replaces the Google Sheet WIP tracking for prepress operators,
automatically tracking job assignments, file arrivals, and proof submissions.
"""

from datetime import datetime
import json
import logging
from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from app.auth.cloudflare import get_identity_from_request
from app.auth.permissions import CurrentUser
from app.auth.sessions import current_user_from_identity, require_active_user
from app.config import AppSettings
from app.security import InputValidator, rate_limiter
from app.database.queries import prepress as prepress_queries
from app.dependencies import settings_dependency

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/prepress", tags=["prepress"])

# Templates
TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=TEMPLATES_DIR)


class SaveJobTicketBody(BaseModel):
    mode: Literal["invoice", "parts"]
    job_part_numbers: List[str] = Field(default_factory=list)


def _current_prepress_user(
    request: Request,
    settings: AppSettings = Depends(settings_dependency),
) -> CurrentUser:
    identity = get_identity_from_request(request, settings)
    user = current_user_from_identity(identity, settings)
    require_active_user(user)
    if not user.can_open_prepress():
        raise HTTPException(status_code=403, detail="PrePress access required")
    return user


def get_template_context(request: Request, user: CurrentUser, settings: AppSettings) -> dict:
    """Build common template context for PrePress pages"""
    return {
        "request": request,
        "user": user,
        "current_app": "prepress",
        "settings": settings,
        "active_nav": "prepress",
        "nav_shell": "full",
        "prepress_job_ticket_save_enabled": bool(settings.prepress_job_ticket_save_enabled),
        "printsmith_report_base_url": settings.prepress_printsmith_report_base_url.rstrip("/"),
    }


def get_user_identifier(request: Request, user: Optional[CurrentUser] = None) -> str:
    """Get unique identifier for rate limiting."""
    if user:
        return f"user:{user.email}"
    return f"ip:{request.client.host if request.client else 'unknown'}"


def _prepress_actor_label(user: Optional[CurrentUser]) -> str:
    """Prefer canonical operator names over auth usernames for workflow attribution."""
    raw_actor = str(getattr(user, "display_name", "") or getattr(user, "email", "") or "").strip()
    if not raw_actor:
        return "unknown"
    normalized = prepress_queries.normalize_prepress_actor_name(raw_actor)
    return normalized or raw_actor


@router.get("/", response_class=HTMLResponse)
async def prepress_home(
    request: Request,
    user: CurrentUser = Depends(_current_prepress_user),
    settings: AppSettings = Depends(settings_dependency),
):
    """PrePress home page - WIP tracker"""
    context = get_template_context(request, user, settings)
    context["page_title"] = "PrePress - WIP Tracker"
    # Operators loaded for initial dropdown options; counts are updated after WIP refresh.
    try:
        context["operators"] = prepress_queries.get_prepress_operators()
    except Exception:
        logger.exception("PrePress home: get_prepress_operators failed")
        context["operators"] = []
    return templates.TemplateResponse(request, "prepress/index.html", context)


@router.get("/partials/wip-table", response_class=HTMLResponse)
async def prepress_wip_table(
    request: Request,
    queue: str = "all",
    include_completed: int = 0,
    page_size: str = "25",
    sort_by: str = "invoice_number",
    sort_dir: str = "asc",
    prepress_search: str = "",
    user: CurrentUser = Depends(_current_prepress_user),
    settings: AppSettings = Depends(settings_dependency),
):
    context = get_template_context(request, user, settings)

    include_completed_bool = bool(include_completed)

    allowed_sort_by = {
        "invoice_number",
        "assigned_to",
        "account_name",
        "taken_by",
        "proof_date",
        "is_hold",
        "needs_data",
        "working_started_at",
        # reference-mode fields
        "completed_at",
        "completed_set_by",
        "most_proof_round",
        "notes",
    }
    sort_by = sort_by if sort_by in allowed_sort_by else "invoice_number"
    sort_dir = "desc" if str(sort_dir).lower() == "desc" else "asc"

    def _fmt_dt(value: object) -> str:
        if isinstance(value, datetime):
            return value.strftime("%m/%d %H:%M")
        return ""

    def _fmt_date(value: object) -> str:
        if isinstance(value, datetime):
            return value.strftime("%m/%d/%Y")
        # MIS proofdate sometimes comes back as date
        try:
            if hasattr(value, "strftime"):
                return value.strftime("%m/%d/%Y")  # type: ignore[union-attr]
        except Exception:
            pass
        if isinstance(value, str):
            return value
        return ""

    def _parse_page_size(value: str) -> int:
        v = (value or "").strip().lower()
        if v in {"all", "0", "-1"}:
            return 0
        try:
            n = int(v)
            return n if n > 0 else 25
        except Exception:
            return 25

    page_size_int = _parse_page_size(page_size)

    def _sort_value(inv: dict):
        if sort_by == "assigned_to":
            v = inv.get("assigned_to_name")
        else:
            v = inv.get(sort_by)
        if v is None:
            return (1, "")
        if sort_by in {"is_hold", "needs_data"}:
            return (0, int(bool(v)))
        # Dates/timestamps are comparable in Python when consistent types
        return (0, v)

    # Completed reference mode: MySQL-only list so users can restore accidental completes.
    if include_completed_bool:
        invoices = prepress_queries.get_prepress_completed_reference_invoices()
        for inv in invoices:
            inv["assigned_to_name"] = ""
            inv["search_text"] = " ".join(
                [
                    str(inv.get("invoice_number") or ""),
                    str(inv.get("account_name") or ""),
                    str(inv.get("taken_by") or ""),
                    _fmt_dt(inv.get("working_started_at")),
                    _fmt_dt(inv.get("completed_at")),
                    "completed yes",
                    str(inv.get("completed_set_by") or ""),
                    str(inv.get("most_proof_round") or ""),
                    str(inv.get("notes") or ""),
                ]
            ).strip()
        try:
            invoices.sort(key=_sort_value, reverse=(sort_dir == "desc"))
        except Exception:
            # never break the UI on sort errors
            pass
        q = str(prepress_search or "").strip().lower()
        if q:
            invoices = [inv for inv in invoices if q in str(inv.get("search_text") or "").lower()]
        if page_size_int:
            invoices = invoices[:page_size_int]
        context.update(
            {
                "operators": prepress_queries.get_prepress_operators(),
                "invoices": invoices,
                "analytics": {},
                "queue": queue,
                "include_completed": include_completed_bool,
                "wip_payload_json": None,
                "completed_reference_mode": True,
                "page_size": "all" if page_size_int == 0 else str(page_size_int),
                "sort_by": sort_by,
                "sort_dir": sort_dir,
            }
        )
        return templates.TemplateResponse(request, "prepress/partials/wip_table.html", context)

    view_mode = "all"
    selected_prepress_id: Optional[int] = None
    if queue == "shared":
        view_mode = "shared"
    elif queue == "all":
        view_mode = "all"
    else:
        try:
            selected_prepress_id = int(queue)
            view_mode = "my"
        except Exception:
            queue = "all"
            view_mode = "all"

    data = prepress_queries.get_prepress_wip(
        selected_prepress_id=selected_prepress_id,
        view_mode=view_mode,
        include_completed=include_completed_bool,
    )

    invoices = data["invoices"]
    operator_name_by_id = {}
    try:
        for op in data.get("operators") or []:
            operator_name_by_id[int(op.id)] = str(op.name or "")  # type: ignore[attr-defined]
    except Exception:
        operator_name_by_id = {}

    for inv in invoices:
        ops = inv.get("matched_operator_ids") or []
        assigned_to_name = ""
        assigned_to_id = None
        if len(ops) > 1:
            assigned_to_name = "Shared"
        elif len(ops) == 1:
            try:
                assigned_to_id = int(ops[0])
                assigned_to_name = operator_name_by_id.get(assigned_to_id, "")
            except Exception:
                assigned_to_id = None
                assigned_to_name = ""

        inv["assigned_to_prepress_id"] = assigned_to_id
        inv["assigned_to_name"] = assigned_to_name

        is_hold = bool(inv.get("is_hold"))
        needs_data = bool(inv.get("needs_data"))
        working_on = bool(inv.get("working_started_at"))
        completed_yes = bool(inv.get("completed_at"))
        has_hcp = bool(inv.get("has_hard_copy_proof"))

        inv["search_text"] = " ".join(
            [
                str(inv.get("invoice_number") or ""),
                str(inv.get("invoice_amount_display") or ""),
                assigned_to_name,
                str(inv.get("account_name") or ""),
                str(inv.get("taken_by") or ""),
                _fmt_date(inv.get("proof_date")),
                ("HCP" if has_hcp else ""),
                ("hcp yes" if has_hcp else ""),
                ("Shared" if len(ops) > 1 else ""),
                ("shared yes" if len(ops) > 1 else ""),
                ("hold yes" if is_hold else ""),
                ("data yes" if needs_data else ""),
                ("working on" if working_on else ""),
                ("completed yes" if completed_yes else ""),
                _fmt_dt(inv.get("working_started_at")),
                _fmt_dt(inv.get("completed_at")),
                str(inv.get("notes") or ""),
            ]
        ).strip()

    try:
        invoices.sort(key=_sort_value, reverse=(sort_dir == "desc"))
    except Exception:
        pass
    q = str(prepress_search or "").strip().lower()
    if q:
        invoices = [inv for inv in invoices if q in str(inv.get("search_text") or "").lower()]
    if page_size_int:
        invoices = invoices[:page_size_int]

    # Payload used by the shell to update dropdown counts + analytics labels.
    wip_payload_json = json.dumps(
        {
            "operator_counts": data.get("operator_counts", {}),
            "shared_queue_count": data.get("shared_queue_count", 0),
            "analytics": data.get("analytics", {}),
        }
    )

    context.update(
        {
            "operators": data["operators"],
            "invoices": invoices,
            "analytics": data["analytics"],
            "queue": queue,
            "include_completed": include_completed_bool,
            "wip_payload_json": wip_payload_json,
            "completed_reference_mode": False,
            "page_size": "all" if page_size_int == 0 else str(page_size_int),
            "sort_by": sort_by,
            "sort_dir": sort_dir,
        }
    )
    return templates.TemplateResponse(request, "prepress/partials/wip_table.html", context)


@router.get("/partials/statistics", response_class=HTMLResponse)
async def prepress_statistics(
    request: Request,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    include_completed: int = 0,
    user: CurrentUser = Depends(_current_prepress_user),
    settings: AppSettings = Depends(settings_dependency),
):
    """
    Statistics panel (passive) - does not impact WIP list behavior.

    Filters are for stats only:
    - date range applies to working_started_at (workflow-only, MySQL)
    - include_completed includes completed invoices in statistics calculations
    """
    context = get_template_context(request, user, settings)

    include_completed_bool = bool(include_completed)

    stats = prepress_queries.get_prepress_statistics(
        date_from=date_from,
        date_to=date_to,
        include_completed=include_completed_bool,
    )

    context.update(
        {
            "filters": stats["filters"],
            "summary": stats["summary"],
            "rows": stats["rows"],
        }
    )

    return templates.TemplateResponse(request, "prepress/partials/statistics.html", context)


@router.get("/partials/invoice/{invoice_number}/parts", response_class=HTMLResponse)
async def prepress_invoice_parts(
    request: Request,
    invoice_number: str,
    user: CurrentUser = Depends(_current_prepress_user),
    settings: AppSettings = Depends(settings_dependency),
):
    context = get_template_context(request, user, settings)

    if not InputValidator.validate_invoice_number(invoice_number):
        context["parts"] = []
        context["invoice_number"] = invoice_number
        return templates.TemplateResponse(request, "prepress/partials/jobpart_rows.html", context)

    parts = prepress_queries.get_invoice_job_parts(invoice_number)
    context["parts"] = parts
    context["invoice_number"] = invoice_number
    return templates.TemplateResponse(request, "prepress/partials/jobpart_rows.html", context)


@router.post("/api/invoice/{invoice_number}/save-job-ticket")
async def prepress_save_job_ticket(
    invoice_number: str,
    body: SaveJobTicketBody,
    request: Request,
    user: CurrentUser = Depends(_current_prepress_user),
    settings: AppSettings = Depends(settings_dependency),
):
    """
    Fetch job ticket PDF(s) from PrintSmith and write under the invoice job folder Remote/.
    """
    if not rate_limiter.is_allowed(get_user_identifier(request, user)):
        return JSONResponse(
            status_code=429,
            content={"ok": False, "message": "Too many requests. Try again shortly.", "path": None},
        )
    if not InputValidator.validate_invoice_number(invoice_number):
        return JSONResponse(
            status_code=400,
            content={"ok": False, "message": "Invalid invoice number.", "path": None},
        )
    if body.mode == "parts" and not body.job_part_numbers:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "message": "Select at least one job part.", "path": None},
        )
    if not settings.prepress_job_ticket_save_enabled:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "message": "Saving job tickets to disk is disabled.", "path": None},
        )
    from app.prepress.save_job_ticket import save_job_ticket_to_remote

    result = await save_job_ticket_to_remote(
        settings,
        invoice_number,
        body.mode,
        body.job_part_numbers,
    )
    return JSONResponse(
        content={
            "ok": result.ok,
            "message": result.message,
            "path": result.path,
        }
    )


@router.post("/api/invoice/{invoice_number}/update", response_class=HTMLResponse)
async def prepress_update_invoice(
    request: Request,
    invoice_number: str,
    queue: str = Form("all"),
    include_completed: int = Form(0),
    page_size: str = Form("25"),
    sort_by: str = Form("invoice_number"),
    sort_dir: str = Form("asc"),
    prepress_search: str = Form(""),
    action: str = Form(...),
    value: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    user: CurrentUser = Depends(_current_prepress_user),
    settings: AppSettings = Depends(settings_dependency),
):
    """
    Update invoice_state. Returns refreshed wip table partial for simplicity.
    action:
      - toggle_hold
      - toggle_needs_data
      - toggle_working
      - toggle_completed
      - set_notes
    """
    if not rate_limiter.is_allowed(get_user_identifier(request, user)):
        # still return table so UI doesn't get stuck
        return await prepress_wip_table(
            request,
            queue,
            include_completed,
            page_size,
            sort_by,
            sort_dir,
            prepress_search,
            user,
            settings,
        )

    if not InputValidator.validate_invoice_number(invoice_number):
        return await prepress_wip_table(
            request,
            queue,
            include_completed,
            page_size,
            sort_by,
            sort_dir,
            prepress_search,
            user,
            settings,
        )

    now = datetime.now()
    actor_label = _prepress_actor_label(user)

    if action == "toggle_hold":
        prepress_queries.set_invoice_hold(invoice_number, is_hold=(value == "1"))
    elif action == "toggle_needs_data":
        prepress_queries.set_invoice_needs_data(invoice_number, needs_data=(value == "1"))
    elif action == "toggle_working":
        prepress_queries.set_invoice_working_started_at(
            invoice_number,
            now if value == "1" else None,
            working_set_by=actor_label if value == "1" else None,
        )
    elif action == "toggle_completed":
        prepress_queries.set_invoice_completed_at(
            invoice_number,
            now if value == "1" else None,
            completed_set_by=actor_label if value == "1" else None,
        )
    elif action == "set_notes":
        safe_notes = InputValidator.sanitize_text(notes or "", max_length=4000)
        prepress_queries.set_invoice_notes(invoice_number, safe_notes)

    return await prepress_wip_table(
        request,
        queue,
        include_completed,
        page_size,
        sort_by,
        sort_dir,
        prepress_search,
        user,
        settings,
    )


@router.post("/api/job/{invoice_number}/{job_part_number}/update", response_class=HTMLResponse)
async def prepress_update_jobpart(
    request: Request,
    invoice_number: str,
    job_part_number: str,
    action: str = Form(...),
    notes: Optional[str] = Form(None),
    user: CurrentUser = Depends(_current_prepress_user),
    settings: AppSettings = Depends(settings_dependency),
):
    """
    Update jobpart_state/proof_event. Returns refreshed parts partial.
    action:
      - set_notes
      - add_proof
    """
    if not rate_limiter.is_allowed(get_user_identifier(request, user)):
        context = get_template_context(request, user, settings)
        context["parts"] = prepress_queries.get_invoice_job_parts(invoice_number)
        context["invoice_number"] = invoice_number
        return templates.TemplateResponse(request, "prepress/partials/jobpart_rows.html", context)

    if not InputValidator.validate_invoice_number(invoice_number):
        context = get_template_context(request, user, settings)
        context["parts"] = []
        context["invoice_number"] = invoice_number
        return templates.TemplateResponse(request, "prepress/partials/jobpart_rows.html", context)

    actor_label = _prepress_actor_label(user)

    if action == "set_notes":
        safe_notes = InputValidator.sanitize_text(notes or "", max_length=4000)
        prepress_queries.upsert_jobpart_note(invoice_number, job_part_number, safe_notes)
    elif action == "add_proof":
        prepress_queries.add_next_proof_event(invoice_number, job_part_number, actor_label)

    context = get_template_context(request, user, settings)
    context["parts"] = prepress_queries.get_invoice_job_parts(invoice_number)
    context["invoice_number"] = invoice_number
    return templates.TemplateResponse(request, "prepress/partials/jobpart_rows.html", context)
