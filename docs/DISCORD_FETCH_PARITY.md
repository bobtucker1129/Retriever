# Discord vs Fetch parity — where to read details

The **canonical** audit, harness location, nondeterminism notes, and intentional non-goals for the Discord–Fetch parity program are maintained next to the BooneOps broker:

- [`../booneops-bots/docs/DISCORD_FETCH_PARITY.md`](../booneops-bots/docs/DISCORD_FETCH_PARITY.md)

Retriever work stays in this repo (`app/fetch`, broker client, UI). Broker routing, gateway envelope construction, and `npm test` parity harness live under `projects/booneops-bots`.

**Fetch-only transport errors** (HTTP timeout, connect failure, 401, non-JSON, repeated 5xx) are centralized in [`app/fetch/broker_user_visible_copy.py`](../app/fetch/broker_user_visible_copy.py) so copy can stay aligned with Discord-style phrasing where sensible; JSON `errors[]` paths still use broker messages via `build_broker_message_presentation`.
