# Secrets Handling

**Status:** planning document  
**Scope:** production, development, and agent-visible secrets for the Retriever rebuild  
**Security source:** [Cursor Security](https://cursor.com/security)

## Plain-English Summary

Cursor can help build Retriever, but Cursor should not become Retriever's secret vault.

Production secrets belong in Boone-controlled storage on the production side. Cursor should see templates, names, and redacted examples, not live keys unless Master Tate explicitly chooses a narrow exception.

## Secret Classes

Known or likely Retriever secrets:

- Cloudflare Access and Tunnel credentials
- Retriever session/cookie signing keys
- BooneOps broker bearer token
- BooneOps broker HMAC signing secret
- Switch webhook secret
- PrintSmith token proxy key
- PrintSmith REST credentials
- MIS Postgres credentials
- MySQL credentials
- Switch API credentials
- Anthropic API key
- Vertex credentials
- web-search provider keys
- future report-job signing secrets

## Cursor Boundary

Allowed in Cursor:

- `.env.example`
- redacted config samples
- local-only throwaway development secrets
- secret names and required variable documentation
- validation code that fails when required secrets are missing
- deployment scripts that read secrets on the Boone server

Not allowed in Cursor by default:

- production `.env` files
- PrintSmith REST credentials
- database passwords
- broker signing secrets
- Cloudflare Tunnel credentials
- long-lived production service account keys
- raw screenshots or logs that expose secrets

## Privacy Mode And Model Handling

Cursor's published security posture includes Privacy Mode and zero data retention terms with model providers when Privacy Mode is enabled. Use that as development-environment protection, not as permission to expose production secrets.

Project rule:

- keep Privacy Mode enabled for Retriever rebuild work
- do not paste production secrets into prompts
- do not ask agents to infer or reconstruct secrets
- do not store secrets in planning docs
- use redacted examples such as `PRINTSMITH_REST_PASSWORD=<redacted>`

## Storage Recommendation

First production version should use a Boone-controlled secret source:

- production env file readable only by the service account, or
- OS-level secret manager if already available on the Boone server, or
- another approved Boone-controlled vault

Do not make 1Password, Cursor, chat transcripts, or agent memory the production runtime dependency unless that is explicitly designed and approved later.

## Required Config Behavior

Production should hard-fail when required secrets are missing.

Do not preserve old development backdoors:

- no insecure default cookie secret
- no auto-created `admin/admin123`
- no `AUTH_ENABLED=false` production mode
- no fallback PrintSmith credentials
- no silent downgrade from signed broker calls to unsigned calls

## Rotation And Incident Rules

Each secret should eventually have:

- owner
- storage location
- rotation method
- last rotated date
- affected service
- safe restart procedure
- emergency revoke procedure

If a secret is exposed to Cursor, a chat transcript, a log, Git, or a screenshot, treat it as compromised and rotate it.

## Open Questions

- Which production secret store will Boone use for first launch?
- Who can read and rotate each production secret?
- How are local development secrets separated from production secrets?
- How will old PrintSmith token authority be preserved without copying raw credentials into the rebuild workspace?
