"""Boone Wiki routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.auth.cloudflare import get_identity_from_request
from app.auth.permissions import CurrentUser
from app.auth.sessions import current_user_from_identity, require_active_user
from app.config import AppSettings
from app.dependencies import settings_dependency

router = APIRouter(prefix="/wiki", tags=["wiki"])
templates = Jinja2Templates(directory="app/templates")


WIKI_SECTIONS = [
    {
        "title": "Boone Basics",
        "kicker": "Company reference",
        "description": "Internal version of who Boone is, what we do, office locations, teams, and how our public story translates into employee context.",
        "source": "boonegraphics.net About Boone and service pages",
    },
    {
        "title": "Quality & ISO",
        "kicker": "Certified system",
        "description": "Quality manual, Level 2 procedures, Level 3 documents, forms, work instructions, training evidence, audit planning, and external ISO references.",
        "source": "Google Drive ISO folder: Final Boone and External Documents",
    },
    {
        "title": "Security Posture",
        "kicker": "Internal practices",
        "description": "Security commitments, controlled access, customer data handling, production safeguards, compliance posture, and Boone DataLock context.",
        "source": "Boone public site plus internal ISO/security documentation",
    },
    {
        "title": "Production Knowledge",
        "kicker": "Shop floor",
        "description": "Print production, mailing, fulfillment, signage, variable data, training documents, and practical work instructions employees need to find quickly.",
        "source": "Training Documents and ISO work instructions",
    },
    {
        "title": "Customer & Vendor Context",
        "kicker": "External relationships",
        "description": "Client-facing standards, vendor references, ISO marks usage, common customer programs, and internal notes that should not live on the public website.",
        "source": "External Documents: Clients, Vendors, ISO Marks Usage",
    },
]


WORK_INSTRUCTION_HIGHLIGHTS = [
    ("WI-015", "File Prep & Output"),
    ("WI-018", "Mail"),
    ("WI-022", "Secure Mailing"),
    ("WI-023", "Outsource Receiving"),
    ("WI-024", "PrintSmith Template Usage"),
    ("WI-030", "Supplier Review"),
]


ISO_SOURCE_MAP = [
    ("Level 1 Quality Manual", "Quality manual and top-level quality system overview."),
    ("Level 2 Procedures", "Core operating procedures that define how Boone runs controlled work."),
    ("Level 3 Documents", "Supporting documents and controlled references."),
    ("Level 3 Forms", "Forms and records used as ISO evidence."),
    ("Level 3 Work Instructions", "Practical step-by-step shop and process guidance."),
    ("Training Documents", "Role and equipment training material."),
    ("External Documents", "Standards, customers, vendors, marks, and external references."),
]


def _current_wiki_user(
    request: Request,
    settings: AppSettings = Depends(settings_dependency),
) -> CurrentUser:
    identity = get_identity_from_request(request, settings)
    user = current_user_from_identity(identity, settings)
    require_active_user(user)
    if not user.can_open_wiki():
        raise HTTPException(status_code=403, detail="Wiki access required")
    return user


@router.get("/", response_class=HTMLResponse)
async def wiki_home(
    request: Request,
    user: CurrentUser = Depends(_current_wiki_user),
    settings: AppSettings = Depends(settings_dependency),
):
    return templates.TemplateResponse(
        request,
        "wiki/index.html",
        {
            "user": user,
            "settings": settings,
            "page_title": "Wiki",
            "active_nav": "wiki",
            "nav_shell": "full",
            "wiki_sections": WIKI_SECTIONS,
            "work_instruction_highlights": WORK_INSTRUCTION_HIGHLIGHTS,
            "iso_source_map": ISO_SOURCE_MAP,
        },
    )
