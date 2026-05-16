"""General conversation model client for Fetch."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional, Sequence

import httpx

from app.config import AppSettings
from app.db.repositories.fetch import FetchMessageRecord

ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
_DEFAULT_TIMEOUT_SECONDS = 45.0
_DEFAULT_MAX_TOKENS = 1200

HttpPostFn = Callable[..., Any]


@dataclass(frozen=True)
class GeneralLlmTurnResult:
    assistant_text: str
    context_state: str
    model_label: Optional[str]
    metadata: Optional[dict[str, Any]] = None


def should_use_general_llm(route: str, settings: AppSettings) -> bool:
    """Normal conversation routes use the configured LLM directly."""
    if not settings.fetch_enabled:
        return False
    if _normalize_provider(settings.model_provider) != "anthropic":
        return False
    if not (settings.anthropic_api_key or "").strip():
        return False
    return route in {"general_candidate", "local", "unknown"}


def resolve_anthropic_model_id(model_default: Optional[str]) -> str:
    """Accept friendly labels from env while sending Anthropic a real model id."""
    raw = (model_default or "").strip()
    if not raw:
        return "claude-opus-4-7"
    low = raw.lower().replace("_", " ").replace("-", " ")
    if raw.startswith("claude-"):
        return raw
    if "opus" in low and "4.7" in low:
        return "claude-opus-4-7"
    if "opus" in low and "4 7" in low:
        return "claude-opus-4-7"
    if "sonnet" in low and ("4.6" in low or "4 6" in low):
        return "claude-sonnet-4-6"
    return raw


def call_general_conversation_llm(
    settings: AppSettings,
    *,
    user_message: str,
    prior_records: Sequence[FetchMessageRecord],
    http_post: HttpPostFn = httpx.post,
) -> GeneralLlmTurnResult:
    """Call Anthropic Messages for ordinary Fetch chat."""
    provider = _normalize_provider(settings.model_provider)
    if provider != "anthropic":
        return _configuration_error_result("Fetch general chat currently supports Anthropic only.")

    api_key = (settings.anthropic_api_key or "").strip()
    if not api_key:
        return _configuration_error_result("Fetch general chat is missing ANTHROPIC_API_KEY.")

    model_id = resolve_anthropic_model_id(settings.model_default)
    payload = {
        "model": model_id,
        "max_tokens": _DEFAULT_MAX_TOKENS,
        "system": _general_chat_system_prompt(),
        "messages": _anthropic_messages_from_history(prior_records, user_message),
    }
    headers = {
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
        "x-api-key": api_key,
    }

    try:
        response = http_post(
            ANTHROPIC_MESSAGES_URL,
            headers=headers,
            json=payload,
            timeout=_DEFAULT_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
    except httpx.TimeoutException:
        return _transient_error_result(
            "Claude took too long to respond. Your message was saved; try again in a moment.",
            model_id,
        )
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code if exc.response is not None else None
        if status and 400 <= status < 500:
            return _configuration_error_result(
                "Claude rejected the request. Check the configured model name and API key.",
                model_id,
            )
        return _transient_error_result(
            "Claude is temporarily unavailable. Your message was saved; try again in a moment.",
            model_id,
        )
    except (httpx.HTTPError, ValueError):
        return _transient_error_result(
            "Fetch could not reach Claude for that general chat request. Your message was saved.",
            model_id,
        )

    text = _assistant_text_from_anthropic_response(data)
    if not text:
        return _transient_error_result(
            "Claude returned an empty response. Your message was saved; try again in a moment.",
            model_id,
        )

    usage = data.get("usage") if isinstance(data, dict) else None
    metadata: dict[str, Any] = {
        "general_llm_provider": "anthropic",
        "general_llm_model_id": model_id,
    }
    if isinstance(usage, dict):
        for key in ("input_tokens", "output_tokens"):
            if isinstance(usage.get(key), int):
                metadata[f"general_llm_{key}"] = usage[key]
    return GeneralLlmTurnResult(
        assistant_text=text,
        context_state="llm",
        model_label=model_id,
        metadata=metadata,
    )


def _anthropic_messages_from_history(
    prior_records: Sequence[FetchMessageRecord],
    user_message: str,
    *,
    limit: int = 12,
) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    for rec in prior_records[-limit:]:
        if rec.role not in {"user", "assistant"}:
            continue
        text = (rec.content or "").strip()
        if not text:
            continue
        messages.append({"role": rec.role, "content": text})
    messages.append({"role": "user", "content": user_message})
    return _merge_adjacent_roles(messages)


def _merge_adjacent_roles(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    merged: list[dict[str, str]] = []
    for message in messages:
        role = message["role"]
        content = message["content"]
        if merged and merged[-1]["role"] == role:
            merged[-1]["content"] = f"{merged[-1]['content']}\n\n{content}"
        else:
            merged.append({"role": role, "content": content})
    return merged


def _assistant_text_from_anthropic_response(data: Any) -> str:
    if not isinstance(data, dict):
        return ""
    blocks = data.get("content")
    if not isinstance(blocks, list):
        return ""
    parts: list[str] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text" and isinstance(block.get("text"), str):
            text = block["text"].strip()
            if text:
                parts.append(text)
    return "\n\n".join(parts).strip()


def _normalize_provider(provider: Optional[str]) -> str:
    return (provider or "").strip().lower()


def _general_chat_system_prompt() -> str:
    return (
        "You are Fetch, a friendly assistant inside Boone Graphics' Retriever app. "
        "For ordinary conversation, answer naturally and helpfully like Claude. "
        "Do not claim you used BooneOps, PrintSmith, MIS, web search, or live sports/news tools "
        "unless the user explicitly asks for an internal routed task and the app routes it there. "
        "If a question needs real-time information, be clear that you may not have live data and "
        "answer with that limitation."
    )


def _configuration_error_result(message: str, model_id: Optional[str] = None) -> GeneralLlmTurnResult:
    return GeneralLlmTurnResult(
        assistant_text=message,
        context_state="error",
        model_label=model_id,
        metadata={"general_llm_provider": "anthropic", "general_llm_error": "configuration"},
    )


def _transient_error_result(message: str, model_id: str) -> GeneralLlmTurnResult:
    return GeneralLlmTurnResult(
        assistant_text=message,
        context_state="error",
        model_label=model_id,
        metadata={"general_llm_provider": "anthropic", "general_llm_error": "transient"},
    )
