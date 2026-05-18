"""Boone Wiki routes."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from app.auth.cloudflare import get_identity_from_request
from app.auth.permissions import CurrentUser
from app.auth.sessions import current_user_from_identity, require_active_user
from app.config import AppSettings
from app.db.connection import create_connection
from app.db.repositories.wiki import (
    WikiDocumentRecord,
    WikiLinkRecord,
    WikiRepository,
    WikiSectionRecord,
    WikiSourceStatusRecord,
)
from app.dependencies import settings_dependency
from app.wiki.sync import (
    DriveInventoryItem,
    fetch_internal_wiki_html,
    parse_datetime,
    sync_drive_inventory,
    sync_internal_wiki_links,
)

router = APIRouter(prefix="/wiki", tags=["wiki"])
templates = Jinja2Templates(directory="app/templates")


WIKI_SECTIONS = [
    {
        "title": "SweetProcess Procedures",
        "kicker": "Daily-use links",
        "description": "Fast links to the procedure collection employees already use every day. These stay visible while Retriever builds richer wiki cards around the same workflows.",
        "source": "boonegraphics.net/internal-wiki SweetProcess links",
    },
    {
        "title": "Work Instructions",
        "kicker": "Shop floor reference",
        "description": "Prominent access to WI documents such as secure mailing, mail, file prep, PrintSmith templates, outsource receiving, and supplier review.",
        "source": "Google Drive Level 3 Work Instructions",
    },
    {
        "title": "Quality & ISO",
        "kicker": "Certified system",
        "description": "Quality manual, Level 2 procedures, Level 3 documents, forms, training evidence, audit planning, and external ISO references in controlled summary form.",
        "source": "Google Drive ISO folder: Final Boone and External Documents",
    },
    {
        "title": "Security Posture",
        "kicker": "Audit readiness",
        "description": "Security commitments, controlled access, customer data handling, production safeguards, Boone DataLock context, and known audit questions from recent audit documents.",
        "source": "Internal security/audit documents plus public Boone security pages",
    },
    {
        "title": "General Knowledge",
        "kicker": "Company reference",
        "description": "Internal version of Boone's public website: services, departments, customers, products, company info, and practical reference material rewritten for employees.",
        "source": "boonegraphics.net and selected internal notes",
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


SWEETPROCESS_LINKS = [
    (
        "Processing Cal Poly DSF",
        "AM",
        "https://www.sweetprocess.com/procedures/132kYCJ9J0/processing-cal-poly-dsf-am/",
    ),
    (
        "UPS Label Purchasing",
        "",
        "https://www.sweetprocess.com/procedures/46mqMSPDP1/ups-label-purchasing/",
    ),
    (
        "Cleaning Up House Account Contacts",
        "AM",
        "https://www.sweetprocess.com/procedures/5jR9Vf9Y9x/cleaning-up-house-account-contacts-am/",
    ),
    (
        "SBCERS Statement Procedures",
        "ST",
        "https://www.sweetprocess.com/procedures/5jV1Rf9Y9x/sbcers-statement-procedures-st/",
    ),
    (
        "XMPie Database and Job Clean-up",
        "ST",
        "https://www.sweetprocess.com/procedures/70BaVIm4m1/xmpie-database-and-job-clean-up-st/",
    ),
    (
        "Marking Pending Estimates for Archival",
        "",
        "https://www.sweetprocess.com/procedures/70ja7um4m1/marking-pending-estimates-for-archival/",
    ),
    (
        "UPS Batch Shipping",
        "ST",
        "https://www.sweetprocess.com/procedures/85bNpID1D7/ups-batch-shipping-st/",
    ),
    (
        "DSF Store Management",
        "TO",
        "https://www.sweetprocess.com/procedures/AK5yJT1B1o/dsf-store-management-to/",
    ),
    (
        "How to Remove Prospects",
        "TO",
        "https://www.sweetprocess.com/procedures/BVEvOUMLMZ/how-to-remove-prospects-to/",
    ),
    (
        "Accessing the ISO Folder",
        "",
        "https://www.sweetprocess.com/procedures/EV3K9i7q7V/accessing-the-iso-folder/",
    ),
    (
        "Manual Quote Required DSF ABI",
        "",
        "https://www.sweetprocess.com/procedures/EVOY2s7q7V/manual-quote-required-dsf-abi/",
    ),
    (
        "Using Walk-in in PrintSmith",
        "ST",
        "https://www.sweetprocess.com/procedures/J7ooJCBOB0/using-walk-in-in-printsmith-st/",
    ),
    (
        "Adding Your Signature in PlanProphet",
        "",
        "https://www.sweetprocess.com/procedures/MO7YkHZDZm/adding-your-signature-in-planprophet/",
    ),
    (
        "Labeling Prospects/Accounts with the Correct Business Type",
        "TO",
        "https://www.sweetprocess.com/procedures/NYeJ4F0D0z/labeling-prospectsaccounts-with-the-correct-business-type-industry-to/",
    ),
    (
        "Adding DSF Imposition Templates to Switch",
        "ST",
        "https://www.sweetprocess.com/procedures/OWLeGFxYxG/adding-dsf-imposition-templates-to-switch-st/",
    ),
    (
        "Entering Prospects in PlanProphet",
        "TO",
        "https://www.sweetprocess.com/procedures/Op46VSxYxG/entering-prospects-in-planprophet-to/",
    ),
    (
        "Approving Quotes Using the Customer Portal",
        "",
        "https://www.sweetprocess.com/procedures/QDaO6smDmR/approving-quotes-using-the-customer-portal/",
    ),
    (
        "Resubmitting Jobs to Esko or Switch",
        "ST",
        "https://www.sweetprocess.com/procedures/VpqeMTw2w0/resubmitting-jobs-to-esko-or-switch-st/",
    ),
    (
        "Purchasing an Item / PO Process",
        "SS / CO",
        "https://www.sweetprocess.com/procedures/YW8KYTqEq4/purchasing-an-item-po-process-ss-co/",
    ),
    (
        "Mechanics Bank: Remove Users from DSF",
        "TO",
        "https://www.sweetprocess.com/procedures/Zjr4vSqAqO/mechanics-bank-instructions-for-removing-users-from-dsf-to/",
    ),
    (
        "Mechanics Bank: Add Users to DSF",
        "TO",
        "https://www.sweetprocess.com/procedures/aDAODIGJGd/mechanics-bank-instructions-for-adding-new-users-to-dsf-to/",
    ),
    (
        "How to Add Prospects",
        "TO",
        "https://www.sweetprocess.com/procedures/bDB4PIB5BL/how-to-add-prospects-to/",
    ),
    (
        "Create UMT Jobs / Boone Mail",
        "TO",
        "https://www.sweetprocess.com/procedures/ev74KUojoR/create-umt-jobs-boone-mail-to/",
    ),
    (
        "Paper Ordering",
        "NG",
        "https://www.sweetprocess.com/procedures/j5EKDTG9Go/paper-ordering-ng/",
    ),
    (
        "Lifetime of a Prospect",
        "TO",
        "https://www.sweetprocess.com/procedures/jDaWOcG9Go/lifetime-of-a-prospect-to/",
    ),
    (
        "Send a Customer Portal Link",
        "",
        "https://www.sweetprocess.com/procedures/mzZwWhoyo6/how-to-send-a-customer-portal-link/",
    ),
    (
        "Archive Jobs in Esko",
        "ST",
        "https://www.sweetprocess.com/procedures/mzo66ioyo6/archive-jobs-in-esko-st/",
    ),
    (
        "Custom Shipping Labels in PlanProphet",
        "",
        "https://www.sweetprocess.com/procedures/v21V7swdw6/custom-shipping-labels-in-planprophet/",
    ),
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


class WikiDriveInventoryFile(BaseModel):
    id: str = ""
    name: str = ""
    title: str = ""
    url: str = ""
    webViewLink: str = ""
    modifiedTime: Optional[str] = None
    modified_at: Optional[str] = None
    mimeType: str = ""
    mime_type: str = ""
    path: str = ""


class WikiDriveInventoryPayload(BaseModel):
    generatedAt: Optional[str] = None
    roots: list[dict[str, Any]] = Field(default_factory=list)
    files: list[WikiDriveInventoryFile] = Field(default_factory=list)


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


def _sweetprocess_links_from_repo(settings: AppSettings) -> list[tuple[str, str, str]]:
    repo = _wiki_repository(settings)
    if not repo:
        return SWEETPROCESS_LINKS
    try:
        links = repo.list_source_links("boone-internal-wiki", link_type="legacy")
    except Exception:
        links = []
    if not links:
        return SWEETPROCESS_LINKS
    return [(link.label, "", link.url) for link in links]


def _source_statuses_from_repo(settings: AppSettings) -> list[WikiSourceStatusRecord]:
    repo = _wiki_repository(settings)
    if not repo:
        return []
    try:
        return repo.list_source_statuses()
    except Exception:
        return []


def _require_wiki_sync_token(request: Request, settings: AppSettings) -> None:
    if not settings.wiki_sync_enabled:
        raise HTTPException(status_code=404, detail="Wiki sync is not enabled")
    expected = settings.wiki_sync_token or ""
    auth = request.headers.get("authorization", "")
    token = ""
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
    token = token or request.headers.get("x-retriever-wiki-sync-token", "").strip()
    if not token or not secrets.compare_digest(token, expected):
        raise HTTPException(status_code=403, detail="Wiki sync token required")


def _inventory_items(payload: WikiDriveInventoryPayload) -> list[DriveInventoryItem]:
    items: list[DriveInventoryItem] = []
    for file in payload.files:
        title = file.title or file.name
        if not title:
            continue
        modified_raw = file.modified_at or file.modifiedTime or ""
        items.append(
            DriveInventoryItem(
                source_document_id=file.id or file.webViewLink or file.url or title,
                title=title,
                url=file.url or file.webViewLink,
                path=file.path,
                modified_at=parse_datetime(modified_raw) if modified_raw else None,
                mime_type=file.mime_type or file.mimeType,
            )
        )
    return items


@router.get("/", response_class=HTMLResponse)
async def wiki_home(
    request: Request,
    user: CurrentUser = Depends(_current_wiki_user),
    settings: AppSettings = Depends(settings_dependency),
):
    wiki_documents = _documents_from_repo(settings)
    sweetprocess_links = _sweetprocess_links_from_repo(settings)
    wiki_source_statuses = _source_statuses_from_repo(settings)
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
            "sweetprocess_links": sweetprocess_links,
            "wiki_documents": wiki_documents,
            "wiki_source_statuses": wiki_source_statuses,
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


@router.post("/sync/source-inventory")
async def wiki_sync_source_inventory(
    payload: WikiDriveInventoryPayload,
    request: Request,
    settings: AppSettings = Depends(settings_dependency),
) -> dict[str, Any]:
    _require_wiki_sync_token(request, settings)
    repo = _wiki_repository(settings)
    if not repo:
        raise HTTPException(status_code=503, detail="Wiki repository is not configured")

    drive_items = _inventory_items(payload)
    internal_result = sync_internal_wiki_links(repo, fetch_internal_wiki_html())
    drive_result = sync_drive_inventory(repo, drive_items)
    return {
        "status": "ok",
        "syncedAt": datetime.now(timezone.utc).isoformat(),
        "generatedAt": payload.generatedAt,
        "roots": len(payload.roots),
        "internalWiki": {
            "sourceKey": internal_result.source_key,
            "scanned": internal_result.scanned_count,
            "changed": internal_result.changed_count,
        },
        "drive": {
            "sourceKey": drive_result.source_key,
            "scanned": drive_result.scanned_count,
            "changed": drive_result.changed_count,
        },
    }
