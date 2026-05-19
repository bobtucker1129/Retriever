from __future__ import annotations

from datetime import datetime
from io import BytesIO

from fastapi.testclient import TestClient

import app.auth.sessions as session_module
import app.routes.inventory as inventory_routes
from app.config import AppSettings
from app.dependencies import settings_dependency
from app.main import create_app
from app.services import tag_generator
from tests.fakes import FakeDb


def make_settings(email: str, *, with_db: bool = True) -> AppSettings:
    kwargs = {
        "retriever_env": "local",
        "local_dev_identity_enabled": True,
        "local_dev_email": email,
        "local_dev_display_name": "Inventory Tester",
        "retriever_seed_admin_email": "state@boonegraphics.net",
    }
    if with_db:
        kwargs.update(
            {
                "mysql_host": "mysql.internal",
                "mysql_user": "retriever_app",
                "mysql_password": "redacted",
            }
        )
    return AppSettings(**kwargs)


def make_inventory_client(monkeypatch, db: FakeDb, email: str) -> TestClient:
    settings = make_settings(email)
    app = create_app()
    app.dependency_overrides[settings_dependency] = lambda: settings
    monkeypatch.setattr(session_module, "create_connection", lambda settings: db.connection())
    return TestClient(app, follow_redirects=False)


class FakeInventoryRepository:
    def __init__(self):
        self.calls: list[tuple] = []
        self.product = {
            "id": 42,
            "sku": "INV-0042",
            "name": "Business Cards",
            "customer_id": 7,
            "customer_name": "Mechanics Bank",
            "site_name": "Goleta",
            "zone_name": "Warehouse",
            "site_id": 1,
            "zone_id": 2,
            "quantity": 100,
            "low_threshold": None,
            "notification_emails": None,
            "status": "active",
            "unit_type": "pack",
            "pack_size": 250,
        }
        self.count = {
            "id": 5,
            "status": "in_progress",
            "discrepancy_threshold_pct": 20,
            "total_items": 1,
            "counted_items": 0,
            "flagged_items": 0,
        }
        self.count_item = {
            "id": 9,
            "product_id": 42,
            "sku": "INV-0042",
            "product_name": "Business Cards",
            "customer_name": "Mechanics Bank",
            "zone_name": "Warehouse",
            "recorded_quantity": 100,
            "counted_quantity": None,
            "discrepancy": None,
            "flagged": False,
            "approved": None,
        }

    def is_manager(self, user):
        return user.can_manage_inventory()

    def get_low_stock_products(self):
        return []

    def get_depletion_projections_batch(self, products):
        return {}

    def get_customers_due_for_count(self):
        return []

    def get_todays_transaction_count(self):
        return 0

    def get_low_stock_count(self):
        return 0

    def get_sites(self, active_only=False):
        return [{"id": 1, "name": "Goleta", "active": True}]

    def get_zones_for_site(self, site_id):
        return [{"id": 2, "name": "Warehouse", "site_id": site_id, "active": True}]

    def get_zones(self, site_id=None):
        return [{"id": 2, "name": "Warehouse", "site_id": 1, "site_name": "Goleta"}]

    def get_customers(self, active_only=True, search=None):
        return [{"id": 7, "name": "Mechanics Bank", "active": True}]

    def get_products(self, **filters):
        return [self.product]

    def get_all_active_products(self):
        return [self.product]

    def get_active_products_for_customer(self, customer_id):
        return [{"id": self.product["id"], "sku": self.product["sku"], "name": self.product["name"]}]

    def get_depletion_projection(self, product_id, current_quantity):
        return {"status": "no_activity", "message": "No recent activity"}

    def get_product(self, product_id):
        return dict(self.product) if int(product_id) == 42 else None

    def get_product_transactions(self, product_id):
        return [
            {
                "id": 1001,
                "product_id": product_id,
                "action": "pull",
                "quantity": -3,
                "quantity_before": 100,
                "quantity_after": 97,
                "order_reference": None,
                "override_reason": None,
                "performed_by": "viewer@boonegraphics.net",
                "created_at": datetime(2026, 5, 18, 9, 0),
            }
        ]

    def lookup_product_by_scan(self, value):
        return dict(self.product) if value in {"42", "INV-0042"} else None

    def search_products_by_scan(self, value):
        return [self.product] if "Business" in value else []

    def pull_stock(self, **kwargs):
        self.calls.append(("pull_stock", kwargs))
        self.product["quantity"] -= kwargs["quantity"]
        return {
            "product_id": kwargs["product_id"],
            "quantity_before": self.product["quantity"] + kwargs["quantity"],
            "quantity_after": self.product["quantity"],
            "transaction_id": 1001,
        }

    def add_stock(self, **kwargs):
        self.calls.append(("add_stock", kwargs))
        self.product["quantity"] += kwargs["quantity"]
        return {
            "product_id": kwargs["product_id"],
            "quantity_before": self.product["quantity"] - kwargs["quantity"],
            "quantity_after": self.product["quantity"],
            "transaction_id": 1002,
        }

    def create_product(self, data, username):
        self.calls.append(("create_product", data, username))
        return 43

    def create_site(self, name, address, username):
        self.calls.append(("create_site", name, address, username))
        return 2

    def get_count(self, count_id):
        return dict(self.count) if int(count_id) == 5 else None

    def get_counts(self, status_filter=None):
        return [dict(self.count)]

    def get_count_items(self, count_id, flagged_only=False):
        return [dict(self.count_item)]

    def get_count_item(self, item_id):
        return dict(self.count_item)

    def update_count_item(self, item_id, counted_quantity, counted_by, threshold_pct):
        self.calls.append(("update_count_item", item_id, counted_quantity, counted_by, threshold_pct))
        self.count_item["counted_quantity"] = counted_quantity
        self.count_item["discrepancy"] = counted_quantity - self.count_item["recorded_quantity"]
        self.count_item["flagged"] = False
        return self.count_item

    def move_count_to_review(self, count_id):
        self.calls.append(("move_count_to_review", count_id))
        self.count["status"] = "review"

    def approve_count_item(self, item_id, approved, approved_by):
        self.calls.append(("approve_count_item", item_id, approved, approved_by))
        self.count_item["approved"] = approved
        self.count_item["approved_by"] = approved_by


def install_fake_inventory(monkeypatch):
    fake = FakeInventoryRepository()
    monkeypatch.setattr(inventory_routes, "inv_queries", fake)
    return fake


def seed_user(db: FakeDb, email: str, inventory_level: str, *, admin: bool = False) -> None:
    db.add_user(email, "Inventory Tester", "active", is_seed_admin=admin, inventory_level=inventory_level)


def test_inventory_access_follows_inventory_level(monkeypatch) -> None:
    install_fake_inventory(monkeypatch)
    db = FakeDb()
    seed_user(db, "none@boonegraphics.net", "no")
    seed_user(db, "viewer@boonegraphics.net", "viewer")

    denied = make_inventory_client(monkeypatch, db, "none@boonegraphics.net").get("/inventory/")
    allowed = make_inventory_client(monkeypatch, db, "viewer@boonegraphics.net").get("/inventory/")

    assert denied.status_code == 403
    assert allowed.status_code == 200
    assert "Inventory" in allowed.text


def test_manager_only_direct_urls_and_posts_reject_viewer(monkeypatch) -> None:
    fake = install_fake_inventory(monkeypatch)
    db = FakeDb()
    seed_user(db, "viewer@boonegraphics.net", "viewer")
    client = make_inventory_client(monkeypatch, db, "viewer@boonegraphics.net")

    assert client.get("/inventory/sites/new").status_code == 403
    response = client.post("/inventory/products", data={"customer_id": 7, "zone_id": 2, "name": "New"})

    assert response.status_code == 403
    assert not fake.calls


def test_manager_can_reach_manager_actions(monkeypatch) -> None:
    fake = install_fake_inventory(monkeypatch)
    db = FakeDb()
    seed_user(db, "manager@boonegraphics.net", "manager")
    client = make_inventory_client(monkeypatch, db, "manager@boonegraphics.net")

    form = {
        "customer_id": 7,
        "zone_id": 2,
        "sku": "INV-0043",
        "name": "New Product",
        "quantity": 5,
    }
    response = client.post("/inventory/products", data=form)

    assert response.status_code == 303
    assert response.headers["location"] == "/inventory/products"
    assert fake.calls[0][0] == "create_product"


def test_viewer_can_scan_pull_and_add_stock(monkeypatch) -> None:
    fake = install_fake_inventory(monkeypatch)
    db = FakeDb()
    seed_user(db, "viewer@boonegraphics.net", "viewer")
    client = make_inventory_client(monkeypatch, db, "viewer@boonegraphics.net")

    lookup = client.post("/inventory/scan/lookup", data={"scan_value": "INV-0042"})
    pull = client.post("/inventory/pull", data={"product_id": 42, "quantity": 3})
    add = client.post("/inventory/add", data={"product_id": 42, "quantity": 8})

    assert lookup.status_code == 200
    assert "Business Cards" in lookup.text
    assert pull.status_code == 200
    assert add.status_code == 200
    assert ("pull_stock", {"product_id": 42, "quantity": 3, "order_reference": None, "override_reason": None, "username": "viewer@boonegraphics.net"}) in fake.calls
    assert ("add_stock", {"product_id": 42, "quantity": 8, "order_reference": None, "override_reason": None, "username": "viewer@boonegraphics.net"}) in fake.calls


def test_core_inventory_pages_render_without_json_dead_ends(monkeypatch) -> None:
    install_fake_inventory(monkeypatch)
    db = FakeDb()
    seed_user(db, "manager@boonegraphics.net", "manager")
    client = make_inventory_client(monkeypatch, db, "manager@boonegraphics.net")

    paths = [
        "/inventory/",
        "/inventory/products",
        "/inventory/products/42",
        "/inventory/products/42/transactions",
        "/inventory/customers",
        "/inventory/sites",
        "/inventory/scan",
        "/inventory/tags",
        "/inventory/counts",
        "/inventory/counts/5",
        "/inventory/counts/5/review",
    ]

    for path in paths:
        response = client.get(path)
        assert response.status_code == 200, path
        assert response.headers["content-type"].startswith("text/html"), path
        assert "<html" in response.text or "<section" in response.text, path


def test_count_item_entry_is_viewer_but_review_is_manager(monkeypatch) -> None:
    fake = install_fake_inventory(monkeypatch)
    db = FakeDb()
    seed_user(db, "viewer@boonegraphics.net", "viewer")
    seed_user(db, "manager@boonegraphics.net", "manager")

    viewer = make_inventory_client(monkeypatch, db, "viewer@boonegraphics.net")
    save = viewer.post("/inventory/counts/5/items/9", data={"counted_quantity": 97})
    review_denied = viewer.post("/inventory/counts/5/review")

    manager = make_inventory_client(monkeypatch, db, "manager@boonegraphics.net")
    review_allowed = manager.post("/inventory/counts/5/review")

    assert save.status_code == 200
    assert ("update_count_item", 9, 97, "viewer@boonegraphics.net", 20) in fake.calls
    assert review_denied.status_code == 403
    assert review_allowed.status_code == 303
    assert review_allowed.headers["location"] == "/inventory/counts/5/review"


def test_tags_route_generates_pdf_for_manager_only(monkeypatch) -> None:
    install_fake_inventory(monkeypatch)
    db = FakeDb()
    seed_user(db, "viewer@boonegraphics.net", "viewer")
    seed_user(db, "manager@boonegraphics.net", "manager")

    viewer = make_inventory_client(monkeypatch, db, "viewer@boonegraphics.net")
    manager = make_inventory_client(monkeypatch, db, "manager@boonegraphics.net")
    form = {"scope": "product", "product_id": "42"}

    denied = viewer.post("/inventory/tags/generate", data=form)
    pdf = manager.post("/inventory/tags/generate", data=form)

    assert denied.status_code == 403
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF-")


def test_barcode_generation_uses_code39_without_checksum(monkeypatch) -> None:
    captured = {}

    class FakeCode39:
        def __init__(self, value, writer=None, add_checksum=True):
            captured["value"] = value
            captured["add_checksum"] = add_checksum

        def write(self, stream, options=None):
            captured["options"] = options or {}
            stream.write(b"png-bytes")

    def fake_get_barcode_class(name):
        captured["symbology"] = name
        return FakeCode39

    monkeypatch.setattr(tag_generator.barcode, "get_barcode_class", fake_get_barcode_class)

    assert tag_generator._generate_barcode_png("INV-0042") == b"png-bytes"
    assert captured["symbology"] == "code39"
    assert captured["value"] == "INV-0042"
    assert captured["add_checksum"] is False
    assert captured["options"]["write_text"] is False


def test_generated_tag_pdf_is_readable_and_mentions_sku() -> None:
    pdf = tag_generator.generate_tags_pdf(
        [
            {
                "id": 42,
                "sku": "INV-0042",
                "name": "Business Cards",
                "customer_name": "Mechanics Bank",
                "unit_type": "pack",
                "pack_size": 250,
            }
        ]
    )

    assert pdf.startswith(b"%PDF-")
    from PyPDF2 import PdfReader

    text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(pdf)).pages)
    assert "INV-0042" in text
    assert "Business Cards" in text
