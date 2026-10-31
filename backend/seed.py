from hashlib import sha256
from uuid import uuid4
from .models import Manifest, digest
from .domain import HOUR


def candidate(manifest, notes, now, sample=False):
    return {
        "id": str(uuid4()),
        "manifest": manifest.model_dump(mode="json"),
        "digest": digest(manifest),
        "notes": notes,
        "created_at": now,
        "version": 1,
        "evidence": [],
        "approvals": [],
        "sample": sample,
    }


def seed(actor, now):
    w = {
        "revision": 0,
        "created_at": now,
        "actor": actor,
        "service": "atlas-api",
        "releases": [],
        "operations": [],
        "environments": {},
        "events": [],
        "receipts": [],
        "next_operation": 3,
    }
    for version, notes in [
        ("1.4.0", "Sample baseline: the previously verified API contract."),
        (
            "1.5.0",
            "Add a searchable order-history endpoint and preserve the existing response fields.",
        ),
        (
            "1.6.0",
            "Candidate for a later iteration. Recorded API evidence needs attention.",
        ),
    ]:
        m = Manifest(
            version=version,
            source_commit=sha256(("sample-" + version).encode()).hexdigest()[:40],
            build_ref="sample-build-" + version,
            dependencies=[{"name": "core-runtime", "version": "3.2.1"}],
            migrations=(
                [{"name": "add_history_index", "backward_compatible": True}]
                if version != "1.4.0"
                else []
            ),
            config_keys=["LOG_LEVEL", "REQUEST_TIMEOUT"],
        )
        r = candidate(m, notes, now, sample=True)
        r["evidence"].append(
            {
                "id": str(uuid4()),
                "digest": r["digest"],
                "checks": {
                    "unit": "passed",
                    "api": "failed" if version == "1.6.0" else "passed",
                    "security": "passed",
                },
                "note": "Seeded demonstration evidence; no CI job was executed.",
                "at": now,
                "actor": "Sample fixture",
                "provenance": "sample-fixture",
                "sample": True,
            }
        )
        w["releases"].append(r)
    for i, (environment, r) in enumerate(
        [("production", w["releases"][0]), ("staging", w["releases"][1])], 1
    ):
        oid = str(uuid4())
        op = {
            "id": oid,
            "sequence": i,
            "kind": "deploy",
            "environment": environment,
            "release_id": r["id"],
            "digest": r["digest"],
            "state": "succeeded",
            "version": 4,
            "expected_generation": 0,
            "evidence_id": r["evidence"][-1]["id"],
            "approval_id": None,
            "restore_target": None,
            "reason": "Seeded sample deployment.",
            "failure": None,
            "created_at": now,
            "updated_at": now,
            "finished_at": now,
            "actor": "Sample fixture",
            "sample": True,
            "steps": [
                {"state": state, "at": now, "note": "Seeded sample lifecycle."}
                for state in ["queued", "running", "verifying", "succeeded"]
            ],
        }
        w["operations"].append(op)
        w["environments"][environment] = {
            "release_id": r["id"],
            "digest": r["digest"],
            "generation": 1,
            "operation_id": oid,
            "updated_at": now,
        }
    return w
