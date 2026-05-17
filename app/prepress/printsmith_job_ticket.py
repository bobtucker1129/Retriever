"""
Fetch job ticket PDFs from PrintSmith REST API (token auth, base64 response).

Token lifecycle:
- old-authority mode borrows the token from old Retriever's token proxy
- new-authority mode owns DB cache -> validate -> generate -> delete+regenerate
"""

from __future__ import annotations

import base64
import hashlib
import logging
import time
import uuid
from datetime import datetime
from io import BytesIO
from typing import TYPE_CHECKING, List, Optional

import httpx
from PyPDF2 import PdfMerger

from app.database.mysql_client import get_mysql_client

if TYPE_CHECKING:
    from config import Config

logger = logging.getLogger(__name__)

_DB_NAME = "retriever_prepress"
_TOKEN_TABLE = "printsmith_api_token"
_HTTPX_TIMEOUT = httpx.Timeout(120.0, connect=30.0)
_TOKEN_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


def _setting(config: Config, lower_name: str, upper_name: str, default: str = "") -> str:
    value = getattr(config, lower_name, None)
    if value is None or value == "":
        value = getattr(config, upper_name, None)
    if hasattr(value, "value"):
        value = value.value
    return str(value or default)


def _md5_hex(plaintext: str) -> str:
    return hashlib.md5(plaintext.encode("utf-8")).hexdigest()


def _api_headers(token: str = "") -> dict:
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "messageId": str(uuid.uuid4()),
        "startTime": str(int(time.time() * 1000)),
        "token": token,
    }


# ── Token persistence (MySQL) ──────────────────────────────────────

def load_cached_token(vendor: str) -> tuple[str, Optional[datetime]]:
    """Return (token, expires_at_dt) from DB, or ("", None)."""
    client = get_mysql_client()
    conn = None
    cursor = None
    try:
        conn = client.get_connection(_DB_NAME)
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            f"SELECT token, expires_at FROM {_TOKEN_TABLE} WHERE vendor = %s",
            (vendor,),
        )
        row = cursor.fetchone()
        if row and row.get("token"):
            return str(row["token"]), row.get("expires_at")
    except Exception as e:
        logger.debug("Token cache read failed (table may not exist yet): %s", e)
    finally:
        try:
            if cursor:
                cursor.close()
        except Exception:
            pass
        try:
            if conn:
                conn.close()
        except Exception:
            pass
    return "", None


def _save_cached_token(vendor: str, token: str, expires_at_str: str) -> None:
    """Upsert token row. expires_at_str format: '2026-04-09 14:52:00'."""
    client = get_mysql_client()
    conn = None
    cursor = None
    try:
        conn = client.get_connection(_DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            f"""
            INSERT INTO {_TOKEN_TABLE} (vendor, token, expires_at)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE
              token = VALUES(token),
              expires_at = VALUES(expires_at)
            """,
            (vendor, token, expires_at_str),
        )
    except Exception as e:
        logger.warning("Token cache write failed: %s", e)
    finally:
        try:
            if cursor:
                cursor.close()
        except Exception:
            pass
        try:
            if conn:
                conn.close()
        except Exception:
            pass


def clear_cached_token(vendor: str) -> None:
    client = get_mysql_client()
    conn = None
    cursor = None
    try:
        conn = client.get_connection(_DB_NAME)
        cursor = conn.cursor()
        cursor.execute(f"DELETE FROM {_TOKEN_TABLE} WHERE vendor = %s", (vendor,))
    except Exception:
        pass
    finally:
        try:
            if cursor:
                cursor.close()
        except Exception:
            pass
        try:
            if conn:
                conn.close()
        except Exception:
            pass


# ── Token acquisition ───────────────────────────────────────────────

def _extract_token_response(data: dict) -> tuple[str, str]:
    """Pull (token, expirationTime) from the nested API response."""
    resp = data.get("response", {}) or {}
    return resp.get("token", ""), resp.get("expirationTime", "")


async def get_valid_token(config: Config) -> str:
    """
    Obtain a valid PrintSmith REST API token.

    1. Check DB cache (skip validation if not near expiry)
    2. Validate cached token with API
    3. Generate new token (MD5 password)
    4. On vendor collision: delete stale token, regenerate
    5. On still-failing: reload from DB (another worker may have refreshed)
    """
    mode = _setting(
        config,
        "printsmith_token_authority_mode",
        "PRINTSMITH_TOKEN_AUTHORITY_MODE",
        "disabled",
    )
    if mode == "using_old_authority":
        return await get_proxy_token(config)

    base = _setting(config, "printsmith_api_base_url", "PREPRESS_PRINTSMITH_API_BASE_URL").rstrip("/")
    if not base:
        base = _setting(config, "printsmith_api_base_url", "PRINTSMITH_API_BASE_URL").rstrip("/")
    vendor = _setting(config, "printsmith_api_vendor", "PREPRESS_PRINTSMITH_API_VENDOR", "LordTate")
    username = _setting(config, "printsmith_api_username", "PREPRESS_PRINTSMITH_API_USERNAME")
    if not username:
        username = _setting(config, "printsmith_api_username", "PRINTSMITH_API_USERNAME")
    password = _setting(config, "printsmith_api_password", "PREPRESS_PRINTSMITH_API_PASSWORD")
    if not password:
        password = _setting(config, "printsmith_api_password", "PRINTSMITH_API_PASSWORD")

    if not all([base, vendor, username, password]):
        raise ValueError("PrintSmith REST API credentials not configured.")

    cached_tok, cached_exp = load_cached_token(vendor)

    # Fast path: cached token with >2 min remaining -- trust without API round-trip
    if cached_tok and cached_exp:
        try:
            remaining = (cached_exp.timestamp() if hasattr(cached_exp, "timestamp") else 0) - time.time()
        except Exception:
            remaining = 0
        if remaining > 120:
            return cached_tok

    # Validate cached token with API if present
    if cached_tok:
        try:
            async with httpx.AsyncClient(timeout=_TOKEN_TIMEOUT, verify=False) as client:
                r = await client.post(
                    f"{base}/token/validate",
                    headers=_api_headers(""),
                    json={"token": cached_tok, "apiUserName": username, "apiVendor": vendor},
                )
                if r.status_code == 200 and r.json().get("responseCode") == 200:
                    return cached_tok
        except httpx.HTTPError:
            pass
        logger.info("Cached PrintSmith API token is invalid/expired; regenerating.")

    # Generate new token
    md5_pass = _md5_hex(password)
    gen_payload = {"apiUserName": username, "apiUserPassword": md5_pass, "apiVendor": vendor}

    async with httpx.AsyncClient(timeout=_TOKEN_TIMEOUT, verify=False) as client:
        r = await client.post(f"{base}/token", headers=_api_headers(""), json=gen_payload)
        data = r.json() if r.status_code == 200 else {}
        rc = data.get("responseCode", 0)
        msg = data.get("responseMessage", "")

        if rc == 200:
            tok, exp = _extract_token_response(data)
            if tok:
                _save_cached_token(vendor, tok, exp)
                return tok

        # Vendor collision: delete blocking token, then regenerate
        if "only one token" in msg.lower():
            logger.info("PrintSmith single-token-per-vendor collision; deleting stale token.")
            del_payload = {"apiUserName": username, "apiUserPassword": md5_pass, "apiVendor": vendor}
            await client.post(f"{base}/token/delete", headers=_api_headers(""), json=del_payload)

            r2 = await client.post(f"{base}/token", headers=_api_headers(""), json=gen_payload)
            data2 = r2.json() if r2.status_code == 200 else {}
            if data2.get("responseCode") == 200:
                tok2, exp2 = _extract_token_response(data2)
                if tok2:
                    _save_cached_token(vendor, tok2, exp2)
                    return tok2

            # Another worker may have won the race -- try DB one more time
            cached_tok2, _ = load_cached_token(vendor)
            if cached_tok2 and cached_tok2 != cached_tok:
                return cached_tok2

    raise ValueError(f"Could not obtain PrintSmith API token: {msg}")


# ── PDF fetch ───────────────────────────────────────────────────────

async def _api_get_pdf(config: Config, path: str) -> bytes:
    """GET a jobTicket endpoint; decode base64 PDF from JSON wrapper."""
    token = await get_valid_token(config)
    base = _setting(config, "printsmith_api_base_url", "PREPRESS_PRINTSMITH_API_BASE_URL").rstrip("/")
    if not base:
        base = _setting(config, "printsmith_api_base_url", "PRINTSMITH_API_BASE_URL").rstrip("/")
    if not base:
        raise ValueError("PrintSmith REST API base URL is not configured.")
    url = f"{base}{path}"

    try:
        async with httpx.AsyncClient(timeout=_HTTPX_TIMEOUT, verify=False) as client:
            r = await client.get(url, headers=_api_headers(token))
    except httpx.HTTPError as e:
        logger.warning("PrintSmith API HTTP error for %s: %s", path, e)
        raise ValueError("PrintSmith API request failed (network or HTTP error).") from e

    if r.status_code != 200:
        raise ValueError(f"PrintSmith API returned HTTP {r.status_code} for {path}")

    data = r.json()
    rc = data.get("responseCode", 0)
    msg = data.get("responseMessage", "")

    if rc == 400 and "token" in msg.lower():
        await invalidate_token(config)
        token = await get_valid_token(config)
        async with httpx.AsyncClient(timeout=_HTTPX_TIMEOUT, verify=False) as client:
            r = await client.get(url, headers=_api_headers(token))
        data = r.json()
        rc = data.get("responseCode", 0)
        msg = data.get("responseMessage", "")

    if rc != 200:
        raise ValueError(f"PrintSmith API error: {msg or 'unknown'}")

    b64_pdf = data.get("response", "")
    if not b64_pdf:
        raise ValueError("PrintSmith API returned empty PDF data.")

    pdf_bytes = base64.b64decode(b64_pdf)
    if not pdf_bytes or pdf_bytes[:4] != b"%PDF":
        raise ValueError("PrintSmith API response did not decode to a valid PDF.")

    return pdf_bytes


async def get_proxy_token(config: Config) -> str:
    """Borrow the current PrintSmith token from the configured token authority."""
    proxy_url = _setting(config, "printsmith_token_proxy_url", "PRINTSMITH_TOKEN_PROXY_URL").rstrip("/")
    proxy_key = _setting(config, "printsmith_token_proxy_key", "PRINTSMITH_TOKEN_PROXY_KEY")
    if not proxy_url or not proxy_key:
        raise ValueError("PrintSmith token proxy is not configured.")

    async with httpx.AsyncClient(timeout=_TOKEN_TIMEOUT) as client:
        r = await client.get(proxy_url, headers={"X-Token-Proxy-Key": proxy_key})

    if r.status_code == 401:
        raise ValueError("PrintSmith token proxy rejected this server.")
    if r.status_code != 200:
        raise ValueError(f"PrintSmith token proxy returned HTTP {r.status_code}.")

    data = r.json()
    token = str(data.get("token") or "")
    if not token:
        raise ValueError("PrintSmith token proxy returned no token.")
    return token


async def invalidate_token(config: Config) -> None:
    mode = _setting(
        config,
        "printsmith_token_authority_mode",
        "PRINTSMITH_TOKEN_AUTHORITY_MODE",
        "disabled",
    )
    if mode == "using_old_authority":
        proxy_url = _setting(config, "printsmith_token_proxy_url", "PRINTSMITH_TOKEN_PROXY_URL").rstrip("/")
        proxy_key = _setting(config, "printsmith_token_proxy_key", "PRINTSMITH_TOKEN_PROXY_KEY")
        if not proxy_url or not proxy_key:
            return
        invalidate_url = f"{proxy_url}/invalidate"
        try:
            async with httpx.AsyncClient(timeout=_TOKEN_TIMEOUT) as client:
                await client.post(invalidate_url, headers={"X-Token-Proxy-Key": proxy_key})
        except httpx.HTTPError:
            logger.warning("PrintSmith token proxy invalidate failed", exc_info=True)
        return

    vendor = _setting(config, "printsmith_api_vendor", "PREPRESS_PRINTSMITH_API_VENDOR", "LordTate")
    clear_cached_token(vendor)


# ── Public API ──────────────────────────────────────────────────────

async def fetch_invoice_ticket_pdf(config: Config, invoice_number: str) -> bytes:
    """Fetch the full invoice job ticket PDF."""
    return await _api_get_pdf(config, f"/jobTicket/{invoice_number}")


async def fetch_job_ticket_pdf(config: Config, invoice_number: str, job_index: int) -> bytes:
    """Fetch a single job part ticket PDF by invoice number + job index."""
    return await _api_get_pdf(config, f"/jobTicket/{invoice_number}/jobIndex/{job_index}")


def merge_pdf_bytes(parts: List[bytes]) -> bytes:
    if not parts:
        raise ValueError("No PDF parts to merge.")
    if len(parts) == 1:
        return parts[0]
    merger = PdfMerger()
    try:
        for blob in parts:
            merger.append(BytesIO(blob))
        out = BytesIO()
        merger.write(out)
        return out.getvalue()
    finally:
        merger.close()
