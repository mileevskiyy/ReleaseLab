from copy import deepcopy
from uuid import uuid4
import sqlite3
import pytest
from backend.store import Store
from backend.models import Approval, Queue, Advance, Create
from backend import domain


def test_workspace_isolation_and_unavailable_foreign_release():
    s = Store()
    a = s.create("One operator")
    b = s.create("Another operator")
    rid = s.get(a)["releases"][1]["id"]
    assert not any(r["id"] == rid for r in s.get(b)["releases"])
    with pytest.raises(domain.Fault):
        domain.release(s.get(b), rid)
    assert "receipts" not in s.snapshot(a)
    s.close()


def test_replaying_a_commit_is_idempotent_even_after_it_advances():
    s = Store()
    t = s.create("Operator")
    r = s.get(t)["releases"][1]
    a = Approval(
        request_id=uuid4(),
        version=1,
        note="Reviewed all recorded evidence in this sandbox.",
    )
    s.mutate(t, "approve:" + r["id"], a, lambda w, n: domain.approve(w, r["id"], a, n))
    q = Queue(
        request_id=uuid4(), release_id=r["id"], environment="production", generation=1
    )
    result = s.mutate(t, "queue", q, lambda w, n: domain.queue(w, q, n))
    oid = result["operation_id"]
    revision = s.get(t)["revision"]
    replay = s.mutate(t, "queue", q, lambda w, n: domain.queue(w, q, n))
    assert replay["replayed"]
    assert replay["operation_id"] == oid
    assert s.get(t)["revision"] == revision
    changed = q.model_copy(update={"generation": 2})
    with pytest.raises(domain.Fault, match="request ID"):
        s.mutate(t, "queue", changed, lambda w, n: domain.queue(w, changed, n))
    s.close()


def test_failed_write_rolls_back_the_environment_pointer_and_full_journal():
    s = Store()
    t = s.create("Operator")
    r = s.get(t)["releases"][1]
    a = Approval(
        request_id=uuid4(),
        version=1,
        note="Reviewed all recorded evidence in this sandbox.",
    )
    s.mutate(t, "approve", a, lambda w, n: domain.approve(w, r["id"], a, n))
    q = Queue(
        request_id=uuid4(), release_id=r["id"], environment="production", generation=1
    )
    oid = s.mutate(t, "queue", q, lambda w, n: domain.queue(w, q, n))["operation_id"]
    for phase in ["start", "verify"]:
        op = domain.operation(s.get(t), oid)
        data = Advance(request_id=uuid4(), version=op["version"], step=phase)
        s.mutate(t, "advance", data, lambda w, n: domain.advance(w, oid, data, n))
    before = s.get(t)
    op = domain.operation(before, oid)
    data = Advance(
        request_id=uuid4(), version=op["version"], step="health", healthy=True
    )
    s.db.execute(
        "CREATE TRIGGER fail_write BEFORE UPDATE OF payload ON workspaces BEGIN SELECT RAISE(ABORT,'forced'); END"
    )
    with pytest.raises(sqlite3.IntegrityError):
        s.mutate(t, "advance", data, lambda w, n: domain.advance(w, oid, data, n))
    assert s.get(t) == before
    s.close()


def test_environment_generation_change_and_manifest_tampering_are_caught_at_advance():
    for mode in ["generation", "manifest"]:
        s = Store()
        t = s.create("Operator")
        r = s.get(t)["releases"][1]
        a = Approval(
            request_id=uuid4(),
            version=1,
            note="Reviewed this candidate in the sandbox.",
        )
        s.mutate(t, "approve", a, lambda w, n: domain.approve(w, r["id"], a, n))
        q = Queue(
            request_id=uuid4(),
            release_id=r["id"],
            environment="production",
            generation=1,
        )
        oid = s.mutate(t, "queue", q, lambda w, n: domain.queue(w, q, n))[
            "operation_id"
        ]
        w = s.get(t)
        if mode == "generation":
            w["environments"]["production"]["generation"] += 1
        else:
            domain.release(w, r["id"])["manifest"]["build_ref"] = "tampered"
        import json

        s.db.execute(
            "UPDATE workspaces SET payload=? WHERE token=?", (json.dumps(w), s.hash(t))
        )
        data = Advance(request_id=uuid4(), version=1, step="start")
        result = s.mutate(
            t, "advance", data, lambda w, n: domain.advance(w, oid, data, n)
        )
        assert domain.operation(result["workspace"], oid)["state"] == "failed"
        s.close()


def test_idle_expiry_and_optional_file_persistence(tmp_path):
    now = [1000]
    path = str(tmp_path / "release.sqlite")
    s = Store(path, clock=lambda: now[0])
    t = s.create("Operator")
    rid = s.get(t)["releases"][1]["id"]
    s.close()
    s = Store(path, clock=lambda: now[0])
    assert s.get(t)["releases"][1]["id"] == rid
    now[0] += 86400001
    with pytest.raises(domain.Fault, match="expired"):
        s.get(t)
    s.close()
