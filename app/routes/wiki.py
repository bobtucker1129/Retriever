"""Boone Wiki routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.auth.cloudflare import get_identity_from_request
from app.auth.permissions import CurrentUser
from app.auth.sessions import current_user_from_identity, require_active_user
from app.config import AppSettings
from app.db.connection import create_connection
from app.db.repositories.wiki import WikiDocumentRecord, WikiLinkRecord, WikiRepository, WikiSectionRecord
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
    ("WI-015", "File Prep & Output", "wi-015-file-prep-output"),
    ("WI-018", "Mail", "wi-018-mail"),
    ("WI-022", "Secure Mailing", "wi-022-secure-mailing"),
    ("WI-023", "Outsource Receiving", "wi-023-outsource-receiving"),
    ("WI-024", "PrintSmith Template Usage", "wi-024-printsmith-template-usage"),
    ("WI-030", "Supplier Review", "wi-030-supplier-review"),
]


FALLBACK_DOCUMENTS = [
    WikiDocumentRecord(
        id=1015,
        slug="wi-015-file-prep-output",
        title="File Prep & Output",
        document_code="WI-015",
        document_type="work_instruction",
        category="Work Instructions",
        summary_status="draft",
        summary="Draft Wiki card for file preparation and output work instructions. The controlled source remains in Google Drive until reviewed summaries are approved.",
        source_url="",
    ),
    WikiDocumentRecord(
        id=1018,
        slug="wi-018-mail",
        title="Mail",
        document_code="WI-018",
        document_type="work_instruction",
        category="Work Instructions",
        summary_status="draft",
        summary="Draft Wiki card for mail production work instructions. Future sync will refresh this card from the Level 3 Work Instructions source.",
        source_url="",
    ),
    WikiDocumentRecord(
        id=1022,
        slug="wi-022-secure-mailing",
        title="Secure Mailing",
        document_code="WI-022",
        document_type="work_instruction",
        category="Work Instructions",
        summary_status="draft",
        summary="Draft Wiki card for secure mailing practices. This page is meant to summarize controlled requirements without sending employees directly into the raw ISO document.",
        source_url="",
    ),
    WikiDocumentRecord(
        id=1023,
        slug="wi-023-outsource-receiving",
        title="Outsource Receiving",
        document_code="WI-023",
        document_type="work_instruction",
        category="Work Instructions",
        summary_status="draft",
        summary="Draft Wiki card for receiving outsourced work and preserving traceability through Boone procedures.",
        source_url="",
    ),
    WikiDocumentRecord(
        id=1024,
        slug="wi-024-printsmith-template-usage",
        title="PrintSmith Template Usage",
        document_code="WI-024",
        document_type="work_instruction",
        category="Work Instructions",
        summary_status="draft",
        summary="Draft Wiki card for PrintSmith template usage. It will become a reviewed internal reference after the source document is summarized.",
        source_url="",
    ),
    WikiDocumentRecord(
        id=1030,
        slug="wi-030-supplier-review",
        title="Supplier Review",
        document_code="WI-030",
        document_type="work_instruction",
        category="Work Instructions",
        summary_status="draft",
        summary="Draft Wiki card for supplier review work instructions and related quality-system supplier controls.",
        source_url="",
    ),
    WikiDocumentRecord(
        id=2001,
        slug="m-001-quality-manual",
        title="Quality Manual",
        document_code="M-001",
        document_type="quality_manual",
        category="Quality & ISO",
        summary_status="draft",
        summary="Top-level ISO quality manual card. This should become the entry point into the reviewed quality-system overview.",
        source_url="",
    ),
    WikiDocumentRecord(
        id=2023,
        slug="sop-023-secure-data-control",
        title="Secure Data Control",
        document_code="SOP-023",
        document_type="procedure",
        category="Security Posture",
        summary_status="draft",
        summary="Draft procedure card for secure data control and customer-data handling posture.",
        source_url="",
    ),
]


FALLBACK_SECTIONS = {
    "wi-022-secure-mailing": [
        WikiSectionRecord(
            slug="purpose",
            heading="Purpose",
            section_order=1,
            summary="Summarize when secure mailing rules apply and what employees should know before handling controlled mail work.",
            body_status="draft",
        ),
        WikiSectionRecord(
            slug="employee-view",
            heading="Employee View",
            section_order=2,
            summary="Provide practical guidance and links without opening the controlled ISO source document directly.",
            body_status="draft",
        ),
    ],
    "sop-023-secure-data-control": [
        WikiSectionRecord(
            slug="security-posture",
            heading="Security Posture",
            section_order=1,
            summary="Summarize Boone's controlled data handling in internal, employee-facing language.",
            body_status="draft",
        )
    ],
}


FALLBACK_LINKS = {
    "wi-022-secure-mailing": [
        WikiLinkRecord(
            label="Current internal wiki collection",
            url="https://www.boonegraphics.net/internal-wiki",
            link_type="legacy",
            visible_to="employee",
        )
    ]
}


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


def _wiki_repository(settings: AppSettings) -> WikiRepository | None:
    if not settings.mysql_host or not settings.mysql_user or not settings.mysql_password:
        return None
    return WikiRepository(lambda: create_connection(settings))


def _fallback_document(slug: str) -> WikiDocumentRecord | None:
    for document in FALLBACK_DOCUMENTS:
        if document.slug == slug:
            return document
    return None


def _documents_from_repo(settings: AppSettings) -> list[WikiDocumentRecord]:
    repo = _wiki_repository(settings)
    if not repo:
        return FALLBACK_DOCUMENTS
    try:
        documents = repo.list_documents()
    except Exception:
        documents = []
    return documents or FALLBACK_DOCUMENTS


@router.get("/", response_class=HTMLResponse)
async def wiki_home(
    request: Request,
    user: CurrentUser = Depends(_current_wiki_user),
    settings: AppSettings = Depends(settings_dependency),
):
    wiki_documents = _documents_from_repo(settings)
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
            "wiki_documents": wiki_documents,
            "iso_source_map": ISO_SOURCE_MAP,
        },
    )


@router.get("/doc/{slug}", response_class=HTMLResponse)
async def wiki_document_detail(
    slug: str,
    request: Request,
    user: CurrentUser = Depends(_current_wiki_user),
    settings: AppSettings = Depends(settings_dependency),
):
    repo = _wiki_repository(settings)
    document = None
    sections: list[WikiSectionRecord] = []
    links: list[WikiLinkRecord] = []
    if repo:
        try:
            document = repo.get_document_by_slug(slug)
            if document:
                sections = repo.list_sections(document.id)
                links = repo.list_links(document.id, include_admin=user.is_admin)
        except Exception:
            document = None

    if not document:
        document = _fallback_document(slug)
        if document:
            sections = FALLBACK_SECTIONS.get(slug, [])
            links = FALLBACK_LINKS.get(slug, [])

    if not document:
        raise HTTPException(status_code=404, detail="Wiki document not found")

    return templates.TemplateResponse(
        request,
        "wiki/detail.html",
        {
            "user": user,
            "settings": settings,
            "page_title": f"Wiki - {document.document_code or document.title}",
            "active_nav": "wiki",
            "nav_shell": "full",
            "document": document,
            "sections": sections,
            "links": links,
        },
    )
