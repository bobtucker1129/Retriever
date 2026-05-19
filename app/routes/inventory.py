"""
Retriever Inventory - Route handlers
Customer fulfillment inventory tracking sub-app.
"""

import csv
import io
import json
import logging

from fastapi import APIRouter, BackgroundTasks, Request, Depends, Form, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.auth.cloudflare import get_identity_from_request
from app.auth.permissions import CurrentUser
from app.auth.sessions import current_user_from_identity, require_active_user
from app.db.repositories import inventory as inv_queries
from app.services import email as email_service
from app.services.tag_generator import generate_tags_pdf
from app.config import AppSettings, get_settings
from app.dependencies import settings_dependency

router = APIRouter(prefix="/inventory", tags=["inventory"])

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=TEMPLATES_DIR)


def get_template_context(request: Request, user: CurrentUser) -> dict:
    """Build common template context for Inventory pages."""
    return {
        "request": request,
        "user": user,
        "settings": get_settings(),
        "current_app": "inventory",
        "active_nav": "inventory",
        "nav_shell": "full",
        "is_manager": inv_queries.is_manager(user),
    }


def _require_manager(user: CurrentUser) -> None:
    if not inv_queries.is_manager(user):
        raise HTTPException(status_code=403, detail="Manager access required")


def _username(user: CurrentUser) -> str:
    return user.email or user.display_name or "unknown"


def _pull_warning_pct() -> int:
    return get_settings().inventory_pull_warning_pct


# =========================================================================
# Dashboard
# =========================================================================


def _current_inventory_user(
    request: Request,
    settings: AppSettings = Depends(settings_dependency),
) -> CurrentUser:
    identity = get_identity_from_request(request, settings)
    user = current_user_from_identity(identity, settings)
    require_active_user(user)
    if not user.can_open_inventory():
        raise HTTPException(status_code=403, detail="Inventory access required")
    return user


@router.get("/", response_class=HTMLResponse)
async def inventory_home(request: Request, user: CurrentUser = Depends(_current_inventory_user)):
    context = get_template_context(request, user)
    low_stock = inv_queries.get_low_stock_products()
    depletion_map = inv_queries.get_depletion_projections_batch(low_stock) if low_stock else {}
    due_for_count = inv_queries.get_customers_due_for_count()
    txn_count = inv_queries.get_todays_transaction_count()
    approaching = sum(
        1 for p in low_stock
        if depletion_map.get(p["id"], {}).get("status") == "projected"
        and depletion_map[p["id"]]["days_remaining"] <= 14
    )
    context["low_stock"] = low_stock
    context["depletion_map"] = depletion_map
    context["due_for_count"] = due_for_count
    context["txn_count"] = txn_count
    context["approaching_depletion"] = approaching
    return templates.TemplateResponse(request, "inventory/index.html", context)


@router.get("/api/low-stock-count", response_class=HTMLResponse)
async def low_stock_badge(request: Request, user: CurrentUser = Depends(_current_inventory_user)):
    """Sidebar badge: returns HTML fragment with low stock count or empty string."""
    count = inv_queries.get_low_stock_count()
    if count > 0:
        return HTMLResponse(f'<span class="sidebar-badge">{count}</span>')
    return HTMLResponse("")


# =========================================================================
# Sites
# =========================================================================


@router.get("/sites", response_class=HTMLResponse)
async def site_list(request: Request, user: CurrentUser = Depends(_current_inventory_user)):
    context = get_template_context(request, user)
    sites = inv_queries.get_sites()
    for site in sites:
        site["zones"] = inv_queries.get_zones_for_site(site["id"])
    context["sites"] = sites
    return templates.TemplateResponse(request, "inventory/sites.html", context)


@router.get("/sites/new", response_class=HTMLResponse)
async def site_new(request: Request, user: CurrentUser = Depends(_current_inventory_user)):
    _require_manager(user)
    context = get_template_context(request, user)
    context["site"] = None
    return templates.TemplateResponse(request, "inventory/site_form.html", context)


@router.post("/sites", response_class=HTMLResponse)
async def site_create(
    request: Request,
    user: CurrentUser = Depends(_current_inventory_user),
    name: str = Form(...),
    address: Optional[str] = Form(None),
):
    _require_manager(user)
    inv_queries.create_site(name.strip(), (address or "").strip() or None, _username(user))
    return RedirectResponse("/inventory/sites", status_code=303)


@router.get("/sites/{site_id}/edit", response_class=HTMLResponse)
async def site_edit(site_id: int, request: Request, user: CurrentUser = Depends(_current_inventory_user)):
    _require_manager(user)
    site = inv_queries.get_site(site_id)
    if not site:
        raise HTTPException(404, "Site not found")
    context = get_template_context(request, user)
    context["site"] = site
    return templates.TemplateResponse(request, "inventory/site_form.html", context)


@router.post("/sites/{site_id}", response_class=HTMLResponse)
async def site_update(
    site_id: int,
    request: Request,
    user: CurrentUser = Depends(_current_inventory_user),
    name: str = Form(...),
    address: Optional[str] = Form(None),
):
    _require_manager(user)
    if not inv_queries.get_site(site_id):
        raise HTTPException(404, "Site not found")
    inv_queries.update_site(site_id, name.strip(), (address or "").strip() or None, _username(user))
    return RedirectResponse("/inventory/sites", status_code=303)


# =========================================================================
# Zones
# =========================================================================


@router.post("/zones", response_class=HTMLResponse)
async def zone_create(
    request: Request,
    user: CurrentUser = Depends(_current_inventory_user),
    site_id: int = Form(...),
    name: str = Form(...),
    description: Optional[str] = Form(None),
):
    _require_manager(user)
    inv_queries.create_zone(site_id, name.strip(), (description or "").strip() or None, _username(user))
    return RedirectResponse("/inventory/sites", status_code=303)


@router.get("/zones/{zone_id}/edit", response_class=HTMLResponse)
async def zone_edit(zone_id: int, request: Request, user: CurrentUser = Depends(_current_inventory_user)):
    _require_manager(user)
    zone = inv_queries.get_zone(zone_id)
    if not zone:
        raise HTTPException(404, "Zone not found")
    context = get_template_context(request, user)
    context["zone"] = zone
    context["sites"] = inv_queries.get_sites(active_only=True)
    return templates.TemplateResponse(request, "inventory/zone_form.html", context)


@router.post("/zones/{zone_id}", response_class=HTMLResponse)
async def zone_update(
    zone_id: int,
    request: Request,
    user: CurrentUser = Depends(_current_inventory_user),
    name: str = Form(...),
    description: Optional[str] = Form(None),
):
    _require_manager(user)
    if not inv_queries.get_zone(zone_id):
        raise HTTPException(404, "Zone not found")
    inv_queries.update_zone(zone_id, name.strip(), (description or "").strip() or None, _username(user))
    return RedirectResponse("/inventory/sites", status_code=303)


@router.get("/partials/zone-list/{site_id}", response_class=HTMLResponse)
async def zone_list_partial(site_id: int, request: Request, user: CurrentUser = Depends(_current_inventory_user)):
    context = get_template_context(request, user)
    context["zones"] = inv_queries.get_zones_for_site(site_id)
    context["site_id"] = site_id
    return templates.TemplateResponse(request, "inventory/partials/zone_list.html", context)


# =========================================================================
# Customers
# =========================================================================


@router.get("/customers", response_class=HTMLResponse)
async def customer_list(request: Request, user: CurrentUser = Depends(_current_inventory_user)):
    search = request.query_params.get("search", "").strip()
    context = get_template_context(request, user)
    context["customers"] = inv_queries.get_customers(active_only=True, search=search or None)
    context["search"] = search
    return templates.TemplateResponse(request, "inventory/customers.html", context)


@router.get("/partials/customer-list", response_class=HTMLResponse)
async def customer_list_partial(request: Request, user: CurrentUser = Depends(_current_inventory_user)):
    search = request.query_params.get("search", "").strip()
    context = get_template_context(request, user)
    context["customers"] = inv_queries.get_customers(active_only=True, search=search or None)
    context["search"] = search
    return templates.TemplateResponse(request, "inventory/partials/customer_list.html", context)


@router.get("/customers/new", response_class=HTMLResponse)
async def customer_new(request: Request, user: CurrentUser = Depends(_current_inventory_user)):
    _require_manager(user)
    context = get_template_context(request, user)
    context["customer"] = None
    context["parents"] = inv_queries.get_parent_customers()
    return templates.TemplateResponse(request, "inventory/customer_form.html", context)


@router.post("/customers", response_class=HTMLResponse)
async def customer_create(
    request: Request,
    user: CurrentUser = Depends(_current_inventory_user),
    name: str = Form(...),
    parent_id: Optional[int] = Form(None),
    primary_contact_username: Optional[str] = Form(None),
    mis_account_id: Optional[int] = Form(None),
    contact_name: Optional[str] = Form(None),
    contact_email: Optional[str] = Form(None),
    count_frequency: str = Form("as_needed"),
    notes: Optional[str] = Form(None),
):
    _require_manager(user)
    data = {
        "name": name.strip(),
        "parent_id": parent_id if parent_id else None,
        "primary_contact_username": (primary_contact_username or "").strip() or None,
        "mis_account_id": mis_account_id if mis_account_id else None,
        "contact_name": (contact_name or "").strip() or None,
        "contact_email": (contact_email or "").strip() or None,
        "count_frequency": count_frequency,
        "notes": (notes or "").strip() or None,
    }
    inv_queries.create_customer(data, _username(user))
    return RedirectResponse("/inventory/customers", status_code=303)


@router.get("/customers/{customer_id}", response_class=HTMLResponse)
async def customer_detail(customer_id: int, request: Request, user: CurrentUser = Depends(_current_inventory_user)):
    customer = inv_queries.get_customer(customer_id)
    if not customer:
        raise HTTPException(404, "Customer not found")
    context = get_template_context(request, user)
    context["customer"] = customer
    context["children"] = inv_queries.get_customer_children(customer_id)
    context["products"] = inv_queries.get_products(customer_id=customer_id, show_retired=True)
    return templates.TemplateResponse(request, "inventory/customer_detail.html", context)


@router.get("/customers/{customer_id}/edit", response_class=HTMLResponse)
async def customer_edit(customer_id: int, request: Request, user: CurrentUser = Depends(_current_inventory_user)):
    _require_manager(user)
    customer = inv_queries.get_customer(customer_id)
    if not customer:
        raise HTTPException(404, "Customer not found")
    context = get_template_context(request, user)
    context["customer"] = customer
    context["parents"] = inv_queries.get_parent_customers()
    return templates.TemplateResponse(request, "inventory/customer_form.html", context)


@router.post("/customers/{customer_id}", response_class=HTMLResponse)
async def customer_update(
    customer_id: int,
    request: Request,
    user: CurrentUser = Depends(_current_inventory_user),
    name: str = Form(...),
    parent_id: Optional[int] = Form(None),
    primary_contact_username: Optional[str] = Form(None),
    mis_account_id: Optional[int] = Form(None),
    contact_name: Optional[str] = Form(None),
    contact_email: Optional[str] = Form(None),
    count_frequency: str = Form("as_needed"),
    notes: Optional[str] = Form(None),
):
    _require_manager(user)
    if not inv_queries.get_customer(customer_id):
        raise HTTPException(404, "Customer not found")
    data = {
        "name": name.strip(),
        "parent_id": parent_id if parent_id else None,
        "primary_contact_username": (primary_contact_username or "").strip() or None,
        "mis_account_id": mis_account_id if mis_account_id else None,
        "contact_name": (contact_name or "").strip() or None,
        "contact_email": (contact_email or "").strip() or None,
        "count_frequency": count_frequency,
        "notes": (notes or "").strip() or None,
    }
    inv_queries.update_customer(customer_id, data, _username(user))
    return RedirectResponse("/inventory/customers", status_code=303)


# =========================================================================
# Products
# =========================================================================


@router.get("/products", response_class=HTMLResponse)
async def product_list(request: Request, user: CurrentUser = Depends(_current_inventory_user)):
    params = request.query_params
    context = get_template_context(request, user)
    filters = _parse_product_filters(params)
    context.update(filters)
    context["products"] = inv_queries.get_products(**filters)
    context["customers_list"] = inv_queries.get_customers(active_only=True)
    context["sites_list"] = inv_queries.get_sites(active_only=True)
    context["zones_list"] = inv_queries.get_zones()
    return templates.TemplateResponse(request, "inventory/products.html", context)


@router.get("/partials/product-list", response_class=HTMLResponse)
async def product_list_partial(request: Request, user: CurrentUser = Depends(_current_inventory_user)):
    params = request.query_params
    context = get_template_context(request, user)
    filters = _parse_product_filters(params)
    context.update(filters)
    context["products"] = inv_queries.get_products(**filters)
    return templates.TemplateResponse(request, "inventory/partials/product_list.html", context)


@router.get("/products/new", response_class=HTMLResponse)
async def product_new(request: Request, user: CurrentUser = Depends(_current_inventory_user)):
    _require_manager(user)
    context = get_template_context(request, user)
    context["product"] = None
    context["customers_list"] = inv_queries.get_customers(active_only=True)
    context["zones_list"] = inv_queries.get_zones()
    return templates.TemplateResponse(request, "inventory/product_form.html", context)


@router.post("/products", response_class=HTMLResponse)
async def product_create(
    request: Request,
    user: CurrentUser = Depends(_current_inventory_user),
    customer_id: int = Form(...),
    zone_id: int = Form(...),
    sku: Optional[str] = Form(None),
    name: str = Form(...),
    description: Optional[str] = Form(None),
    unit_type: str = Form("individual"),
    pack_size: Optional[int] = Form(None),
    quantity: int = Form(0),
    low_threshold: Optional[int] = Form(None),
    cost_per_unit: Optional[float] = Form(None),
    notification_emails: Optional[str] = Form(None),
):
    _require_manager(user)
    data = {
        "customer_id": customer_id,
        "zone_id": zone_id,
        "sku": (sku or "").strip() or None,
        "name": name.strip(),
        "description": (description or "").strip() or None,
        "unit_type": unit_type,
        "pack_size": pack_size if unit_type == "pack" else None,
        "quantity": quantity,
        "low_threshold": low_threshold,
        "cost_per_unit": cost_per_unit,
        "notification_emails": (notification_emails or "").strip() or None,
    }
    inv_queries.create_product(data, _username(user))
    return RedirectResponse("/inventory/products", status_code=303)


@router.get("/products/{product_id}", response_class=HTMLResponse)
async def product_detail(product_id: int, request: Request, user: CurrentUser = Depends(_current_inventory_user)):
    product = inv_queries.get_product(product_id)
    if not product:
        raise HTTPException(404, "Product not found")
    context = get_template_context(request, user)
    context["product"] = product
    context["replacement_options"] = (
        inv_queries.get_active_products_for_customer(product["customer_id"])
        if product["status"] == "active" else []
    )
    if product["status"] == "active" and product["quantity"] > 0:
        context["depletion"] = inv_queries.get_depletion_projection(product_id, product["quantity"])
    else:
        context["depletion"] = None
    return templates.TemplateResponse(request, "inventory/product_detail.html", context)


@router.get("/products/{product_id}/edit", response_class=HTMLResponse)
async def product_edit(product_id: int, request: Request, user: CurrentUser = Depends(_current_inventory_user)):
    _require_manager(user)
    product = inv_queries.get_product(product_id)
    if not product:
        raise HTTPException(404, "Product not found")
    context = get_template_context(request, user)
    context["product"] = product
    context["customers_list"] = inv_queries.get_customers(active_only=True)
    context["zones_list"] = inv_queries.get_zones()
    return templates.TemplateResponse(request, "inventory/product_form.html", context)


@router.post("/products/{product_id}", response_class=HTMLResponse)
async def product_update(
    product_id: int,
    request: Request,
    user: CurrentUser = Depends(_current_inventory_user),
    customer_id: int = Form(...),
    zone_id: int = Form(...),
    name: str = Form(...),
    description: Optional[str] = Form(None),
    unit_type: str = Form("individual"),
    pack_size: Optional[int] = Form(None),
    low_threshold: Optional[int] = Form(None),
    cost_per_unit: Optional[float] = Form(None),
    notification_emails: Optional[str] = Form(None),
):
    _require_manager(user)
    if not inv_queries.get_product(product_id):
        raise HTTPException(404, "Product not found")
    data = {
        "customer_id": customer_id,
        "zone_id": zone_id,
        "name": name.strip(),
        "description": (description or "").strip() or None,
        "unit_type": unit_type,
        "pack_size": pack_size if unit_type == "pack" else None,
        "low_threshold": low_threshold,
        "cost_per_unit": cost_per_unit,
        "notification_emails": (notification_emails or "").strip() or None,
    }
    inv_queries.update_product(product_id, data, _username(user))
    return RedirectResponse(f"/inventory/products/{product_id}", status_code=303)


@router.post("/products/{product_id}/retire", response_class=HTMLResponse)
async def product_retire(
    product_id: int,
    request: Request,
    user: CurrentUser = Depends(_current_inventory_user),
    replaced_by_id: Optional[int] = Form(None),
):
    _require_manager(user)
    product = inv_queries.get_product(product_id)
    if not product:
        raise HTTPException(404, "Product not found")
    if product["status"] == "retired":
        raise HTTPException(400, "Product is already retired")
    inv_queries.retire_product(
        product_id,
        replaced_by_id if replaced_by_id else None,
        _username(user),
    )
    return RedirectResponse(f"/inventory/products/{product_id}", status_code=303)


# =========================================================================
# Scan / Pull / Add
# =========================================================================


@router.get("/scan", response_class=HTMLResponse)
async def scan_page(request: Request, user: CurrentUser = Depends(_current_inventory_user)):
    context = get_template_context(request, user)
    context["pull_warning_pct"] = _pull_warning_pct()
    context["preload_product_id"] = request.query_params.get("product_id", "")
    return templates.TemplateResponse(request, "inventory/scan.html", context)


@router.post("/scan/lookup", response_class=HTMLResponse)
async def scan_lookup(
    request: Request,
    user: CurrentUser = Depends(_current_inventory_user),
    scan_value: str = Form(""),
):
    """HTMX partial: look up product by barcode, SKU, or name."""
    context = get_template_context(request, user)
    value = scan_value.strip()
    if not value:
        context["error"] = "No scan input received."
        return templates.TemplateResponse(request, "inventory/partials/scan_result.html", context)

    product = inv_queries.lookup_product_by_scan(value)
    if product:
        context["product"] = product
        context["pull_warning_pct"] = _pull_warning_pct()
        context["mode"] = "pull"
        return templates.TemplateResponse(request, "inventory/partials/product_action.html", context)

    results = inv_queries.search_products_by_scan(value)
    context["results"] = results
    context["scan_value"] = value
    return templates.TemplateResponse(request, "inventory/partials/scan_result.html", context)


@router.get("/scan/{product_id}", response_class=HTMLResponse)
async def scan_product_direct(
    product_id: int,
    request: Request,
    user: CurrentUser = Depends(_current_inventory_user),
):
    """Load product action panel directly by ID (from search result click)."""
    context = get_template_context(request, user)
    product = inv_queries.get_product(product_id)
    if not product:
        context["error"] = f"Product #{product_id} not found."
        return templates.TemplateResponse(request, "inventory/partials/scan_result.html", context)
    context["product"] = product
    context["pull_warning_pct"] = _pull_warning_pct()
    context["mode"] = "pull"
    return templates.TemplateResponse(request, "inventory/partials/product_action.html", context)


@router.post("/scan/confirm", response_class=HTMLResponse)
async def scan_confirm(
    request: Request,
    user: CurrentUser = Depends(_current_inventory_user),
    product_id: int = Form(...),
    action: str = Form(...),
    quantity: int = Form(...),
    order_reference: Optional[str] = Form(None),
    override_reason: Optional[str] = Form(None),
):
    """HTMX partial: confirmation screen with safeguard warnings."""
    context = get_template_context(request, user)
    product = inv_queries.get_product(product_id)
    if not product:
        context["error"] = "Product not found."
        return templates.TemplateResponse(request, "inventory/partials/scan_result.html", context)

    if quantity <= 0:
        context["product"] = product
        context["pull_warning_pct"] = _pull_warning_pct()
        context["mode"] = action
        context["form_error"] = "Quantity must be greater than zero."
        return templates.TemplateResponse(request, "inventory/partials/product_action.html", context)

    warnings = []
    if action == "pull":
        new_qty = product["quantity"] - quantity
        pct = _pull_warning_pct()
        if product["quantity"] > 0 and quantity > (product["quantity"] * pct / 100):
            warnings.append(
                f"This pull removes more than {pct}% of current stock "
                f"({quantity} of {product['quantity']})."
            )
        if new_qty < 0:
            warnings.append(
                f"This pull will take quantity below zero "
                f"({product['quantity']} - {quantity} = {new_qty})."
            )
    else:
        new_qty = product["quantity"] + quantity

    needs_override = bool(warnings) and not (override_reason or "").strip()

    context["product"] = product
    context["action"] = action
    context["quantity"] = quantity
    context["new_qty"] = new_qty
    context["order_reference"] = (order_reference or "").strip()
    context["override_reason"] = (override_reason or "").strip()
    context["warnings"] = warnings
    context["needs_override"] = needs_override
    context["pull_warning_pct"] = _pull_warning_pct()
    return templates.TemplateResponse(request, "inventory/partials/confirmation.html", context)


@router.post("/pull", response_class=HTMLResponse)
async def execute_pull(
    request: Request,
    background_tasks: BackgroundTasks,
    user: CurrentUser = Depends(_current_inventory_user),
    product_id: int = Form(...),
    quantity: int = Form(...),
    order_reference: Optional[str] = Form(None),
    override_reason: Optional[str] = Form(None),
):
    """Execute stock pull (decrement) with transaction logging."""
    context = get_template_context(request, user)
    product = inv_queries.get_product(product_id)
    if not product:
        context["error"] = "Product not found."
        return templates.TemplateResponse(request, "inventory/partials/scan_result.html", context)

    if quantity <= 0:
        context["product"] = product
        context["pull_warning_pct"] = _pull_warning_pct()
        context["mode"] = "pull"
        context["form_error"] = "Quantity must be greater than zero."
        return templates.TemplateResponse(request, "inventory/partials/product_action.html", context)

    try:
        result = inv_queries.pull_stock(
            product_id=product_id,
            quantity=quantity,
            order_reference=(order_reference or "").strip() or None,
            override_reason=(override_reason or "").strip() or None,
            username=_username(user),
        )
    except ValueError as exc:
        context["product"] = product
        context["pull_warning_pct"] = _pull_warning_pct()
        context["mode"] = "pull"
        context["form_error"] = f"Pull failed: {exc}"
        return templates.TemplateResponse(request, "inventory/partials/product_action.html", context)
    except Exception:
        logging.getLogger(__name__).exception("Unexpected error in pull_stock")
        context["product"] = product
        context["pull_warning_pct"] = _pull_warning_pct()
        context["mode"] = "pull"
        context["form_error"] = "Pull failed due to a system error. Please try again."
        return templates.TemplateResponse(request, "inventory/partials/product_action.html", context)

    context["result"] = result
    context["action"] = "pull"
    context["quantity"] = quantity
    product = inv_queries.get_product(product_id)
    context["product"] = product

    if (
        product
        and product.get("low_threshold") is not None
        and product.get("notification_emails")
        and product["quantity"] <= product["low_threshold"]
    ):
        background_tasks.add_task(email_service.send_low_stock_alert, product)

    return templates.TemplateResponse(request, "inventory/partials/scan_success.html", context)


@router.post("/add", response_class=HTMLResponse)
async def execute_add(
    request: Request,
    background_tasks: BackgroundTasks,
    user: CurrentUser = Depends(_current_inventory_user),
    product_id: int = Form(...),
    quantity: int = Form(...),
    order_reference: Optional[str] = Form(None),
    override_reason: Optional[str] = Form(None),
):
    """Execute stock add (increment) with transaction logging."""
    context = get_template_context(request, user)
    product = inv_queries.get_product(product_id)
    if not product:
        context["error"] = "Product not found."
        return templates.TemplateResponse(request, "inventory/partials/scan_result.html", context)

    if quantity <= 0:
        context["product"] = product
        context["pull_warning_pct"] = _pull_warning_pct()
        context["mode"] = "add"
        context["form_error"] = "Quantity must be greater than zero."
        return templates.TemplateResponse(request, "inventory/partials/product_action.html", context)

    try:
        result = inv_queries.add_stock(
            product_id=product_id,
            quantity=quantity,
            order_reference=(order_reference or "").strip() or None,
            override_reason=(override_reason or "").strip() or None,
            username=_username(user),
        )
    except ValueError as exc:
        context["product"] = product
        context["pull_warning_pct"] = _pull_warning_pct()
        context["mode"] = "add"
        context["form_error"] = f"Add failed: {exc}"
        return templates.TemplateResponse(request, "inventory/partials/product_action.html", context)
    except Exception:
        logging.getLogger(__name__).exception("Unexpected error in add_stock")
        context["product"] = product
        context["pull_warning_pct"] = _pull_warning_pct()
        context["mode"] = "add"
        context["form_error"] = "Add failed due to a system error. Please try again."
        return templates.TemplateResponse(request, "inventory/partials/product_action.html", context)

    context["result"] = result
    context["action"] = "add"
    context["quantity"] = quantity
    product = inv_queries.get_product(product_id)
    context["product"] = product

    if (
        product
        and product.get("low_threshold") is not None
        and product.get("notification_emails")
        and result["quantity_before"] <= product["low_threshold"]
        and product["quantity"] > product["low_threshold"]
    ):
        background_tasks.add_task(email_service.send_restock_confirmation, product)

    return templates.TemplateResponse(request, "inventory/partials/scan_success.html", context)


# =========================================================================
# Transactions
# =========================================================================


@router.get("/products/{product_id}/transactions", response_class=HTMLResponse)
async def product_transactions(
    product_id: int,
    request: Request,
    user: CurrentUser = Depends(_current_inventory_user),
):
    product = inv_queries.get_product(product_id)
    if not product:
        raise HTTPException(404, "Product not found")
    context = get_template_context(request, user)
    context["product"] = product
    context["transactions"] = inv_queries.get_product_transactions(product_id)
    return templates.TemplateResponse(request, "inventory/transactions.html", context)


# =========================================================================
# CSV Import
# =========================================================================

_CSV_TEMPLATE_COLUMNS = [
    "customer_name", "program", "site", "zone", "sku", "product_name",
    "description", "unit_type", "pack_size", "quantity", "low_threshold",
    "cost_per_unit", "notification_emails",
]

_CSV_TEMPLATE_INSTRUCTIONS = [
    "# Retriever Inventory - Product Import Template",
    "# Fill in one product per row below the header line.",
    "# customer_name: REQUIRED. Must match an existing customer name exactly.",
    "# program: Optional sub-program name (child customer). Leave blank if N/A.",
    "# site: REQUIRED. Must match an existing site name (e.g. Goleta, SLO).",
    "# zone: REQUIRED. Must match an existing zone name at the given site.",
    "# sku: Optional. Auto-generated (INV-0001) if left blank.",
    "# product_name: REQUIRED.",
    "# unit_type: 'individual' or 'pack'. Defaults to 'individual'.",
    "# pack_size: Required when unit_type is 'pack'. Number of items per pack.",
    "# quantity, low_threshold, cost_per_unit: Numeric. Commas OK (e.g. 1,000).",
    "# notification_emails: Comma-separated email addresses for low-stock alerts.",
    "# Values like 'n/a', 'N/A', 'TBD', '-' are treated as blank.",
    "",
]


@router.get("/import", response_class=HTMLResponse)
async def import_page(request: Request, user: CurrentUser = Depends(_current_inventory_user)):
    _require_manager(user)
    context = get_template_context(request, user)
    return templates.TemplateResponse(request, "inventory/import.html", context)


@router.get("/import/template")
async def import_template_download(user: CurrentUser = Depends(_current_inventory_user)):
    """Download the CSV template with instruction rows."""
    _require_manager(user)
    buf = io.StringIO()
    for line in _CSV_TEMPLATE_INSTRUCTIONS:
        buf.write(line + "\n")
    writer = csv.writer(buf)
    writer.writerow(_CSV_TEMPLATE_COLUMNS)
    writer.writerow([
        "Mechanics Bank", "", "Goleta", "Warehouse", "",
        "Business Cards - Main Branch", "Standard 250ct box", "pack", "250",
        "500", "100", "0.04", "warehouse@example.com",
    ])
    content = buf.getvalue()
    buf.close()
    return StreamingResponse(
        iter([content]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=inventory_import_template.csv"},
    )


@router.post("/import/upload", response_class=HTMLResponse)
async def import_upload(
    request: Request,
    user: CurrentUser = Depends(_current_inventory_user),
    file: UploadFile = File(...),
):
    """Parse uploaded CSV, validate, and show preview."""
    _require_manager(user)
    context = get_template_context(request, user)

    if not file.filename or not file.filename.lower().endswith(".csv"):
        context["upload_error"] = "Please upload a .csv file."
        return templates.TemplateResponse(request, "inventory/import.html", context)

    max_upload_bytes = 5 * 1024 * 1024  # 5 MB
    raw = await file.read()
    if len(raw) > max_upload_bytes:
        context["upload_error"] = "File too large (max 5 MB)."
        return templates.TemplateResponse(request, "inventory/import.html", context)
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")

    rows, errors, warnings = _parse_import_csv(text, _username(user))

    context["parsed_rows"] = rows
    context["parse_errors"] = errors
    context["parse_warnings"] = warnings
    context["valid_count"] = sum(1 for r in rows if not r.get("_errors"))
    context["error_count"] = sum(1 for r in rows if r.get("_errors"))
    context["rows_json"] = json.dumps([r for r in rows if not r.get("_errors")], default=str)
    return templates.TemplateResponse(request, "inventory/import_preview.html", context)


@router.post("/import/commit", response_class=HTMLResponse)
async def import_commit(
    request: Request,
    user: CurrentUser = Depends(_current_inventory_user),
    rows_json: str = Form(...),
):
    """Commit validated rows from the preview step."""
    _require_manager(user)
    context = get_template_context(request, user)

    try:
        rows = json.loads(rows_json)
    except (json.JSONDecodeError, TypeError):
        context["upload_error"] = "Invalid import data. Please re-upload the CSV."
        return templates.TemplateResponse(request, "inventory/import.html", context)

    if not rows:
        context["upload_error"] = "No valid rows to import."
        return templates.TemplateResponse(request, "inventory/import.html", context)

    product_rows = []
    for r in rows:
        product_rows.append({
            "customer_id": r["customer_id"],
            "zone_id": r["zone_id"],
            "sku": r.get("sku") or None,
            "name": r["product_name"],
            "description": r.get("description") or None,
            "unit_type": r.get("unit_type", "individual"),
            "pack_size": r.get("pack_size") or None,
            "quantity": r.get("quantity", 0),
            "low_threshold": r.get("low_threshold") or None,
            "cost_per_unit": r.get("cost_per_unit") or None,
            "notification_emails": r.get("notification_emails") or None,
        })

    try:
        created = inv_queries.bulk_create_products(product_rows, _username(user))
    except Exception:
        logging.getLogger(__name__).exception("Unexpected error in bulk_create_products")
        context["upload_error"] = "Import failed due to a system error. Please try again."
        return templates.TemplateResponse(request, "inventory/import.html", context)

    context["import_success"] = True
    context["created_count"] = created
    return templates.TemplateResponse(request, "inventory/import.html", context)


# =========================================================================
# Shelf Tags
# =========================================================================


@router.get("/tags", response_class=HTMLResponse)
async def tags_page(request: Request, user: CurrentUser = Depends(_current_inventory_user)):
    _require_manager(user)
    context = get_template_context(request, user)
    context["customers_list"] = inv_queries.get_customers(active_only=True)
    context["products_list"] = inv_queries.get_products()
    return templates.TemplateResponse(request, "inventory/tags.html", context)


@router.post("/tags/generate")
async def tags_generate(
    request: Request,
    user: CurrentUser = Depends(_current_inventory_user),
    scope: str = Form(...),
    product_id: Optional[str] = Form(None),
    customer_id: Optional[str] = Form(None),
):
    """Generate shelf-tag PDF for the requested scope."""
    _require_manager(user)

    pid = int(product_id) if product_id and product_id.strip().isdigit() else None
    cid = int(customer_id) if customer_id and customer_id.strip().isdigit() else None

    products = []
    filename = "shelf_tags.pdf"

    if scope == "product" and pid:
        product = inv_queries.get_product(pid)
        if not product:
            raise HTTPException(404, "Product not found")
        products = [product]
        filename = f"tag_{product['sku']}.pdf"

    elif scope == "customer" and cid:
        products = inv_queries.get_products(customer_id=cid)
        customer = inv_queries.get_customer(cid)
        if customer:
            safe_name = customer["name"].replace(" ", "_")[:30]
            filename = f"tags_{safe_name}.pdf"

    elif scope == "all":
        products = inv_queries.get_all_active_products()
        filename = "tags_all_products.pdf"

    else:
        raise HTTPException(400, "Invalid scope or missing selection")

    if not products:
        raise HTTPException(404, "No products found for the selected scope")

    pdf_bytes = generate_tags_pdf(products)
    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# =========================================================================
# Physical Counts
# =========================================================================


@router.get("/counts", response_class=HTMLResponse)
async def count_list(request: Request, user: CurrentUser = Depends(_current_inventory_user)):
    _require_manager(user)
    context = get_template_context(request, user)
    context["counts"] = inv_queries.get_counts()
    return templates.TemplateResponse(request, "inventory/counts.html", context)


@router.get("/counts/new", response_class=HTMLResponse)
async def count_new(request: Request, user: CurrentUser = Depends(_current_inventory_user)):
    _require_manager(user)
    context = get_template_context(request, user)
    context["sites"] = inv_queries.get_sites(active_only=True)
    context["zones"] = inv_queries.get_zones()
    context["customers_list"] = inv_queries.get_customers(active_only=True)
    return templates.TemplateResponse(request, "inventory/count_form.html", context)


@router.post("/counts", response_class=HTMLResponse)
async def count_create(request: Request, user: CurrentUser = Depends(_current_inventory_user)):
    _require_manager(user)
    form = await request.form()

    scopes = []
    for key, value in form.multi_items():
        if key == "site_id" and value:
            scopes.append({"scope_type": "site", "scope_id": int(value)})
        elif key == "zone_id" and value:
            scopes.append({"scope_type": "zone", "scope_id": int(value)})
        elif key == "customer_id" and value:
            scopes.append({"scope_type": "customer", "scope_id": int(value)})

    if not scopes:
        context = get_template_context(request, user)
        context["sites"] = inv_queries.get_sites(active_only=True)
        context["zones"] = inv_queries.get_zones()
        context["customers_list"] = inv_queries.get_customers(active_only=True)
        context["form_error"] = "Select at least one site, zone, or customer."
        return templates.TemplateResponse(request, "inventory/count_form.html", context)

    scope_desc = form.get("scope_description", "").strip() or "Physical count"
    threshold = int(form.get("discrepancy_threshold_pct", "20") or "20")

    try:
        count_id = inv_queries.create_count(
            initiated_by=_username(user),
            scope_description=scope_desc,
            threshold_pct=threshold,
            scopes=scopes,
        )
    except ValueError as exc:
        context = get_template_context(request, user)
        context["sites"] = inv_queries.get_sites(active_only=True)
        context["zones"] = inv_queries.get_zones()
        context["customers_list"] = inv_queries.get_customers(active_only=True)
        context["form_error"] = str(exc)
        return templates.TemplateResponse(request, "inventory/count_form.html", context)

    return RedirectResponse(f"/inventory/counts/{count_id}", status_code=303)


@router.get("/counts/{count_id}", response_class=HTMLResponse)
async def count_detail(count_id: int, request: Request, user: CurrentUser = Depends(_current_inventory_user)):
    count = inv_queries.get_count(count_id)
    if not count:
        raise HTTPException(404, "Count not found")
    context = get_template_context(request, user)
    context["count"] = count
    context["items"] = inv_queries.get_count_items(count_id)
    return templates.TemplateResponse(request, "inventory/count_detail.html", context)


@router.post("/counts/{count_id}/items/{item_id}", response_class=HTMLResponse)
async def count_item_save(
    count_id: int,
    item_id: int,
    request: Request,
    user: CurrentUser = Depends(_current_inventory_user),
    counted_quantity: int = Form(...),
):
    """Save counted quantity for one item (HTMX partial swap)."""
    if counted_quantity < 0:
        raise HTTPException(400, "Counted quantity cannot be negative")
    count = inv_queries.get_count(count_id)
    if not count or count["status"] != "in_progress":
        raise HTTPException(400, "Count is not in progress")

    inv_queries.update_count_item(
        item_id=item_id,
        counted_quantity=counted_quantity,
        counted_by=_username(user),
        threshold_pct=count["discrepancy_threshold_pct"],
    )
    context = get_template_context(request, user)
    context["count"] = count
    context["item"] = inv_queries.get_count_item(item_id)
    return templates.TemplateResponse(request, "inventory/partials/count_item_row.html", context)


@router.post("/counts/{count_id}/review", response_class=HTMLResponse)
async def count_move_review(
    count_id: int, request: Request, user: CurrentUser = Depends(_current_inventory_user),
):
    _require_manager(user)
    count = inv_queries.get_count(count_id)
    if not count or count["status"] != "in_progress":
        raise HTTPException(400, "Count is not in progress")
    inv_queries.move_count_to_review(count_id)
    return RedirectResponse(f"/inventory/counts/{count_id}/review", status_code=303)


@router.get("/counts/{count_id}/review", response_class=HTMLResponse)
async def count_review_page(
    count_id: int, request: Request, user: CurrentUser = Depends(_current_inventory_user),
):
    _require_manager(user)
    count = inv_queries.get_count(count_id)
    if not count:
        raise HTTPException(404, "Count not found")
    context = get_template_context(request, user)
    context["count"] = count
    context["flagged_items"] = inv_queries.get_count_items(count_id, flagged_only=True)
    context["all_items"] = inv_queries.get_count_items(count_id)
    return templates.TemplateResponse(request, "inventory/count_review.html", context)


@router.post("/counts/{count_id}/approve/{item_id}", response_class=HTMLResponse)
async def count_approve_item(
    count_id: int,
    item_id: int,
    request: Request,
    user: CurrentUser = Depends(_current_inventory_user),
    approved: str = Form("true"),
):
    _require_manager(user)
    inv_queries.approve_count_item(
        item_id=item_id,
        approved=approved == "true",
        approved_by=_username(user),
    )
    context = get_template_context(request, user)
    context["count"] = inv_queries.get_count(count_id)
    context["item"] = inv_queries.get_count_item(item_id)
    return templates.TemplateResponse(request, "inventory/partials/count_review_item.html", context)


@router.post("/counts/{count_id}/complete", response_class=HTMLResponse)
async def count_complete(
    count_id: int, request: Request, user: CurrentUser = Depends(_current_inventory_user),
):
    _require_manager(user)
    count = inv_queries.get_count(count_id)
    if not count or count["status"] not in ("in_progress", "review"):
        raise HTTPException(400, "Count cannot be completed")
    try:
        inv_queries.complete_count(count_id, _username(user))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return RedirectResponse(f"/inventory/counts/{count_id}", status_code=303)


@router.post("/counts/{count_id}/cancel", response_class=HTMLResponse)
async def count_cancel(
    count_id: int, request: Request, user: CurrentUser = Depends(_current_inventory_user),
):
    _require_manager(user)
    count = inv_queries.get_count(count_id)
    if not count or count["status"] not in ("in_progress", "review"):
        raise HTTPException(400, "Count cannot be canceled")
    inv_queries.cancel_count(count_id, _username(user))
    return RedirectResponse("/inventory/counts", status_code=303)


# =========================================================================
# Helpers
# =========================================================================


_STRIP_VALUES = {"n/a", "na", "tbd", "-", "—", "none", "null", ""}


def _clean_cell(value: str) -> str:
    """Strip whitespace; replace junk tokens with empty string."""
    value = value.strip()
    if value.lower() in _STRIP_VALUES:
        return ""
    return value


def _clean_number(value: str) -> Optional[float]:
    """Parse a numeric string, handling commas, decimals, and junk values."""
    value = _clean_cell(value)
    if not value:
        return None
    value = value.replace(",", "").replace("$", "").strip()
    try:
        return float(value)
    except ValueError:
        return None


def _clean_int(value: str) -> Optional[int]:
    """Parse an integer string, rounding decimals."""
    num = _clean_number(value)
    if num is None:
        return None
    return round(num)


def _parse_import_csv(
    text: str, username: str,
) -> tuple:
    """Parse CSV text and validate each row.

    Returns (rows, global_errors, global_warnings) where each row dict
    includes _errors list (empty if valid) and resolved IDs.
    """
    lines = text.splitlines()
    data_lines = [ln for ln in lines if not ln.startswith("#")]
    if not data_lines:
        return [], ["CSV file is empty or contains only comment lines."], []

    reader = csv.DictReader(io.StringIO("\n".join(data_lines)))
    if not reader.fieldnames:
        return [], ["Could not detect CSV column headers."], []

    normalized_fields = {f.strip().lower().replace(" ", "_"): f for f in reader.fieldnames}
    required_cols = {"customer_name", "product_name", "site", "zone"}
    missing_cols = required_cols - set(normalized_fields.keys())
    if missing_cols:
        return [], [f"Missing required columns: {', '.join(sorted(missing_cols))}"], []

    field_map = {}
    for expected in _CSV_TEMPLATE_COLUMNS:
        for norm_key, orig_key in normalized_fields.items():
            if norm_key == expected:
                field_map[expected] = orig_key
                break

    global_warnings: List[str] = []
    rows: List[Dict[str, Any]] = []
    seen_skus: set = set()
    blank_rows_skipped = 0

    for row_num, raw_row in enumerate(reader, start=2):
        customer_raw = _clean_cell(raw_row.get(field_map.get("customer_name", "customer_name"), ""))
        product_raw = _clean_cell(raw_row.get(field_map.get("product_name", "product_name"), ""))

        if not customer_raw and not product_raw:
            blank_rows_skipped += 1
            continue

        row_errors: List[str] = []
        parsed: Dict[str, Any] = {"_row": row_num}

        if not customer_raw:
            row_errors.append("customer_name is required")
        if not product_raw:
            row_errors.append("product_name is required")

        parsed["product_name"] = product_raw

        program_raw = _clean_cell(raw_row.get(field_map.get("program", "program"), ""))
        site_raw = _clean_cell(raw_row.get(field_map.get("site", "site"), ""))
        zone_raw = _clean_cell(raw_row.get(field_map.get("zone", "zone"), ""))

        if not site_raw:
            row_errors.append("site is required")
        if not zone_raw:
            row_errors.append("zone is required")

        customer_id = None
        if customer_raw:
            if program_raw:
                cust = inv_queries.find_customer_by_name(program_raw)
                if not cust:
                    cust = inv_queries.find_customer_by_name(customer_raw)
                    if not cust:
                        row_errors.append(f"Customer '{customer_raw}' not found")
                    else:
                        row_errors.append(f"Sub-program '{program_raw}' not found under '{customer_raw}'")
                else:
                    customer_id = cust["id"]
            else:
                cust = inv_queries.find_customer_by_name(customer_raw)
                if not cust:
                    row_errors.append(f"Customer '{customer_raw}' not found")
                else:
                    customer_id = cust["id"]
        parsed["customer_id"] = customer_id
        parsed["customer_name"] = program_raw or customer_raw

        site_id = None
        if site_raw:
            site = inv_queries.find_site_by_name(site_raw)
            if not site:
                row_errors.append(f"Site '{site_raw}' not found")
            else:
                site_id = site["id"]
        parsed["site_name"] = site_raw

        zone_id = None
        if zone_raw and site_id:
            zone = inv_queries.find_zone_by_name(zone_raw, site_id)
            if not zone:
                row_errors.append(f"Zone '{zone_raw}' not found at site '{site_raw}'")
            else:
                zone_id = zone["id"]
        elif zone_raw and not site_id:
            pass
        parsed["zone_id"] = zone_id
        parsed["zone_name"] = zone_raw

        sku_raw = _clean_cell(raw_row.get(field_map.get("sku", "sku"), ""))
        if sku_raw:
            if sku_raw in seen_skus:
                row_errors.append(f"Duplicate SKU '{sku_raw}' in this file")
            elif inv_queries.sku_exists(sku_raw):
                row_errors.append(f"SKU '{sku_raw}' already exists in database")
            else:
                seen_skus.add(sku_raw)
        parsed["sku"] = sku_raw or None

        desc_raw = _clean_cell(raw_row.get(field_map.get("description", "description"), ""))
        parsed["description"] = desc_raw or None

        unit_type_raw = _clean_cell(raw_row.get(field_map.get("unit_type", "unit_type"), "")).lower()
        if unit_type_raw in ("pack", "packs"):
            parsed["unit_type"] = "pack"
        else:
            parsed["unit_type"] = "individual"

        pack_size_raw = raw_row.get(field_map.get("pack_size", "pack_size"), "")
        parsed["pack_size"] = _clean_int(pack_size_raw) if parsed["unit_type"] == "pack" else None
        if parsed["unit_type"] == "pack" and not parsed["pack_size"]:
            row_errors.append("pack_size is required when unit_type is 'pack'")

        parsed["quantity"] = _clean_int(raw_row.get(field_map.get("quantity", "quantity"), "")) or 0
        parsed["low_threshold"] = _clean_int(raw_row.get(field_map.get("low_threshold", "low_threshold"), ""))
        parsed["cost_per_unit"] = _clean_number(raw_row.get(field_map.get("cost_per_unit", "cost_per_unit"), ""))

        emails_raw = _clean_cell(raw_row.get(field_map.get("notification_emails", "notification_emails"), ""))
        parsed["notification_emails"] = emails_raw or None

        parsed["_errors"] = row_errors
        rows.append(parsed)

    if blank_rows_skipped:
        global_warnings.append(f"{blank_rows_skipped} blank row(s) skipped.")

    return rows, [], global_warnings


def _parse_product_filters(params) -> dict:
    customer_id = params.get("customer_id")
    site_id = params.get("site_id")
    zone_id = params.get("zone_id")
    search = params.get("search", "").strip()
    show_retired = params.get("show_retired") == "1"
    return {
        "customer_id": int(customer_id) if customer_id else None,
        "site_id": int(site_id) if site_id else None,
        "zone_id": int(zone_id) if zone_id else None,
        "search": search or None,
        "show_retired": show_retired,
    }
