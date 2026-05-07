# Webhook And Broker Auth

**Status:** planning document  
**Scope:** machine-to-machine auth for Retriever, BooneOps, Switch webhooks, and future service tools  
**Security source:** [Cursor Security](https://cursor.com/security)

## Plain-English Summary

Machine credentials are not user permissions, and development credentials are not production credentials.

Cursor can help design and test webhook/broker contracts. It should not hold the live bearer tokens, HMAC secrets, PrintSmith token proxy keys, or Switch webhook secrets that production Retriever depends on.

## Current Known Machine Paths

Known paths from old Retriever and the review:

- BooneOps broker bearer token
- BooneOps broker HMAC signing secret
- Switch review webhook shared secret
- PrintSmith token proxy shared key
- future LAN action-service signing secret
- future report-job worker signing secret

These should be designed as one consistent machine-to-machine auth model instead of several accidental shared-header patterns.

## Credential Separation

Use separate credentials for:

- local development
- Cursor/agent testing
- staging or test runtime
- production Retriever
- production broker
- production webhooks

Never reuse:

- Cursor MCP credential as Retriever production credential
- local dev token as production token
- Switch webhook secret as broker secret
- PrintSmith token proxy key as general service key

## Recommended Pattern

For Retriever-to-service calls:

- HTTPS only
- service-specific bearer token or mTLS if later justified
- HMAC signature over request body
- timestamp header
- nonce or request ID
- short replay window
- strict audience/service name
- structured error codes
- correlation ID in both systems

For incoming webhooks:

- verify shared secret or signature before parsing privileged payloads
- reject missing, expired, or mismatched signatures
- log accepted and rejected attempts
- separate customer/public webhook endpoints from internal service endpoints
- do not rely on source IP alone

## Cursor And MCP Boundary

Cursor's security page points to MCP and agent security guidance. For this project, that means:

- development MCP tools can help inspect docs, browser state, or non-secret local systems
- production Retriever service tools need their own auth and audit
- Cursor MCP tokens must not be copied into Retriever runtime config
- Retriever broker tokens must not be exposed to Cursor agents by default
- any agent-authored tool contract must include auth failure tests and audit behavior

## BooneOps Light And Medium

BooneOps level is a user/business authorization concept. Broker credentials are service credentials.

The broker should receive:

- authenticated Retriever service identity
- user identity from Retriever
- user's BooneOps level
- requested action or report
- correlation ID

The broker should not trust a user-supplied bot ID without Retriever-side authorization.

Open mapping decision:

- BooneOps Light likely maps to the old normal employee broker behavior.
- BooneOps Medium likely maps to scheduled/reporting behavior.
- The final mapping to old `booneops.production`, `booneops.admin`, and `booneops.super` bot IDs still needs an explicit decision before implementation.

## PrintSmith Token Authority

Old Retriever is currently the shared PrintSmith REST token authority. The rebuild must not accidentally create competing token owners.

Before cutover:

- preserve old `/api/printsmith-token` and invalidate behavior, or
- replace it with an equivalent M2M token authority, or
- move token ownership to a clearly documented service

Cursor should document and test this flow with redacted examples only.

## Required Tests

Before production:

- valid broker request succeeds
- missing bearer token fails
- bad HMAC fails
- replayed timestamp fails
- wrong service audience fails
- user without BooneOps level is denied
- `/printsmith` read-only request cannot become a write
- Switch webhook missing secret fails
- PrintSmith token proxy rejects wrong key
- audit log records accepted and rejected calls

## Open Questions

- Does the broker contract change for BooneOps Medium?
- Where are service credentials stored on the Boone server?
- What replay window is acceptable?
- Are service credentials rotated manually or on a schedule?
- Which services need inbound access through Cloudflare/Tailscale versus LAN-only paths?
