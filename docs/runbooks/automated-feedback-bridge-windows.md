# Automated feedback bridge after deploy (Windows, `bggol-vesko01`)

**Purpose:** After code lands on `main`, GitHub Actions already deploys **`RetrieverRebuild`** on **`127.0.0.1:8810`**. The remaining gap is **feedback the agent can read**: deploy outcomes, health/version, smoke results, and (later) realistic Fetch checks—**without copying logs through a clipboard.**

This complements:

- **`.github/workflows/deploy-retriever-rebuild-windows.yml`** — push and manual deploy to **`RetrieverRebuild` only**.
- **`docs/runbooks/github-actions-retriever-rebuild-deploy.md`** — runner install, labels, workflow inputs.
- **`deploy/WINDOWS_FETCH_RELEASE.md`** — production smoke semantics, **`FETCH_ENABLED`**, legacy coexistence.

## Guardrails (non-negotiable)

- **Legacy `Retriever` on port `8000`** stays out of deploy automation. Smoke may **read** legacy liveness only; never “fix” failing deploys by stopping or reconfiguring the old service.
- **Secrets:** Production URLs, database passwords, Cloudflare service tokens, and broker tokens belong **on the server** (for example under **`D:\retriever-rebuild\env\`**)—**not** in GitHub repository secrets for this design, unless policy changes explicitly.
- **Supported new-app port:** **`8810`** only (watch **`8710` vs `8810` typos** in tunnel/NSSM).

---

## Staged roadmap

### Phase A — Localhost-first feedback artifact (now)

**Implemented:** **`deploy/github-runner/post-deploy-feedback.ps1`**, invoked on every workflow run with **`if: always()`**, uploads **`retriever-rebuild-deploy-feedback`** (see **`docs/runbooks/github-actions-retriever-rebuild-deploy.md`** > **Part E**).

**Goal:** Right after a successful deploy on the **self-hosted Windows runner**, produce a **small, agent-readable bundle** that answers: *what revision is live, did health/smoke pass, is legacy still up?*

**Plain English contents (target):**

- Git SHA (or ref) that **`deploy.ps1`** actually deployed.
- Exit codes / pass-fail lines from **`healthcheck.ps1`** and **`smoke.ps1`** (or equivalent). **`RETRIEVER_SMOKE_EXPECT_FETCH_ENABLED`** governs Fetch-pilot assertions in **both** scripts; **`post-deploy-feedback.ps1`** **`-RunSmoke`** mirrors **`smoke.ps1`** expectations (fills the flag from **`retriever.env`** when process env does not).
- Redacted **`GET http://127.0.0.1:8810/version`** (and key **`/health/*`** fields if useful).
- **Read-only** legacy probe summary for **`localhost:8000`** when enabled (matches today’s “do not skip unless you mean it” posture).

**Delivery (current):**

1. **GitHub Actions artifact** — **`retriever-rebuild-deploy-feedback`** includes **`feedback.json`**, summary, and optional **`smoke-transcript.txt`**.
2. **Structured tail in the job log** — markers **`=== FEEDBACK_SUMMARY (concise) ===`** / **`=== End FEEDBACK_SUMMARY ===`** echo **`FEEDBACK_SUMMARY.md`**.
3. **On-server file** — optional future: mirror **`D:\retriever-rebuild\logs\last-deploy-feedback.json`** for RDP-only review (not required for remote agents today).

**Windows-specific notes:**

- Paths assume **`D:\retriever-rebuild`** layout per **`deploy/VM_SETUP_RUNBOOK.md`**.
- Runner account must read logs and invoke local HTTP to **`127.0.0.1`**; service restart rights are already a known prerequisite for **`deploy.ps1`**.

---

### Phase B — Public URL checks via Cloudflare Access (service token on box)

**Goal:** Confirm the **employee-facing path**—**`https://retriever.boonegraphics.net`** (or the agreed hostname)—returns expected responses **through Cloudflare Access**, using a **service token** stored **on `bggol-vesko01`**, not in the repo.

**Plain English approach:**

- Store **Cloudflare Access service token** credentials **only on the server** (env file or secret store IT approves). Do **not** paste them into GitHub org/repo secret UI unless leadership explicitly changes the threat model.
- Teach **`smoke.ps1`** (or a sibling script) to send **`CF-Access-Client-Id`** / **`CF-Access-Client-Secret`** **only when those variables are present** on the host, mirroring today’s optional **`RETRIEVER_SMOKE_CF_URL`** pattern described in **`github-actions-retriever-rebuild-deploy.md`**.
- Start with **safe GETs**: **`/health/live`**, **`/version`**, maybe an authenticated HTML route only after token proves out—avoid hammering write paths.

**Risks:**

- Misconfigured tokens look like “site down” vs “Access blocked”; tune messages so operators distinguish DNS/Access/app failures.
- Rate limits and audit: service tokens should use least privilege and **non-production identities** where possible.

---

### Phase C — Real Fetch prompt smoke (broker-enabled)

**Goal:** Once **`BOONEOPS_BROKER_ENABLED`**, **`FETCH_ENABLED`**, and related gates are deliberately on for a controlled window, add a **small number of deterministic prompts** that prove Fetch + broker plumbing **end-to-end** (not only localhost HTML).

** Preconditions (documentation-only reminder):**

- Follow **`docs/runbooks/booneops-broker-fetch-windows.md`** and **`deploy/WINDOWS_FETCH_RELEASE.md`** for **`BOONEOPS_*`**, Tailscale assumptions, and **`FETCH_GENERAL_QUESTIONS_ENABLED`** posture.
- Keep **legacy `8000`** liveness in the loop unless maintenance says otherwise.

**Scope discipline:**

- Prefer **one happy-path** and **one failure-path** test over a large matrix; heavy tests belong in scheduled maintenance or a dedicated job, not every push.

---

### Phase D — Agent-readable workflow summaries

**Goal:** Make **GitHub Actions** itself easy for an agent to consume: short **job summaries**, **stable artifact names**, and optional **markdown** emitted via workflow commands so “what happened?” is on the run’s front page.

**Examples of direction (implementation later):**

- Attach Phase A bundle as **`deploy-feedback`** (or similar) every run.
- Emit a **Summary** table: ref, smoke pass/fail, version string, legacy probe.

---

## What Master Tate gets

| Phase | Operator-visible | Agent-visible |
|--------|------------------|---------------|
| A | Same Windows logs as today | Artifact or log block with deploy + health + smoke + version |
| B | Access-protected public URL healthy | Same bundle extended with public URL checks |
| C | Fetch/broker path proven | Prompt-level proof in artifact (redacted) |
| D | Nicer GitHub UI | Faster parsing / less log noise |

---

## Open decisions (capture in `PLAN.md` when resolved)

- Exact **artifact format** (JSON schema vs plain text) and **max size** cap.
- Whether Phase B runs on **every push** or only **manual dispatch** / scheduled smoke (cost vs catch rate).
- Who owns **rotation** for the Cloudflare service token on the host.

---

## Related files

- **`PLAN.md`** — current phase and next session pointer.
- **`SESSION-LOG.md`** — when Phase A–D milestones land, log them here.
- **`DEPLOYMENT_BRIDGE.md`** — broader Cursor → GitHub → Boone lane (this doc is the **post-deploy feedback** slice).
