# Domain model, API and invariants

## Workspace aggregate

SQLite stores `workspaces(token, touched, payload)`. The token is a SHA-256 digest of a random cookie. The aggregate holds the operator label, immutable candidates, evidence/sign-off histories, operations, environment pointers, audit records and request receipts. Each request resolves only the cookie-bound workspace.

A candidate has a manifest digest and a concurrency version. Recording evidence or approval advances that version without changing the immutable manifest. An operation has a separate version and captured gate references. Each environment has an independently incrementing generation and points to its current successful operation.

## Mutation transaction

1. Begin `IMMEDIATE` and load the unexpired workspace.
2. Canonicalize action and validated payload; exclude the request ID itself.
3. Return a harmless replay for an existing matching request receipt, or reject a reused key with changed content.
4. Validate the domain transition against current state.
5. Apply the change; append an actor-attributed audit event with before/after environment snapshots.
6. Increment workspace revision, retain the latest 200 audit entries and add a request receipt.
7. Check serialized byte limits, save and commit.
8. Roll back the whole aggregate on any exception.

Receipt history is retained until workspace expiry or its 2,000-command limit. Truncating displayed audit history does not permit re-execution of an old request key. Client pending keys are in-memory retry aids, not durable offline commands.

## Promotion admission

A normal queue request identifies the candidate, environment and expected generation. It rejects a competing active operation in that environment. Fresh passing evidence must match the digest. Production additionally requires the current exact staging candidate, declared migration compatibility and an unexpired sign-off tied to the latest evidence.

The queued operation captures digest, expected environment generation, evidence ID and production approval ID. At each valid advance step, these prerequisites are checked again. A changed gate turns the existing operation into a recorded terminal failure, preserving the active pointer. A malformed or stale step/version request is rejected before any transition.

Only a healthy final step updates the pointer and increments generation. The operation's successful state, journal step, environment, audit snapshots and receipt commit together. This protects the boundary even if a client retries after losing a response.

## Restore admission

A restore chooses an earlier successful journal entry from the same environment. It cannot target the already active artifact and must precede the current successful operation's sequence. The reason is retained. Fresh evidence/sign-off gates are intentionally bypassed, while identity, generation, target success and health checks remain enforced.

This models emergency artifact-pointer restoration, not reversal of database migrations. The system does not execute external changes; this distinction remains visible in the UI and export format.

## Evidence and provenance

Manifest SHA-256 identifies sorted-key JSON serialization, with array order preserved. It is not an OCI image digest or signed artifact attestation. Source commit/build fields are recorded strings. Dependency versions support only stable three-part cores; names and configuration key names are bounded and validated.

Evidence records are immutable, with the exact digest, per-check statuses, actor, timestamp, note and provenance `manual-sandbox` or `sample-fixture`. Seeded deployments are labeled samples; the initial audit is empty. The repository CI tests this application independently from the demonstration check records.

Sign-off is a single anonymous operator's recorded decision. Its relation to digest and evidence is checked; operator identity, independence and cryptographic authenticity are not established.

## API

| Method | Path                          | Purpose                                                |
| ------ | ----------------------------- | ------------------------------------------------------ |
| GET    | `/api/health`                 | Service health                                         |
| POST   | `/api/demo`                   | Create an isolated seeded workspace                    |
| GET    | `/api/session`                | Session presence and CSRF token                        |
| GET    | `/api/workspace`              | Snapshot with current gate evaluation                  |
| POST   | `/api/releases`               | Register immutable candidate                           |
| POST   | `/api/releases/:id/evidence`  | Append manual evidence with expected candidate version |
| POST   | `/api/releases/:id/approve`   | Record sign-off with expected candidate version        |
| POST   | `/api/operations`             | Queue normal promotion                                 |
| POST   | `/api/restores`               | Queue restore from successful history                  |
| POST   | `/api/operations/:id/advance` | Versioned start/verify/health/cancel command           |
| GET    | `/api/releases/:id/export`    | Download candidate evidence and related journal/audit  |

Pydantic forbids unexpected fields. The server assigns actor/time/provenance; clients cannot inject another audit actor. API data is not cached, body limits cover streamed content, and all mutations except workspace creation require session CSRF. Browser Origin headers are checked.

## Operating model

This is a single-process FastAPI application. Synchronous request handlers share a locked SQLite connection. Domain functions perform no network I/O or arbitrary code execution. The default database is in memory; optional file storage changes restart persistence, not expiry or the identity model. Multi-worker operation would require coordinated admission and persistence design before deployment.
