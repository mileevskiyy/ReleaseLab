from uuid import uuid4
from copy import deepcopy
import pytest
from pydantic import ValidationError
from backend.models import (
    Create,
    Evidence,
    Approval,
    Queue,
    Restore,
    Advance,
    Manifest,
    digest,
    version_tuple,
)
from backend.store import Store
from backend import domain


def setup():
    now = [1800000000000]
    s = Store(clock=lambda: now[0])
    t = s.create("Operator")
    return s, t, now


def cmd(cls, **kwargs):
    return cls(request_id=uuid4(), **kwargs)


def sign(s, t, rid=None):
    w = s.get(t)
    r = next(r for r in w["releases"] if r["id"] == rid) if rid else w["releases"][1]
    data = cmd(
        Approval,
        version=r["version"],
        note="Reviewed this artifact and its evidence in the sandbox.",
    )
    return s.mutate(
        t,
        "approve:" + r["id"],
        data,
        lambda w, now: domain.approve(w, r["id"], data, now),
    )


def enqueue(s, t, rid=None, env="production"):
    w = s.get(t)
    rid = rid or w["releases"][1]["id"]
    data = cmd(
        Queue,
        release_id=rid,
        environment=env,
        generation=w["environments"][env]["generation"],
    )
    return s.mutate(t, "queue", data, lambda w, now: domain.queue(w, data, now))


def step(s, t, oid, phase, healthy=None, note=""):
    op = domain.operation(s.get(t), oid)
    data = cmd(Advance, version=op["version"], step=phase, healthy=healthy, note=note)
    return s.mutate(
        t, "advance:" + oid, data, lambda w, now: domain.advance(w, oid, data, now)
    )


def record(s, t, rid, status="passed"):
    r = domain.release(s.get(t), rid)
    data = cmd(
        Evidence,
        version=r["version"],
        unit="passed",
        api=status,
        security="passed",
        note="Manually recorded sandbox outcomes.",
    )
    return s.mutate(
        t, "evidence:" + rid, data, lambda w, now: domain.evidence(w, rid, data, now)
    )


def healthy(s, t, oid):
    step(s, t, oid, "start")
    step(s, t, oid, "verify")
    return step(s, t, oid, "health", True)


def test_seed_is_explicitly_sample_and_has_no_fictional_audit_events():
    s, t, _ = setup()
    w = s.snapshot(t)
    assert len(w["operations"]) == 2
    assert all(o["sample"] for o in w["operations"])
    assert all(r["sample"] for r in w["releases"])
    assert w["events"] == []
    assert "receipts" not in w
    s.close()


def test_production_needs_signoff_and_then_commits_only_after_healthy_outcome():
    s, t, _ = setup()
    before = deepcopy(s.get(t)["environments"]["production"])
    with pytest.raises(domain.Fault, match="sign-off"):
        enqueue(s, t)
    sign(s, t)
    r = enqueue(s, t)
    oid = r["operation_id"]
    assert s.get(t)["environments"]["production"] == before
    step(s, t, oid, "start")
    step(s, t, oid, "verify")
    assert s.get(t)["environments"]["production"] == before
    w = step(s, t, oid, "health", True)["workspace"]
    assert w["environments"]["production"]["generation"] == before["generation"] + 1
    assert w["environments"]["production"]["release_id"] == w["releases"][1]["id"]
    assert w["events"][-1]["before"]["production"]["generation"] == 1
    assert w["events"][-1]["after"]["production"]["generation"] == 2
    s.close()


def test_failing_health_preserves_environment_and_records_terminal_failure():
    s, t, _ = setup()
    sign(s, t)
    oid = enqueue(s, t)["operation_id"]
    step(s, t, oid, "start")
    step(s, t, oid, "verify")
    before = deepcopy(s.get(t)["environments"])
    result = step(s, t, oid, "health", False, note="Reported unhealthy in the sandbox.")
    assert result["workspace"]["environments"] == before
    assert domain.operation(s.get(t), oid)["state"] == "failed"
    s.close()


def test_staging_requires_passing_evidence_but_not_production_signoff():
    s, t, _ = setup()
    rid = s.get(t)["releases"][2]["id"]
    with pytest.raises(domain.Fault, match="Recorded checks"):
        enqueue(s, t, rid, "staging")
    record(s, t, rid)
    oid = enqueue(s, t, rid, "staging")["operation_id"]
    healthy(s, t, oid)
    assert s.get(t)["environments"]["staging"]["release_id"] == rid
    s.close()


def test_old_evidence_cannot_be_signed_off_or_promoted():
    s, t, now = setup()
    now[0] += domain.HOUR + 1
    with pytest.raises(domain.Fault):
        sign(s, t)
    with pytest.raises(domain.Fault, match="freshness"):
        enqueue(s, t)
    s.close()


def test_new_evidence_invalidates_earlier_signoff_even_if_still_passing():
    s, t, _ = setup()
    sign(s, t)
    rid = s.get(t)["releases"][1]["id"]
    record(s, t, rid)
    with pytest.raises(domain.Fault, match="sign-off"):
        enqueue(s, t)
    sign(s, t, rid)
    assert enqueue(s, t, rid)["operation_id"]
    s.close()


def test_changed_evidence_stops_an_already_queued_operation():
    s, t, _ = setup()
    sign(s, t)
    oid = enqueue(s, t)["operation_id"]
    rid = s.get(t)["releases"][1]["id"]
    record(s, t, rid, "failed")
    before = deepcopy(s.get(t)["environments"])
    w = step(s, t, oid, "start")["workspace"]
    assert domain.operation(w, oid)["state"] == "failed"
    assert "changed" in domain.operation(w, oid)["failure"]
    assert w["environments"] == before
    s.close()


def test_gate_expiry_during_verification_prevents_commit():
    s, t, now = setup()
    sign(s, t)
    oid = enqueue(s, t)["operation_id"]
    step(s, t, oid, "start")
    step(s, t, oid, "verify")
    now[0] += domain.HOUR + 1
    w = step(s, t, oid, "health", True)["workspace"]
    assert domain.operation(w, oid)["state"] == "failed"
    assert w["environments"]["production"]["generation"] == 1
    s.close()


def test_staging_changes_while_production_is_queued_block_the_old_candidate():
    s, t, _ = setup()
    sign(s, t)
    production = enqueue(s, t)["operation_id"]
    rid = s.get(t)["releases"][2]["id"]
    record(s, t, rid)
    staging = enqueue(s, t, rid, "staging")["operation_id"]
    healthy(s, t, staging)
    w = step(s, t, production, "start")["workspace"]
    assert domain.operation(w, production)["state"] == "failed"
    assert "staging" in domain.operation(w, production)["failure"]
    assert w["environments"]["production"]["generation"] == 1
    s.close()


def test_environment_lock_and_generation_check_reject_competing_queues():
    s, t, _ = setup()
    sign(s, t)
    enqueue(s, t)
    with pytest.raises(domain.Fault, match="active rehearsal"):
        enqueue(s, t)
    data = cmd(
        Queue,
        release_id=s.get(t)["releases"][1]["id"],
        environment="production",
        generation=0,
    )
    with pytest.raises(domain.Fault, match="generation"):
        s.mutate(t, "queue", data, lambda w, now: domain.queue(w, data, now))
    s.close()


def test_invalid_step_and_stale_operation_version_cannot_mutate_state():
    s, t, _ = setup()
    sign(s, t)
    oid = enqueue(s, t)["operation_id"]
    before = s.get(t)
    with pytest.raises(domain.Fault, match="step"):
        step(s, t, oid, "health", True)
    assert s.get(t) == before
    step(s, t, oid, "start")
    data = cmd(Advance, version=1, step="verify")
    with pytest.raises(domain.Fault, match="changed"):
        s.mutate(
            t, "advance:" + oid, data, lambda w, now: domain.advance(w, oid, data, now)
        )
    s.close()


def test_terminal_operations_cannot_be_restarted_and_cancel_preserves_state():
    s, t, _ = setup()
    sign(s, t)
    oid = enqueue(s, t)["operation_id"]
    before = deepcopy(s.get(t)["environments"])
    step(s, t, oid, "cancel", note="Cancelled after reviewing this rehearsal plan.")
    assert s.get(t)["environments"] == before
    with pytest.raises(domain.Fault, match="terminal"):
        step(s, t, oid, "start")
    s.close()


def test_rollback_restores_earlier_success_without_reusing_new_release_gates():
    s, t, now = setup()
    sign(s, t)
    old = deepcopy(s.get(t)["environments"]["production"])
    oid = enqueue(s, t)["operation_id"]
    healthy(s, t, oid)
    now[0] += domain.HOUR + 1
    w = s.get(t)
    data = cmd(
        Restore,
        target_operation_id=old["operation_id"],
        environment="production",
        generation=2,
        reason="Restore a known successful artifact in this sandbox.",
    )
    result = s.mutate(
        t, "restore", data, lambda w, now: domain.queue(w, data, now, restore=True)
    )
    healthy(s, t, result["operation_id"])
    env = s.get(t)["environments"]["production"]
    assert env["release_id"] == old["release_id"]
    assert env["generation"] == 3
    s.close()


def test_restore_rejects_wrong_environment_and_current_artifact():
    s, t, _ = setup()
    w = s.get(t)
    data = cmd(
        Restore,
        target_operation_id=w["environments"]["staging"]["operation_id"],
        environment="production",
        generation=1,
        reason="This target belongs to another environment.",
    )
    with pytest.raises(domain.Fault, match="this environment"):
        s.mutate(
            t, "restore", data, lambda w, now: domain.queue(w, data, now, restore=True)
        )
    data = cmd(
        Restore,
        target_operation_id=w["environments"]["production"]["operation_id"],
        environment="production",
        generation=1,
        reason="This artifact is already the active snapshot.",
    )
    with pytest.raises(domain.Fault, match="already active"):
        s.mutate(
            t, "restore", data, lambda w, now: domain.queue(w, data, now, restore=True)
        )
    s.close()


def test_health_failure_during_restore_preserves_current_artifact():
    s, t, _ = setup()
    sign(s, t)
    old = s.get(t)["environments"]["production"]["operation_id"]
    healthy(s, t, enqueue(s, t)["operation_id"])
    data = cmd(
        Restore,
        target_operation_id=old,
        environment="production",
        generation=2,
        reason="Rehearse a restore with an unhealthy outcome.",
    )
    oid = s.mutate(
        t, "restore", data, lambda w, now: domain.queue(w, data, now, restore=True)
    )["operation_id"]
    step(s, t, oid, "start")
    step(s, t, oid, "verify")
    before = deepcopy(s.get(t)["environments"])
    step(s, t, oid, "health", False)
    assert s.get(t)["environments"] == before
    s.close()


def test_version_order_is_numeric_not_lexicographic():
    assert version_tuple("1.10.0") > version_tuple("1.9.9")


def test_digest_is_stable_for_object_order_and_changes_with_content():
    m = Manifest(version="1.2.3", source_commit="a" * 40, build_ref="test")
    raw = m.model_dump(mode="json")
    assert digest(raw) == digest(dict(reversed(list(raw.items()))))
    raw["version"] = "1.2.4"
    assert digest(raw) != digest(m)


def test_duplicate_version_cannot_replace_an_existing_manifest():
    s, t, _ = setup()
    r = s.get(t)["releases"][1]
    data = cmd(
        Create, manifest=r["manifest"], notes="Different content is a new candidate."
    )
    with pytest.raises(domain.Fault, match="already exists"):
        s.create_release(t, data)
    s.close()


@pytest.mark.parametrize(
    "version", ["01.2.3", "1.2", "v1.2.3", "1.2.3-beta", "1.2.3+build"]
)
def test_only_three_part_stable_versions_are_accepted(version):
    with pytest.raises(ValidationError):
        Manifest(version=version, source_commit="a" * 40, build_ref="test")


def test_manifest_rejects_duplicate_names_and_secret_values_in_config_keys():
    with pytest.raises(ValidationError):
        Manifest(
            version="1.2.3",
            source_commit="a" * 40,
            build_ref="test",
            config_keys=["TOKEN=value"],
        )
    with pytest.raises(ValidationError):
        Manifest(
            version="1.2.3",
            source_commit="a" * 40,
            build_ref="test",
            dependencies=[
                {"name": "lib", "version": "1.0.0"},
                {"name": "LIB", "version": "1.1.0"},
            ],
        )


def test_incompatible_migration_can_be_rehearsed_in_staging_but_not_signed_for_production():
    s, t, _ = setup()
    data = cmd(
        Create,
        manifest={
            "version": "1.7.0",
            "source_commit": "a" * 40,
            "build_ref": "test",
            "migrations": [{"name": "breaking_change", "backward_compatible": False}],
        },
        notes="A deliberate incompatible migration example.",
    )
    rid = s.create_release(t, data)["release_id"]
    record(s, t, rid)
    healthy(s, t, enqueue(s, t, rid, "staging")["operation_id"])
    with pytest.raises(domain.Fault, match="compatible"):
        sign(s, t, rid)
    assert not next(
        g
        for g in domain.gates(
            s.get(t), domain.release(s.get(t), rid), "production", s.clock()
        )
        if g["key"] == "migration"
    )["ok"]
    s.close()
