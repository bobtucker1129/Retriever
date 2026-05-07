# Audit Log Design

**Status:** planning document  
**Scope:** Retriever app audit logs and development/agent audit trail  
**Security source:** [Cursor Security](https://cursor.com/security)

## Plain-English Summary

Retriever needs two different audit stories:

1. **App audit logs:** what employees and services did inside Retriever.
2. **Development audit trail:** how Cursor/OpenClaw helped create and deploy the code.

Cursor's security posture helps with development trust, but it does not replace Retriever's own logs. Production Retriever must record its own important user, tool, report, admin, and machine-to-machine events.

## App Audit Levels

### Light Audit

For ordinary Fetch read and LLM interactions:

- timestamp
- user identity
- module
- route used
- capability checked
- model/tool family
- success/failure
- request ID
- token/cost summary when available

Do not log full sensitive prompts by default until retention and redaction are decided.

### Standard Audit

For workflow and app-data writes:

- everything in Light Audit
- action name
- target record type
- target record ID
- before/after summary when practical
- validation result
- error category if failed

### Strict Audit

For PrintSmith/Postgres writes, Switch actions, LAN action-service calls, scheduled reports, admin changes, and secret/config changes:

- log requested before execution
- log succeeded or failed after execution
- user or service identity
- capability or service credential used
- validated payload summary
- correlation ID
- source IP or service origin when available
- approval reference when required

## Minimum First Schema

Minimum viable fields:

- `id`
- `timestamp`
- `actor_type` (`user`, `service`, `agent`, `system`)
- `actor_id`
- `module`
- `action`
- `route`
- `capability`
- `target_type`
- `target_id`
- `risk_level` (`light`, `standard`, `strict`)
- `result` (`requested`, `succeeded`, `failed`, `denied`)
- `request_id`
- `correlation_id`
- `error_category`
- `metadata_redacted`

## Cursor And Agent Audit Trail

Cursor-authored work should be auditable through development artifacts, not production app logs.

Use:

- git commit hashes
- pull request descriptions
- review comments
- deployment logs
- `/version` endpoint output
- session logs in project documents
- explicit operator notes for production actions

Do not rely on:

- chat memory as the only record
- Cursor transcript as canonical production audit
- agent claims without a file path, command output, commit hash, or deployment artifact

## MCP And Tool Calls

If Retriever uses MCP-like tools or brokered services, audit each production tool call at the Retriever boundary.

Record:

- user who requested it
- service that executed it
- route/tool name
- whether it touched `/printsmith`, `/docs`, upload data, or a future write path
- payload summary after redaction
- result
- request ID

Cursor MCP access for development must not share credentials with Retriever production MCP/service access. If a Cursor agent calls a development MCP tool, that is development activity. If Retriever calls a production tool, that is app activity and belongs in Retriever audit logs.

## Privacy And Retention

Open decisions:

- where audit logs live
- retention period
- who can read them
- how sensitive prompts are redacted
- whether logs are append-only
- whether tamper evidence is needed for first launch
- how logs are exported for review

Default recommendation:

- start in MySQL `retriever_cloudflare.audit_events`, with optional append-only file mirroring to `/var/log/retriever-rebuild/audit.jsonl`
- log metadata by default
- redact full prompts and uploaded text unless explicitly needed
- use correlation IDs so detailed troubleshooting can happen without exposing everything by default

## Events Required Before Launch

At minimum, audit:

- Cloudflare identity accepted by Retriever
- pending user created
- user activated/suspended/blocked
- capability changed
- BooneOps level changed
- Fetch `/printsmith` query
- Fetch `/docs` query
- Fetch upload
- delayed report created
- delayed report completed/failed
- artifact downloaded
- broker auth rejected
- production write action requested, when those modules exist
- machine-to-machine webhook accepted/rejected

## Current Storage Decision

First audit store: MySQL table `retriever_cloudflare.audit_events`.

Optional runtime mirror: `/var/log/retriever-rebuild/audit.jsonl` for local operator visibility and emergency troubleshooting.

Do not store full prompts, uploaded customer text, bearer tokens, HMAC signatures, PrintSmith tokens, proxy keys, or raw authorization headers by default.

## Open Questions

- Who can read audit logs besides Master Tate?
- What retention period is acceptable for Fetch metadata?
- Are full prompts ever stored, and under what approval?
- How do we redact customer-upload text while preserving troubleshooting value?
