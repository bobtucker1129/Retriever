"""
Shared Email Service

Platform-wide SMTP email sender with TLS support, retry on failure,
and graceful degradation when SMTP is not configured.

First consumer: Retriever Inventory (low stock + restock alerts).
Future consumers: Proofs (Phase 5), PrePress.
"""

from __future__ import annotations

import logging
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Optional

from app.config import get_settings

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2  # seconds


def is_smtp_configured() -> bool:
    """True if SMTP_HOST and SMTP_FROM_EMAIL are both set in config."""
    settings = get_settings()
    return bool(settings.smtp_host) and bool(settings.smtp_from_email)


def send_email(
    to_addresses: List[str],
    subject: str,
    body_text: str,
    body_html: Optional[str] = None,
) -> bool:
    """Send an email via SMTP with retry.

    Returns True on success, False on failure.  Never raises -- all
    errors are logged so callers (including background tasks) don't crash.
    """
    if not to_addresses:
        logger.warning("send_email called with empty recipient list -- skipping")
        return False

    if not is_smtp_configured():
        logger.info(
            "SMTP not configured -- email NOT sent. subject=%r, to=%s",
            subject,
            ", ".join(to_addresses),
        )
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    settings = get_settings()
    msg["From"] = settings.smtp_from_email
    msg["To"] = ", ".join(to_addresses)
    msg.attach(MIMEText(body_text, "plain"))
    if body_html:
        msg.attach(MIMEText(body_html, "html"))

    host = settings.smtp_host
    port = int(settings.smtp_port or 587)
    use_tls = settings.smtp_use_tls
    username = settings.smtp_username
    password = settings.smtp_password

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            if port == 465:
                server = smtplib.SMTP_SSL(host, port, timeout=30)
            else:
                server = smtplib.SMTP(host, port, timeout=30)
                if use_tls:
                    server.starttls()

            with server:
                if username and password:
                    server.login(username, password)
                server.send_message(msg)

            logger.info(
                "Email sent: subject=%r, to=%s", subject, ", ".join(to_addresses)
            )
            return True
        except Exception:
            logger.warning(
                "Email send attempt %d/%d failed: subject=%r, to=%s",
                attempt,
                MAX_RETRIES,
                subject,
                ", ".join(to_addresses),
                exc_info=True,
            )
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF_BASE ** attempt)

    logger.error(
        "Email send FAILED after %d attempts: subject=%r, to=%s",
        MAX_RETRIES,
        subject,
        ", ".join(to_addresses),
    )
    return False


# =========================================================================
# Inventory notification helpers
# =========================================================================


def _parse_notification_emails(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    return [e.strip() for e in raw.split(",") if e.strip()]


def _build_inventory_body(
    heading: str,
    product: dict,
) -> tuple[str, str]:
    """Return (plain_text, html) body for an inventory notification."""
    name = product.get("name", "Unknown")
    sku = product.get("sku", "N/A")
    customer = product.get("customer_name", "Unknown")
    quantity = product.get("quantity", "?")
    threshold = product.get("low_threshold", "N/A")
    site = product.get("site_name", "")
    zone = product.get("zone_name", "")
    contact = product.get("primary_contact_username") or "Not assigned"
    location = f"{site} / {zone}" if site and zone else site or zone or "N/A"

    text = (
        f"{heading}\n"
        f"{'=' * len(heading)}\n\n"
        f"Product:   {name}\n"
        f"SKU:       {sku}\n"
        f"Customer:  {customer}\n"
        f"Quantity:  {quantity}\n"
        f"Threshold: {threshold}\n"
        f"Location:  {location}\n"
        f"Primary Contact: {contact}\n"
    )

    html = (
        f"<h2 style='margin:0 0 12px'>{heading}</h2>"
        "<table style='border-collapse:collapse;font-family:sans-serif;font-size:14px'>"
        f"<tr><td style='padding:4px 12px 4px 0;font-weight:bold'>Product</td><td>{name}</td></tr>"
        f"<tr><td style='padding:4px 12px 4px 0;font-weight:bold'>SKU</td><td>{sku}</td></tr>"
        f"<tr><td style='padding:4px 12px 4px 0;font-weight:bold'>Customer</td><td>{customer}</td></tr>"
        f"<tr><td style='padding:4px 12px 4px 0;font-weight:bold'>Quantity</td><td>{quantity}</td></tr>"
        f"<tr><td style='padding:4px 12px 4px 0;font-weight:bold'>Threshold</td><td>{threshold}</td></tr>"
        f"<tr><td style='padding:4px 12px 4px 0;font-weight:bold'>Location</td><td>{location}</td></tr>"
        f"<tr><td style='padding:4px 12px 4px 0;font-weight:bold'>Primary Contact</td><td>{contact}</td></tr>"
        "</table>"
    )

    return text, html


def send_low_stock_alert(product: dict) -> None:
    """Send low stock alert for an inventory product.

    Called as a background task after a pull leaves quantity at or below
    the product's low_threshold.
    """
    recipients = _parse_notification_emails(product.get("notification_emails"))
    if not recipients:
        logger.info(
            "No notification_emails for product %s (%s) -- low stock alert skipped",
            product.get("id"),
            product.get("sku"),
        )
        return

    subject = f"Low Stock Alert: {product.get('name', 'Unknown')} [{product.get('sku', '')}]"
    body_text, body_html = _build_inventory_body("Low Stock Alert", product)
    send_email(recipients, subject, body_text, body_html)


def send_restock_confirmation(product: dict) -> None:
    """Send restock confirmation for an inventory product.

    Called as a background task after an add brings quantity back above
    the product's low_threshold.
    """
    recipients = _parse_notification_emails(product.get("notification_emails"))
    if not recipients:
        logger.info(
            "No notification_emails for product %s (%s) -- restock confirmation skipped",
            product.get("id"),
            product.get("sku"),
        )
        return

    subject = f"Restock Confirmation: {product.get('name', 'Unknown')} [{product.get('sku', '')}]"
    body_text, body_html = _build_inventory_body("Restock Confirmation", product)
    send_email(recipients, subject, body_text, body_html)
