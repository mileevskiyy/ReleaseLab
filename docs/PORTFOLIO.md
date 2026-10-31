# ReleaseLab — portfolio wording

## CV

**ReleaseLab — release-control and rollback rehearsal platform** | Python, FastAPI, React, TypeScript, SQLite

- Built a release-rehearsal control plane linking immutable manifest identities, recorded build evidence, staging prerequisites and version-bound production sign-off.
- Implemented explicit deployment/restore state machines with optimistic operation versions, per-environment generation checks and idempotent command receipts.
- Preserved active environment state on failed health signals or stale gates, with atomic before/after audit snapshots and exportable evidence records.
- Developed domain, storage, HTTP and browser tests for gate expiry, concurrent-state conflicts, artifact identity, rollback targets and forced transaction failure.

## LinkedIn project description

ReleaseLab is a full-stack sandbox for exploring release-control correctness before connecting an orchestrator to real infrastructure. It models immutable candidates, recorded build evidence, staging verification, single-operator sign-off, promotion attempts and restoration from successful history.

The core concern is consistency across decisions. A queued operation captures the artifact digest, evidence/sign-off references and environment generation. Each step rechecks those references. A newer evidence record, expired gate, changed staging candidate or stale generation stops the attempt while preserving the active artifact. A successful health outcome commits the pointer, operation state, request receipt and audit snapshots together in SQLite.

The React interface provides a candidate workbench, environment register, manifest comparison, operation journal and evidence exports. The adapter deliberately changes only simulated environment pointers. Build outcomes and health signals are explicitly marked as manual sandbox inputs; the repository separately runs actual application tests in GitHub Actions.

## Interview discussion points

- Why is a manifest digest different from an image digest or a signed attestation?
- Why must sign-off refer to an evidence record ID rather than only a version string?
- What can change between queue admission and final activation?
- How do generation checks, operation versions and idempotency protect different boundaries?
- Why does a failed rehearsal preserve the previously active artifact?
- Why can artifact restoration not be treated as database rollback?
- What identity, provenance and adapter boundaries must be added before real deployments?

Do not describe the sandbox as production cloud deployment infrastructure, a security scanner, signed CI integration, independent approval workflow or a system with measured real-world deployment impact.
