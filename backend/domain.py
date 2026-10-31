from uuid import uuid4
from .models import digest, version_tuple

HOUR = 3600000
ACTIVE = {"queued", "running", "verifying"}
TERMINAL = {"succeeded", "failed", "cancelled"}


class Fault(Exception):
    def __init__(self, status, message):
        self.status = status
        self.message = message


def require(condition, message, status=409):
    if not condition:
        raise Fault(status, message)


def release(w, rid):
    r = next((r for r in w["releases"] if r["id"] == rid), None)
    require(r is not None, "Release not found.", 404)
    return r


def operation(w, oid):
    op = next((o for o in w["operations"] if o["id"] == oid), None)
    require(op is not None, "Operation not found.", 404)
    return op


def latest_evidence(r):
    return r["evidence"][-1] if r["evidence"] else None


def latest_approval(r):
    return r["approvals"][-1] if r["approvals"] else None


def signoff_ready(w, r, now):
    e = latest_evidence(r)
    return bool(
        e
        and e["digest"] == r["digest"]
        and all(v == "passed" for v in e["checks"].values())
        and now - e["at"] <= HOUR
        and w["environments"]["staging"]["release_id"] == r["id"]
        and all(m["backward_compatible"] for m in r["manifest"]["migrations"])
        and digest(r["manifest"]) == r["digest"]
    )


def gates(w, r, env, now):
    e = latest_evidence(r)
    approval = latest_approval(r)
    current_id = w["environments"][env]["release_id"]
    current = release(w, current_id) if current_id else None
    rows = [
        {
            "key": "integrity",
            "label": "Manifest identity",
            "ok": digest(r["manifest"]) == r["digest"],
            "detail": "SHA-256 of canonical manifest content.",
        },
        {
            "key": "evidence",
            "label": "Recorded checks",
            "ok": bool(
                e
                and e["digest"] == r["digest"]
                and all(v == "passed" for v in e["checks"].values())
            ),
            "detail": "Latest recorded unit, API and security results must pass for this digest.",
        },
        {
            "key": "fresh",
            "label": "Evidence freshness",
            "ok": bool(e and now - e["at"] <= HOUR),
            "detail": "Evidence is usable for 60 minutes.",
        },
        {
            "key": "version",
            "label": "Forward version",
            "ok": current is None
            or version_tuple(r["manifest"]["version"])
            > version_tuple(current["manifest"]["version"]),
            "detail": "Normal promotion must advance the active three-part version.",
        },
    ]
    if env == "production":
        rows.extend(
            [
                {
                    "key": "staging",
                    "label": "Verified in staging",
                    "ok": w["environments"]["staging"]["release_id"] == r["id"],
                    "detail": "The exact candidate must currently be active in staging.",
                },
                {
                    "key": "migration",
                    "label": "Migration compatibility",
                    "ok": all(
                        m["backward_compatible"] for m in r["manifest"]["migrations"]
                    ),
                    "detail": "All declared migrations must assert backward compatibility.",
                },
                {
                    "key": "approval",
                    "label": "Current sign-off",
                    "ok": bool(
                        e
                        and approval
                        and approval["evidence_id"] == e["id"]
                        and approval["digest"] == r["digest"]
                        and approval["expires_at"] >= now
                    ),
                    "detail": "An unexpired sign-off must refer to the latest evidence.",
                },
            ]
        )
    return rows


def promotion_ready(w, r, env, now):
    return all(g["ok"] for g in gates(w, r, env, now))


def evidence(w, rid, data, now):
    r = release(w, rid)
    require(
        r["version"] == data.version,
        "The release changed. Reload before recording evidence.",
    )
    require(len(r["evidence"]) < 20, "This candidate reached its evidence limit.", 422)
    item = {
        "id": str(uuid4()),
        "digest": r["digest"],
        "checks": {"unit": data.unit, "api": data.api, "security": data.security},
        "note": data.note,
        "at": now,
        "actor": w["actor"],
        "provenance": "manual-sandbox",
        "sample": False,
    }
    r["evidence"].append(item)
    r["version"] += 1
    return {
        "kind": "evidence.recorded",
        "text": f"Recorded build evidence for v{r['manifest']['version']}",
        "release_id": rid,
        "detail": data.note,
    }


def approve(w, rid, data, now):
    r = release(w, rid)
    require(
        r["version"] == data.version, "The release changed. Reload before sign-off."
    )
    require(
        signoff_ready(w, r, now),
        "Sign-off needs fresh passing evidence, a matching staging candidate and compatible migration declarations.",
    )
    previous = latest_approval(r)
    e = latest_evidence(r)
    require(
        not (
            previous
            and previous["evidence_id"] == e["id"]
            and previous["expires_at"] >= now
        ),
        "This evidence already has a current sign-off.",
    )
    require(len(r["approvals"]) < 10, "This candidate reached its sign-off limit.", 422)
    r["approvals"].append(
        {
            "id": str(uuid4()),
            "digest": r["digest"],
            "evidence_id": e["id"],
            "at": now,
            "expires_at": now + HOUR,
            "actor": w["actor"],
            "note": data.note,
            "sample": False,
        }
    )
    r["version"] += 1
    return {
        "kind": "release.approved",
        "text": f"Signed off v{r['manifest']['version']} for production rehearsal",
        "release_id": rid,
        "detail": data.note,
    }


def queue(w, data, now, restore=False):
    env = w["environments"][data.environment]
    require(
        env["generation"] == data.generation,
        "The environment changed. Reload its current generation.",
    )
    require(
        not any(
            o["environment"] == data.environment and o["state"] in ACTIVE
            for o in w["operations"]
        ),
        "This environment already has an active rehearsal.",
    )
    require(
        len(w["operations"]) < 120, "This workspace reached its operation limit.", 422
    )
    if restore:
        target = operation(w, data.target_operation_id)
        require(
            target["environment"] == data.environment
            and target["state"] == "succeeded",
            "Choose a successful deployment from this environment.",
        )
        require(
            target["release_id"] != env["release_id"],
            "That artifact is already active.",
        )
        require(
            env["operation_id"] is not None
            and target["sequence"] < operation(w, env["operation_id"])["sequence"],
            "Choose an earlier successful deployment.",
        )
        rid = target["release_id"]
        reason = data.reason
        target_id = target["id"]
        e = None
        approval = None
    else:
        rid = data.release_id
        r = release(w, rid)
        failed = [g["label"] for g in gates(w, r, data.environment, now) if not g["ok"]]
        require(not failed, "Promotion blocked: " + ", ".join(failed) + ".")
        reason = ""
        target_id = None
        e = latest_evidence(r)
        approval = latest_approval(r) if data.environment == "production" else None
    r = release(w, rid)
    op = {
        "id": str(uuid4()),
        "sequence": w["next_operation"],
        "kind": "restore" if restore else "deploy",
        "environment": data.environment,
        "release_id": rid,
        "digest": r["digest"],
        "state": "queued",
        "version": 1,
        "expected_generation": env["generation"],
        "evidence_id": e["id"] if e else None,
        "approval_id": approval["id"] if approval else None,
        "restore_target": target_id,
        "reason": reason,
        "failure": None,
        "created_at": now,
        "updated_at": now,
        "finished_at": None,
        "actor": w["actor"],
        "sample": False,
        "steps": [
            {
                "state": "queued",
                "at": now,
                "note": reason or "Sandbox operation queued.",
            }
        ],
    }
    w["next_operation"] += 1
    w["operations"].append(op)
    return {
        "kind": "operation.queued",
        "text": f"Queued {'restore' if restore else 'deployment'} of v{r['manifest']['version']} to {data.environment}",
        "release_id": rid,
        "operation_id": op["id"],
        "detail": reason,
    }


def recheck(w, op, now):
    env = w["environments"][op["environment"]]
    r = release(w, op["release_id"])
    if env["generation"] != op["expected_generation"]:
        return "Environment generation changed."
    if digest(r["manifest"]) != op["digest"] or r["digest"] != op["digest"]:
        return "Manifest identity changed."
    if op["kind"] == "restore":
        target = operation(w, op["restore_target"])
        if target["state"] != "succeeded" or target["digest"] != op["digest"]:
            return "Restore target is no longer a valid successful snapshot."
        return None
    e = latest_evidence(r)
    ap = latest_approval(r)
    if not e or e["id"] != op["evidence_id"]:
        return "Build evidence changed after this operation was queued."
    if op["environment"] == "production" and (not ap or ap["id"] != op["approval_id"]):
        return "Sign-off changed after this operation was queued."
    failed = [g["label"] for g in gates(w, r, op["environment"], now) if not g["ok"]]
    return ("Gate no longer satisfied: " + ", ".join(failed) + ".") if failed else None


def advance(w, oid, data, now):
    op = operation(w, oid)
    require(
        op["version"] == data.version,
        "This operation changed. Reload before advancing it.",
    )
    require(
        op["state"] in ACTIVE,
        "This rehearsal is already terminal. Start a new operation.",
    )
    if data.step == "cancel":
        state = "cancelled"
        note = data.note
        op["reason"] = data.note
    else:
        expected = {"start": "queued", "verify": "running", "health": "verifying"}
        require(
            op["state"] == expected[data.step],
            "This step is not valid for the current operation state.",
        )
        failure = recheck(w, op, now)
        if failure:
            state = "failed"
            note = failure
            op["failure"] = failure
        elif data.step == "start":
            state = "running"
            note = "Sandbox adapter started; no external process is deployed."
        elif data.step == "verify":
            state = "verifying"
            note = "Waiting for a manually reported sandbox health signal."
        elif not data.healthy:
            state = "failed"
            note = data.note or "Sandbox health signal reported failure."
            op["failure"] = note
        else:
            state = "succeeded"
            note = data.note or "Sandbox health signal reported healthy."
            env = w["environments"][op["environment"]]
            env["release_id"] = op["release_id"]
            env["digest"] = op["digest"]
            env["generation"] += 1
            env["operation_id"] = op["id"]
            env["updated_at"] = now
    op["state"] = state
    op["version"] += 1
    op["updated_at"] = now
    op["steps"].append({"state": state, "at": now, "note": note})
    if state in TERMINAL:
        op["finished_at"] = now
    return {
        "kind": "operation." + state,
        "text": f"Rehearsal #{op['sequence']:03} {state} in {op['environment']}",
        "release_id": op["release_id"],
        "operation_id": op["id"],
        "detail": note,
    }


def view(w, now):
    releases = []
    for r in w["releases"]:
        releases.append(
            {
                **r,
                "gates": {
                    env: gates(w, r, env, now) for env in ["staging", "production"]
                },
                "can_approve": signoff_ready(w, r, now),
            }
        )
    return {
        **{k: v for k, v in w.items() if k != "receipts"},
        "releases": releases,
        "now": now,
    }
