"""
Inventory-Specific Database Queries

Retriever Inventory stores all data in MySQL schema retriever_inventory
on 192.168.33.243 (same server as pm_review, retriever_core, retriever_prepress).

MIS reads are limited to optional customer-to-account lookups (read-only).
"""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from app.auth.permissions import CurrentUser
from app.config import get_settings
from app.database.mysql_client import get_mysql_client

logger = logging.getLogger(__name__)

def is_manager(user: CurrentUser) -> bool:
    """Return True if user has manager-tier access (CRUD, counts, tags)."""
    return user.can_manage_inventory()


def _get_inventory_connection():
    """Get a MySQL connection to the retriever_inventory schema."""
    client = get_mysql_client()
    return client.get_connection(get_settings().inventory_mysql_database)


def _fetch_all(
    query: str,
    params: Optional[Tuple[Any, ...]] = None,
) -> List[Dict[str, Any]]:
    """Execute a SELECT and return rows as list of dicts."""
    conn = _get_inventory_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(query, params or ())
        rows = cursor.fetchall()
        cursor.close()
        return rows or []
    finally:
        conn.close()


def _fetch_one(
    query: str,
    params: Optional[Tuple[Any, ...]] = None,
) -> Optional[Dict[str, Any]]:
    """Execute a SELECT and return a single row as dict, or None."""
    conn = _get_inventory_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(query, params or ())
        row = cursor.fetchone()
        cursor.close()
        return row
    finally:
        conn.close()


def _execute(
    query: str,
    params: Optional[Tuple[Any, ...]] = None,
) -> int:
    """Execute an INSERT/UPDATE/DELETE and return lastrowid (for INSERT) or rowcount."""
    conn = _get_inventory_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(query, params or ())
        result = cursor.lastrowid or cursor.rowcount
        cursor.close()
        return result
    finally:
        conn.close()


# =========================================================================
# Site queries
# =========================================================================


def get_sites(active_only: bool = False) -> List[Dict[str, Any]]:
    """Return all sites, optionally filtered to active only."""
    q = "SELECT * FROM sites"
    if active_only:
        q += " WHERE active = TRUE"
    q += " ORDER BY name"
    return _fetch_all(q)


def get_site(site_id: int) -> Optional[Dict[str, Any]]:
    """Return a single site by ID, or None."""
    return _fetch_one("SELECT * FROM sites WHERE id = %s", (site_id,))


def create_site(name: str, address: Optional[str], username: str) -> int:
    """Insert a new site and log an audit event. Returns the new site ID."""
    site_id = _execute(
        "INSERT INTO sites (name, address) VALUES (%s, %s)",
        (name, address),
    )
    log_audit("site", site_id, "created", None, username)
    return site_id


def update_site(
    site_id: int, name: str, address: Optional[str], username: str,
) -> None:
    """Update a site's fields and log an audit event if anything changed."""
    old = get_site(site_id)
    _execute(
        "UPDATE sites SET name = %s, address = %s WHERE id = %s",
        (name, address, site_id),
    )
    changes = _diff_fields(old, {"name": name, "address": address})
    if changes:
        log_audit("site", site_id, "updated", changes, username)


# =========================================================================
# Zone queries
# =========================================================================


def get_zones(site_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Return zones with site name, optionally filtered to a single site."""
    if site_id:
        return _fetch_all(
            "SELECT z.*, s.name AS site_name FROM zones z "
            "JOIN sites s ON s.id = z.site_id "
            "WHERE z.site_id = %s ORDER BY z.name",
            (site_id,),
        )
    return _fetch_all(
        "SELECT z.*, s.name AS site_name FROM zones z "
        "JOIN sites s ON s.id = z.site_id "
        "ORDER BY s.name, z.name"
    )


def get_zone(zone_id: int) -> Optional[Dict[str, Any]]:
    """Return a single zone with its site name, or None."""
    return _fetch_one(
        "SELECT z.*, s.name AS site_name FROM zones z "
        "JOIN sites s ON s.id = z.site_id "
        "WHERE z.id = %s",
        (zone_id,),
    )


def get_zones_for_site(site_id: int) -> List[Dict[str, Any]]:
    """Return active zones belonging to a specific site."""
    return _fetch_all(
        "SELECT * FROM zones WHERE site_id = %s AND active = TRUE ORDER BY name",
        (site_id,),
    )


def create_zone(
    site_id: int, name: str, description: Optional[str], username: str,
) -> int:
    """Insert a new zone under a site and log an audit event. Returns the new zone ID."""
    zone_id = _execute(
        "INSERT INTO zones (site_id, name, description) VALUES (%s, %s, %s)",
        (site_id, name, description),
    )
    log_audit("zone", zone_id, "created", None, username)
    return zone_id


def update_zone(
    zone_id: int, name: str, description: Optional[str], username: str,
) -> None:
    """Update a zone's fields and log an audit event if anything changed."""
    old = get_zone(zone_id)
    _execute(
        "UPDATE zones SET name = %s, description = %s WHERE id = %s",
        (name, description, zone_id),
    )
    changes = _diff_fields(old, {"name": name, "description": description})
    if changes:
        log_audit("zone", zone_id, "updated", changes, username)


# =========================================================================
# Customer queries
# =========================================================================


def get_customers(
    active_only: bool = True, search: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Return customers with parent name, optionally filtered by active status and search term."""
    q = (
        "SELECT c.*, p.name AS parent_name "
        "FROM customers c "
        "LEFT JOIN customers p ON p.id = c.parent_id "
        "WHERE 1=1"
    )
    params: list = []
    if active_only:
        q += " AND c.active = TRUE"
    if search:
        q += " AND c.name LIKE %s"
        params.append(f"%{search}%")
    q += " ORDER BY COALESCE(p.name, c.name), c.parent_id IS NULL DESC, c.name"
    return _fetch_all(q, tuple(params))


def get_customer(customer_id: int) -> Optional[Dict[str, Any]]:
    """Return a single customer with parent name, or None."""
    return _fetch_one(
        "SELECT c.*, p.name AS parent_name "
        "FROM customers c "
        "LEFT JOIN customers p ON p.id = c.parent_id "
        "WHERE c.id = %s",
        (customer_id,),
    )


def get_customer_children(parent_id: int) -> List[Dict[str, Any]]:
    """Return child customers (sub-programs) for a given parent."""
    return _fetch_all(
        "SELECT * FROM customers WHERE parent_id = %s ORDER BY name",
        (parent_id,),
    )


def get_parent_customers() -> List[Dict[str, Any]]:
    """Top-level customers (no parent) for use in dropdowns."""
    return _fetch_all(
        "SELECT id, name FROM customers WHERE parent_id IS NULL AND active = TRUE "
        "ORDER BY name"
    )


def create_customer(data: Dict[str, Any], username: str) -> int:
    """Insert a new customer and log an audit event. Returns the new customer ID."""
    cust_id = _execute(
        "INSERT INTO customers "
        "(name, parent_id, primary_contact_username, mis_account_id, "
        " contact_name, contact_email, count_frequency, notes) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        (
            data["name"],
            data.get("parent_id") or None,
            data.get("primary_contact_username") or None,
            data.get("mis_account_id") or None,
            data.get("contact_name") or None,
            data.get("contact_email") or None,
            data.get("count_frequency", "as_needed"),
            data.get("notes") or None,
        ),
    )
    log_audit("customer", cust_id, "created", None, username)
    return cust_id


def update_customer(customer_id: int, data: Dict[str, Any], username: str) -> None:
    """Update a customer's fields and log an audit event if anything changed."""
    old = get_customer(customer_id)
    _execute(
        "UPDATE customers SET "
        "name = %s, parent_id = %s, primary_contact_username = %s, "
        "mis_account_id = %s, contact_name = %s, contact_email = %s, "
        "count_frequency = %s, notes = %s "
        "WHERE id = %s",
        (
            data["name"],
            data.get("parent_id") or None,
            data.get("primary_contact_username") or None,
            data.get("mis_account_id") or None,
            data.get("contact_name") or None,
            data.get("contact_email") or None,
            data.get("count_frequency", "as_needed"),
            data.get("notes") or None,
            customer_id,
        ),
    )
    new_fields = {
        "name": data["name"],
        "parent_id": data.get("parent_id") or None,
        "primary_contact_username": data.get("primary_contact_username") or None,
        "mis_account_id": data.get("mis_account_id") or None,
        "contact_name": data.get("contact_name") or None,
        "contact_email": data.get("contact_email") or None,
        "count_frequency": data.get("count_frequency", "as_needed"),
        "notes": data.get("notes") or None,
    }
    changes = _diff_fields(old, new_fields)
    if changes:
        log_audit("customer", customer_id, "updated", changes, username)


# =========================================================================
# Product queries
# =========================================================================


def generate_next_sku() -> str:
    """Generate the next auto-incremented SKU in INV-NNNN format."""
    row = _fetch_one(
        "SELECT MAX(CAST(SUBSTRING(sku, 5) AS UNSIGNED)) AS max_num "
        "FROM products WHERE sku LIKE 'INV-%%'"
    )
    next_num = (row["max_num"] or 0) + 1 if row else 1
    return f"INV-{next_num:04d}"


def get_products(
    customer_id: Optional[int] = None,
    site_id: Optional[int] = None,
    zone_id: Optional[int] = None,
    search: Optional[str] = None,
    show_retired: bool = False,
) -> List[Dict[str, Any]]:
    """Return products with customer/zone/site joins, filterable by multiple criteria."""
    q = (
        "SELECT p.*, c.name AS customer_name, z.name AS zone_name, "
        "s.name AS site_name "
        "FROM products p "
        "JOIN customers c ON c.id = p.customer_id "
        "JOIN zones z ON z.id = p.zone_id "
        "JOIN sites s ON s.id = z.site_id "
        "WHERE 1=1"
    )
    params: list = []
    if not show_retired:
        q += " AND p.status = 'active'"
    if customer_id:
        q += " AND p.customer_id = %s"
        params.append(customer_id)
    if site_id:
        q += " AND z.site_id = %s"
        params.append(site_id)
    if zone_id:
        q += " AND p.zone_id = %s"
        params.append(zone_id)
    if search:
        q += " AND (p.name LIKE %s OR p.sku LIKE %s)"
        params.extend([f"%{search}%", f"%{search}%"])
    q += " ORDER BY c.name, p.name"
    return _fetch_all(q, tuple(params))


def get_product(product_id: int) -> Optional[Dict[str, Any]]:
    """Return a single product with customer/zone/site/replacement joins, or None."""
    return _fetch_one(
        "SELECT p.*, c.name AS customer_name, c.primary_contact_username, "
        "z.name AS zone_name, s.name AS site_name, z.site_id, "
        "rb.name AS replaced_by_name, rb.sku AS replaced_by_sku "
        "FROM products p "
        "JOIN customers c ON c.id = p.customer_id "
        "JOIN zones z ON z.id = p.zone_id "
        "JOIN sites s ON s.id = z.site_id "
        "LEFT JOIN products rb ON rb.id = p.replaced_by_id "
        "WHERE p.id = %s",
        (product_id,),
    )


def get_active_products_for_customer(customer_id: int) -> List[Dict[str, Any]]:
    """Return active products for a customer (id, sku, name only), for dropdowns."""
    return _fetch_all(
        "SELECT id, sku, name FROM products "
        "WHERE customer_id = %s AND status = 'active' ORDER BY name",
        (customer_id,),
    )


def get_all_active_products() -> List[Dict[str, Any]]:
    """All active products with customer/zone/site joins, for tag generation."""
    return _fetch_all(
        "SELECT p.*, c.name AS customer_name, z.name AS zone_name, "
        "s.name AS site_name "
        "FROM products p "
        "JOIN customers c ON c.id = p.customer_id "
        "JOIN zones z ON z.id = p.zone_id "
        "JOIN sites s ON s.id = z.site_id "
        "WHERE p.status = 'active' "
        "ORDER BY c.name, p.name"
    )


def create_product(data: Dict[str, Any], username: str) -> int:
    """Insert a new product (auto-generating SKU if not provided) and log an audit event."""
    sku = data.get("sku") or generate_next_sku()
    prod_id = _execute(
        "INSERT INTO products "
        "(customer_id, zone_id, sku, name, description, unit_type, "
        " pack_size, quantity, low_threshold, cost_per_unit, "
        " notification_emails, created_by) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (
            data["customer_id"],
            data["zone_id"],
            sku,
            data["name"],
            data.get("description") or None,
            data.get("unit_type", "individual"),
            data.get("pack_size") or None,
            data.get("quantity", 0),
            data.get("low_threshold") or None,
            data.get("cost_per_unit") or None,
            data.get("notification_emails") or None,
            username,
        ),
    )
    log_audit("product", prod_id, "created", None, username)
    return prod_id


def update_product(product_id: int, data: Dict[str, Any], username: str) -> None:
    """Update a product's fields and log an audit event if anything changed."""
    old = get_product(product_id)
    _execute(
        "UPDATE products SET "
        "customer_id = %s, zone_id = %s, name = %s, description = %s, "
        "unit_type = %s, pack_size = %s, low_threshold = %s, "
        "cost_per_unit = %s, notification_emails = %s "
        "WHERE id = %s",
        (
            data["customer_id"],
            data["zone_id"],
            data["name"],
            data.get("description") or None,
            data.get("unit_type", "individual"),
            data.get("pack_size") or None,
            data.get("low_threshold") or None,
            data.get("cost_per_unit") or None,
            data.get("notification_emails") or None,
            product_id,
        ),
    )
    new_fields = {
        "customer_id": data["customer_id"],
        "zone_id": data["zone_id"],
        "name": data["name"],
        "description": data.get("description") or None,
        "unit_type": data.get("unit_type", "individual"),
        "pack_size": data.get("pack_size") or None,
        "low_threshold": data.get("low_threshold") or None,
        "cost_per_unit": data.get("cost_per_unit") or None,
        "notification_emails": data.get("notification_emails") or None,
    }
    changes = _diff_fields(old, new_fields)
    if changes:
        log_audit("product", product_id, "updated", changes, username)


def retire_product(
    product_id: int,
    replaced_by_id: Optional[int],
    username: str,
) -> None:
    """Set a product to retired status with optional replacement link."""
    _execute(
        "UPDATE products SET status = 'retired', replaced_by_id = %s WHERE id = %s",
        (replaced_by_id, product_id),
    )
    log_audit(
        "product", product_id, "retired",
        {"replaced_by_id": replaced_by_id},
        username,
    )


def find_customer_by_name(name: str) -> Optional[Dict[str, Any]]:
    """Case-insensitive customer lookup by exact name."""
    return _fetch_one(
        "SELECT id, name, parent_id FROM customers "
        "WHERE LOWER(name) = LOWER(%s) AND active = TRUE",
        (name,),
    )


def find_site_by_name(name: str) -> Optional[Dict[str, Any]]:
    """Case-insensitive site lookup by exact name."""
    return _fetch_one(
        "SELECT id, name FROM sites WHERE LOWER(name) = LOWER(%s) AND active = TRUE",
        (name,),
    )


def find_zone_by_name(name: str, site_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """Case-insensitive zone lookup, optionally scoped to a site."""
    if site_id:
        return _fetch_one(
            "SELECT z.id, z.name, z.site_id, s.name AS site_name "
            "FROM zones z JOIN sites s ON s.id = z.site_id "
            "WHERE LOWER(z.name) = LOWER(%s) AND z.site_id = %s AND z.active = TRUE",
            (name, site_id),
        )
    return _fetch_one(
        "SELECT z.id, z.name, z.site_id, s.name AS site_name "
        "FROM zones z JOIN sites s ON s.id = z.site_id "
        "WHERE LOWER(z.name) = LOWER(%s) AND z.active = TRUE "
        "ORDER BY s.name LIMIT 1",
        (name,),
    )


def sku_exists(sku: str) -> bool:
    """Check if a SKU already exists in the products table."""
    row = _fetch_one("SELECT 1 FROM products WHERE sku = %s", (sku,))
    return row is not None


def bulk_create_products(rows: List[Dict[str, Any]], username: str) -> int:
    """Insert multiple products in a single transaction. Returns count created."""
    if not rows:
        return 0
    conn = _get_inventory_connection()
    conn.autocommit = False
    created = 0
    try:
        cursor = conn.cursor()
        for data in rows:
            sku = data.get("sku") or generate_next_sku()
            cursor.execute(
                "INSERT INTO products "
                "(customer_id, zone_id, sku, name, description, unit_type, "
                " pack_size, quantity, low_threshold, cost_per_unit, "
                " notification_emails, created_by) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    data["customer_id"],
                    data["zone_id"],
                    sku,
                    data["name"],
                    data.get("description") or None,
                    data.get("unit_type", "individual"),
                    data.get("pack_size") or None,
                    data.get("quantity", 0),
                    data.get("low_threshold") or None,
                    data.get("cost_per_unit") or None,
                    data.get("notification_emails") or None,
                    username,
                ),
            )
            prod_id = cursor.lastrowid
            cursor.execute(
                "INSERT INTO audit_log (entity_type, entity_id, action, changes, performed_by) "
                "VALUES ('product', %s, 'created', NULL, %s)",
                (prod_id, username),
            )
            created += 1
        conn.commit()
        cursor.close()
        return created
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# =========================================================================
# Transaction queries
# =========================================================================


def lookup_product_by_scan(value: str) -> Optional[Dict[str, Any]]:
    """Find a product by exact ID, exact SKU, or partial name match.

    Scan input priority: numeric ID first, then exact SKU, then name search.
    Returns the joined product row or None.
    """
    value = value.strip()
    if not value:
        return None

    if value.isdigit():
        product = _fetch_one(
            "SELECT p.*, c.name AS customer_name, z.name AS zone_name, "
            "s.name AS site_name, z.site_id "
            "FROM products p "
            "JOIN customers c ON c.id = p.customer_id "
            "JOIN zones z ON z.id = p.zone_id "
            "JOIN sites s ON s.id = z.site_id "
            "WHERE p.id = %s",
            (int(value),),
        )
        if product:
            return product

    product = _fetch_one(
        "SELECT p.*, c.name AS customer_name, z.name AS zone_name, "
        "s.name AS site_name, z.site_id "
        "FROM products p "
        "JOIN customers c ON c.id = p.customer_id "
        "JOIN zones z ON z.id = p.zone_id "
        "JOIN sites s ON s.id = z.site_id "
        "WHERE p.sku = %s",
        (value,),
    )
    if product:
        return product

    return _fetch_one(
        "SELECT p.*, c.name AS customer_name, z.name AS zone_name, "
        "s.name AS site_name, z.site_id "
        "FROM products p "
        "JOIN customers c ON c.id = p.customer_id "
        "JOIN zones z ON z.id = p.zone_id "
        "JOIN sites s ON s.id = z.site_id "
        "WHERE p.name LIKE %s "
        "ORDER BY p.status = 'active' DESC, p.name "
        "LIMIT 1",
        (f"%{value}%",),
    )


def search_products_by_scan(value: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Return multiple product matches for search fallback (name or SKU)."""
    value = value.strip()
    if not value:
        return []
    return _fetch_all(
        "SELECT p.id, p.sku, p.name, p.quantity, p.status, "
        "c.name AS customer_name, z.name AS zone_name, s.name AS site_name "
        "FROM products p "
        "JOIN customers c ON c.id = p.customer_id "
        "JOIN zones z ON z.id = p.zone_id "
        "JOIN sites s ON s.id = z.site_id "
        "WHERE (p.name LIKE %s OR p.sku LIKE %s) "
        "ORDER BY p.status = 'active' DESC, p.name "
        "LIMIT %s",
        (f"%{value}%", f"%{value}%", limit),
    )


def pull_stock(
    product_id: int,
    quantity: int,
    order_reference: Optional[str],
    override_reason: Optional[str],
    username: str,
) -> Dict[str, Any]:
    """Atomic stock decrement with transaction logging.

    Uses SELECT ... FOR UPDATE to lock the product row during the
    transaction, preventing concurrent modification.

    Returns dict with keys: product_id, quantity_before, quantity_after, transaction_id.
    """
    if is_product_locked(product_id):
        raise ValueError("Product is locked for physical count")

    conn = _get_inventory_connection()
    conn.autocommit = False
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, quantity FROM products WHERE id = %s FOR UPDATE",
            (product_id,),
        )
        product = cursor.fetchone()
        if not product:
            conn.rollback()
            raise ValueError("Product not found")

        qty_before = product["quantity"]
        qty_after = qty_before - quantity

        cursor.execute(
            "UPDATE products SET quantity = %s WHERE id = %s",
            (qty_after, product_id),
        )
        cursor.execute(
            "INSERT INTO transactions "
            "(product_id, action, quantity, quantity_before, quantity_after, "
            " order_reference, override_reason, performed_by) "
            "VALUES (%s, 'pull', %s, %s, %s, %s, %s, %s)",
            (product_id, -quantity, qty_before, qty_after,
             order_reference, override_reason, username),
        )
        txn_id = cursor.lastrowid
        conn.commit()
        cursor.close()
        return {
            "product_id": product_id,
            "quantity_before": qty_before,
            "quantity_after": qty_after,
            "transaction_id": txn_id,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def add_stock(
    product_id: int,
    quantity: int,
    order_reference: Optional[str],
    override_reason: Optional[str],
    username: str,
) -> Dict[str, Any]:
    """Atomic stock increment with transaction logging.

    Same locking strategy as pull_stock.
    """
    if is_product_locked(product_id):
        raise ValueError("Product is locked for physical count")

    conn = _get_inventory_connection()
    conn.autocommit = False
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, quantity FROM products WHERE id = %s FOR UPDATE",
            (product_id,),
        )
        product = cursor.fetchone()
        if not product:
            conn.rollback()
            raise ValueError("Product not found")

        qty_before = product["quantity"]
        qty_after = qty_before + quantity

        cursor.execute(
            "UPDATE products SET quantity = %s WHERE id = %s",
            (qty_after, product_id),
        )
        cursor.execute(
            "INSERT INTO transactions "
            "(product_id, action, quantity, quantity_before, quantity_after, "
            " order_reference, override_reason, performed_by) "
            "VALUES (%s, 'add', %s, %s, %s, %s, %s, %s)",
            (product_id, quantity, qty_before, qty_after,
             order_reference, override_reason, username),
        )
        txn_id = cursor.lastrowid
        conn.commit()
        cursor.close()
        return {
            "product_id": product_id,
            "quantity_before": qty_before,
            "quantity_after": qty_after,
            "transaction_id": txn_id,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_product_transactions(
    product_id: int, limit: int = 50,
) -> List[Dict[str, Any]]:
    """Recent transactions for a product, newest first."""
    return _fetch_all(
        "SELECT * FROM transactions WHERE product_id = %s "
        "ORDER BY created_at DESC LIMIT %s",
        (product_id, limit),
    )


def get_recent_transactions(limit: int = 50) -> List[Dict[str, Any]]:
    """Recent transactions across all products, newest first."""
    return _fetch_all(
        "SELECT t.*, p.sku, p.name AS product_name, c.name AS customer_name "
        "FROM transactions t "
        "JOIN products p ON p.id = t.product_id "
        "JOIN customers c ON c.id = p.customer_id "
        "ORDER BY t.created_at DESC LIMIT %s",
        (limit,),
    )


# =========================================================================
# Dashboard queries
# =========================================================================


def get_low_stock_products() -> List[Dict[str, Any]]:
    """Active products at or below their low stock threshold."""
    return _fetch_all(
        "SELECT p.id, p.sku, p.name, p.quantity, p.low_threshold, "
        "c.name AS customer_name, z.name AS zone_name, s.name AS site_name "
        "FROM products p "
        "JOIN customers c ON c.id = p.customer_id "
        "JOIN zones z ON z.id = p.zone_id "
        "JOIN sites s ON s.id = z.site_id "
        "WHERE p.status = 'active' "
        "AND p.low_threshold IS NOT NULL "
        "AND p.quantity <= p.low_threshold "
        "ORDER BY (p.quantity - p.low_threshold) ASC, c.name, p.name"
    )


def get_low_stock_count() -> int:
    """Count of active products at or below their low stock threshold."""
    row = _fetch_one(
        "SELECT COUNT(*) AS cnt FROM products "
        "WHERE status = 'active' "
        "AND low_threshold IS NOT NULL "
        "AND quantity <= low_threshold"
    )
    return row["cnt"] if row else 0


def get_todays_transaction_count() -> int:
    """Count of transactions created today."""
    row = _fetch_one(
        "SELECT COUNT(*) AS cnt FROM transactions "
        "WHERE DATE(created_at) = CURDATE()"
    )
    return row["cnt"] if row else 0


# =========================================================================
# Depletion projection
# =========================================================================


def get_depletion_projection(
    product_id: int, current_quantity: int,
) -> Dict[str, Any]:
    """Estimate depletion date from 90-day average pull rate.

    Returns dict with 'status' key:
      - "no_activity": zero pulls in last 90 days
      - "projected": includes avg_daily_rate, days_remaining, estimated_date
    """
    row = _fetch_one(
        "SELECT COALESCE(SUM(ABS(t.quantity)), 0) AS total_pulled, "
        "DATEDIFF(CURDATE(), MIN(t.created_at)) AS days_span "
        "FROM transactions t "
        "WHERE t.product_id = %s AND t.action = 'pull' "
        "AND t.created_at >= DATE_SUB(CURDATE(), INTERVAL 90 DAY)",
        (product_id,),
    )

    if not row or not row["total_pulled"]:
        return {"status": "no_activity", "message": "No recent activity"}

    days_span = max(row["days_span"] or 1, 1)
    avg_daily_rate = row["total_pulled"] / days_span
    days_remaining = current_quantity / avg_daily_rate if avg_daily_rate else 0
    estimated = date.today() + timedelta(days=round(days_remaining))

    return {
        "status": "projected",
        "avg_daily_rate": round(avg_daily_rate, 1),
        "days_remaining": round(days_remaining),
        "estimated_date": estimated.isoformat(),
    }


def get_depletion_projections_batch(
    products: List[Dict[str, Any]],
) -> Dict[int, Dict[str, Any]]:
    """Batch depletion projections for multiple products (dashboard use).

    products: list of dicts with at least 'id' and 'quantity' keys.
    Returns dict keyed by product_id -> projection dict.
    """
    if not products:
        return {}

    product_ids = [p["id"] for p in products]
    qty_map = {p["id"]: p["quantity"] for p in products}

    placeholders = ", ".join(["%s"] * len(product_ids))
    rows = _fetch_all(
        "SELECT t.product_id, "
        "COALESCE(SUM(ABS(t.quantity)), 0) AS total_pulled, "
        "DATEDIFF(CURDATE(), MIN(t.created_at)) AS days_span "
        "FROM transactions t "
        "WHERE t.product_id IN (" + placeholders + ") "
        "AND t.action = 'pull' "
        "AND t.created_at >= DATE_SUB(CURDATE(), INTERVAL 90 DAY) "
        "GROUP BY t.product_id",
        tuple(product_ids),
    )

    pull_data = {r["product_id"]: r for r in rows}
    result: Dict[int, Dict[str, Any]] = {}

    for pid in product_ids:
        r = pull_data.get(pid)
        if not r or not r["total_pulled"]:
            result[pid] = {"status": "no_activity", "message": "No recent activity"}
            continue
        days_span = max(r["days_span"] or 1, 1)
        avg_daily_rate = r["total_pulled"] / days_span
        current_qty = qty_map.get(pid, 0)
        days_remaining = current_qty / avg_daily_rate if avg_daily_rate else 0
        estimated = date.today() + timedelta(days=round(days_remaining))
        result[pid] = {
            "status": "projected",
            "avg_daily_rate": round(avg_daily_rate, 1),
            "days_remaining": round(days_remaining),
            "estimated_date": estimated.isoformat(),
        }

    return result


# =========================================================================
# Inventory Count queries
# =========================================================================


def is_product_locked(product_id: int) -> bool:
    """True if product is in an active count (in_progress or review)."""
    row = _fetch_one(
        "SELECT 1 FROM count_items ci "
        "JOIN inventory_counts ic ON ic.id = ci.count_id "
        "WHERE ci.product_id = %s AND ic.status IN ('in_progress', 'review') "
        "LIMIT 1",
        (product_id,),
    )
    return row is not None


def get_products_in_scope(
    scopes: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Resolve scope selections to active products.

    Each scope dict has keys: scope_type ('site', 'zone', 'customer'), scope_id (int).
    Returns product rows (id, quantity, customer_id) matching any scope entry.
    """
    if not scopes:
        return []

    conditions = []
    params: list = []
    for s in scopes:
        st = s["scope_type"]
        sid = s["scope_id"]
        if st == "site":
            conditions.append("z.site_id = %s")
            params.append(sid)
        elif st == "zone":
            conditions.append("p.zone_id = %s")
            params.append(sid)
        elif st == "customer":
            conditions.append("p.customer_id = %s")
            params.append(sid)

    if not conditions:
        return []

    where = " OR ".join(conditions)
    return _fetch_all(
        "SELECT p.id, p.quantity, p.customer_id, p.sku, p.name, "
        "c.name AS customer_name "
        "FROM products p "
        "JOIN customers c ON c.id = p.customer_id "
        "JOIN zones z ON z.id = p.zone_id "
        f"WHERE p.status = 'active' AND ({where}) "
        "ORDER BY c.name, p.name",
        tuple(params),
    )


def create_count(
    initiated_by: str,
    scope_description: str,
    threshold_pct: int,
    scopes: List[Dict[str, Any]],
) -> int:
    """Create a physical inventory count with scope and product snapshots.

    scopes: list of {scope_type, scope_id} dicts.
    Returns count ID.
    """
    products = get_products_in_scope(scopes)
    if not products:
        raise ValueError("No active products found in the selected scope")

    conn = _get_inventory_connection()
    conn.autocommit = False
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO inventory_counts "
            "(initiated_by, scope_description, discrepancy_threshold_pct) "
            "VALUES (%s, %s, %s)",
            (initiated_by, scope_description, threshold_pct),
        )
        count_id = cursor.lastrowid

        for s in scopes:
            cursor.execute(
                "INSERT INTO count_scope (count_id, scope_type, scope_id) "
                "VALUES (%s, %s, %s)",
                (count_id, s["scope_type"], s["scope_id"]),
            )

        for p in products:
            cursor.execute(
                "INSERT INTO count_items (count_id, product_id, recorded_quantity) "
                "VALUES (%s, %s, %s)",
                (count_id, p["id"], p["quantity"]),
            )

        cursor.execute(
            "INSERT INTO audit_log (entity_type, entity_id, action, changes, performed_by) "
            "VALUES ('count', %s, 'created', %s, %s)",
            (count_id, json.dumps({"products": len(products)}), initiated_by),
        )

        conn.commit()
        cursor.close()
        return count_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_counts(status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
    """List counts with item progress stats."""
    q = (
        "SELECT ic.*, "
        "COUNT(ci.id) AS total_items, "
        "SUM(CASE WHEN ci.counted_quantity IS NOT NULL THEN 1 ELSE 0 END) AS counted_items, "
        "SUM(CASE WHEN ci.flagged = TRUE THEN 1 ELSE 0 END) AS flagged_items "
        "FROM inventory_counts ic "
        "LEFT JOIN count_items ci ON ci.count_id = ic.id "
    )
    params: list = []
    if status_filter:
        q += "WHERE ic.status = %s "
        params.append(status_filter)
    q += "GROUP BY ic.id ORDER BY ic.started_at DESC"
    return _fetch_all(q, tuple(params))


def get_count(count_id: int) -> Optional[Dict[str, Any]]:
    """Single count with progress stats."""
    return _fetch_one(
        "SELECT ic.*, "
        "COUNT(ci.id) AS total_items, "
        "SUM(CASE WHEN ci.counted_quantity IS NOT NULL THEN 1 ELSE 0 END) AS counted_items, "
        "SUM(CASE WHEN ci.flagged = TRUE THEN 1 ELSE 0 END) AS flagged_items "
        "FROM inventory_counts ic "
        "LEFT JOIN count_items ci ON ci.count_id = ic.id "
        "WHERE ic.id = %s "
        "GROUP BY ic.id",
        (count_id,),
    )


def get_count_items(
    count_id: int, flagged_only: bool = False,
) -> List[Dict[str, Any]]:
    """Items in a count with product details."""
    q = (
        "SELECT ci.*, p.sku, p.name AS product_name, "
        "c.name AS customer_name, z.name AS zone_name "
        "FROM count_items ci "
        "JOIN products p ON p.id = ci.product_id "
        "JOIN customers c ON c.id = p.customer_id "
        "JOIN zones z ON z.id = p.zone_id "
        "WHERE ci.count_id = %s"
    )
    params: list = [count_id]
    if flagged_only:
        q += " AND ci.flagged = TRUE"
    q += " ORDER BY c.name, p.name"
    return _fetch_all(q, tuple(params))


def get_count_item(item_id: int) -> Optional[Dict[str, Any]]:
    """Single count item with product details."""
    return _fetch_one(
        "SELECT ci.*, p.sku, p.name AS product_name, "
        "c.name AS customer_name, z.name AS zone_name "
        "FROM count_items ci "
        "JOIN products p ON p.id = ci.product_id "
        "JOIN customers c ON c.id = p.customer_id "
        "JOIN zones z ON z.id = p.zone_id "
        "WHERE ci.id = %s",
        (item_id,),
    )


def update_count_item(
    item_id: int, counted_quantity: int, counted_by: str, threshold_pct: int,
) -> Dict[str, Any]:
    """Save a counted quantity, compute discrepancy, auto-flag if above threshold."""
    conn = _get_inventory_connection()
    conn.autocommit = False
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT ci.*, ic.discrepancy_threshold_pct "
            "FROM count_items ci "
            "JOIN inventory_counts ic ON ic.id = ci.count_id "
            "WHERE ci.id = %s FOR UPDATE",
            (item_id,),
        )
        item = cursor.fetchone()
        if not item:
            conn.rollback()
            raise ValueError("Count item not found")

        discrepancy = counted_quantity - item["recorded_quantity"]
        pct = threshold_pct or item["discrepancy_threshold_pct"] or 20
        flagged = False
        if item["recorded_quantity"] > 0:
            flagged = abs(discrepancy) > (item["recorded_quantity"] * pct / 100)
        elif discrepancy != 0:
            flagged = True

        cursor.execute(
            "UPDATE count_items SET "
            "counted_quantity = %s, discrepancy = %s, flagged = %s, "
            "counted_by = %s, counted_at = NOW() "
            "WHERE id = %s",
            (counted_quantity, discrepancy, flagged, counted_by, item_id),
        )
        conn.commit()
        cursor.close()
        return {
            "item_id": item_id,
            "counted_quantity": counted_quantity,
            "discrepancy": discrepancy,
            "flagged": flagged,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def approve_count_item(
    item_id: int, approved: bool, approved_by: str,
) -> None:
    """Manager approval on a flagged count item."""
    _execute(
        "UPDATE count_items SET approved = %s, approved_by = %s WHERE id = %s",
        (approved, approved_by, item_id),
    )


def move_count_to_review(count_id: int) -> None:
    """Transition count from in_progress to review."""
    _execute(
        "UPDATE inventory_counts SET status = 'review' WHERE id = %s AND status = 'in_progress'",
        (count_id,),
    )


def cancel_count(count_id: int, username: str) -> None:
    """Cancel a count -- no adjustments applied, products unlocked."""
    _execute(
        "UPDATE inventory_counts SET status = 'canceled', completed_at = NOW(), "
        "completed_by = %s WHERE id = %s AND status IN ('in_progress', 'review')",
        (username, count_id),
    )
    log_audit("count", count_id, "canceled", None, username)


def complete_count(count_id: int, completed_by: str) -> Dict[str, Any]:
    """Finalize count: apply adjustments as count_adjustment transactions,
    update last_count_date on affected customers, set status to completed.

    Returns summary dict with adjustment count.
    """
    conn = _get_inventory_connection()
    conn.autocommit = False
    try:
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            "SELECT id, status FROM inventory_counts WHERE id = %s FOR UPDATE",
            (count_id,),
        )
        count = cursor.fetchone()
        if not count or count["status"] not in ("in_progress", "review"):
            conn.rollback()
            raise ValueError("Count not found or not in a completable state")

        cursor.execute(
            "SELECT ci.id, ci.product_id, ci.recorded_quantity, ci.counted_quantity, "
            "ci.discrepancy, ci.flagged, ci.approved, p.quantity AS current_quantity, "
            "p.customer_id "
            "FROM count_items ci "
            "JOIN products p ON p.id = ci.product_id "
            "WHERE ci.count_id = %s",
            (count_id,),
        )
        items = cursor.fetchall()

        adjustments = 0
        customer_ids = set()
        for item in items:
            if item["counted_quantity"] is None:
                continue
            if item["flagged"] and not item["approved"]:
                continue

            customer_ids.add(item["customer_id"])
            disc = item["discrepancy"] or 0
            if disc == 0:
                continue

            qty_before = item["current_quantity"]
            qty_after = qty_before + disc

            cursor.execute(
                "UPDATE products SET quantity = %s WHERE id = %s",
                (qty_after, item["product_id"]),
            )
            cursor.execute(
                "INSERT INTO transactions "
                "(product_id, action, quantity, quantity_before, quantity_after, "
                " order_reference, performed_by) "
                "VALUES (%s, 'count_adjustment', %s, %s, %s, %s, %s)",
                (item["product_id"], disc, qty_before, qty_after,
                 f"Count #{count_id}", completed_by),
            )
            adjustments += 1

        for cid in customer_ids:
            cursor.execute(
                "UPDATE customers SET last_count_date = CURDATE() WHERE id = %s",
                (cid,),
            )

        cursor.execute(
            "UPDATE inventory_counts SET status = 'completed', "
            "completed_at = NOW(), completed_by = %s WHERE id = %s",
            (completed_by, count_id),
        )

        cursor.execute(
            "INSERT INTO audit_log (entity_type, entity_id, action, changes, performed_by) "
            "VALUES ('count', %s, 'count_completed', %s, %s)",
            (count_id, json.dumps({"adjustments": adjustments}), completed_by),
        )

        conn.commit()
        cursor.close()
        return {"count_id": count_id, "adjustments": adjustments}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_customers_due_for_count() -> List[Dict[str, Any]]:
    """Customers whose last_count_date + frequency interval is past due."""
    return _fetch_all(
        "SELECT c.*, "
        "CASE c.count_frequency "
        "  WHEN 'monthly' THEN DATE_ADD(c.last_count_date, INTERVAL 1 MONTH) "
        "  WHEN 'quarterly' THEN DATE_ADD(c.last_count_date, INTERVAL 3 MONTH) "
        "  WHEN 'semi_annual' THEN DATE_ADD(c.last_count_date, INTERVAL 6 MONTH) "
        "  WHEN 'annual' THEN DATE_ADD(c.last_count_date, INTERVAL 1 YEAR) "
        "  ELSE NULL "
        "END AS next_count_due "
        "FROM customers c "
        "WHERE c.active = TRUE "
        "AND c.count_frequency != 'as_needed' "
        "AND ("
        "  c.last_count_date IS NULL "
        "  OR CASE c.count_frequency "
        "    WHEN 'monthly' THEN DATE_ADD(c.last_count_date, INTERVAL 1 MONTH) "
        "    WHEN 'quarterly' THEN DATE_ADD(c.last_count_date, INTERVAL 3 MONTH) "
        "    WHEN 'semi_annual' THEN DATE_ADD(c.last_count_date, INTERVAL 6 MONTH) "
        "    WHEN 'annual' THEN DATE_ADD(c.last_count_date, INTERVAL 1 YEAR) "
        "  END <= CURDATE()"
        ") "
        "ORDER BY c.last_count_date ASC"
    )


# =========================================================================
# Audit log
# =========================================================================


def log_audit(
    entity_type: str,
    entity_id: int,
    action: str,
    changes: Any,
    username: str,
) -> int:
    """Insert an audit log entry. changes is serialized to JSON if provided."""
    changes_json = json.dumps(changes) if changes else None
    return _execute(
        "INSERT INTO audit_log (entity_type, entity_id, action, changes, performed_by) "
        "VALUES (%s, %s, %s, %s, %s)",
        (entity_type, entity_id, action, changes_json, username),
    )


# =========================================================================
# Helpers
# =========================================================================


def _diff_fields(
    old: Optional[Dict[str, Any]], new_fields: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Compare old row dict to new field values; return {field: {old, new}} or None."""
    if not old:
        return None
    changes: Dict[str, Any] = {}
    for key, new_val in new_fields.items():
        old_val = old.get(key)
        if _normalize(old_val) != _normalize(new_val):
            changes[key] = {"old": _serialize(old_val), "new": _serialize(new_val)}
    return changes or None


def _normalize(val: Any) -> Any:
    """Normalize for comparison: empty string and None are equivalent."""
    if val == "" or val == "None":
        return None
    return val


def _serialize(val: Any) -> Any:
    """Make value JSON-safe."""
    from decimal import Decimal
    from datetime import date, datetime
    if isinstance(val, Decimal):
        return float(val)
    if isinstance(val, (date, datetime)):
        return val.isoformat()
    return val
