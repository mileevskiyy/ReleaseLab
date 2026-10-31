from uuid import uuid4
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.store import Store


def test_http_signoff_promotion_restore_and_export_with_csrf_and_replay():
    s = Store()
    with TestClient(create_app(s, origin="https://release.example", secure=False)) as c:
        assert c.get("/api/workspace").status_code == 401
        assert (
            c.post(
                "/api/demo",
                json={"name": "Operator"},
                headers={"Origin": "https://evil.example"},
            ).status_code
            == 403
        )
        session = c.post("/api/demo", json={"name": "Operator"})
        assert session.status_code == 200
        assert "HttpOnly" in session.headers["set-cookie"]
        h = {"x-csrf-token": session.json()["csrf"]}
        w = c.get("/api/workspace").json()
        r = w["releases"][1]
        old = w["environments"]["production"]["operation_id"]
        body = {
            "request_id": str(uuid4()),
            "version": 1,
            "note": "Reviewed the current sample staging candidate.",
        }
        assert c.post(f'/api/releases/{r["id"]}/approve', json=body).status_code == 403
        assert (
            c.post(
                f'/api/releases/{r["id"]}/approve',
                json=body,
                headers={**h, "Origin": "https://evil.example"},
            ).status_code
            == 403
        )
        signed = c.post(f'/api/releases/{r["id"]}/approve', json=body, headers=h)
        assert signed.status_code == 200
        q = {
            "request_id": str(uuid4()),
            "release_id": r["id"],
            "environment": "production",
            "generation": 1,
        }
        result = c.post("/api/operations", json=q, headers=h)
        assert result.status_code == 200
        oid = result.json()["operation_id"]
        assert c.post("/api/operations", json=q, headers=h).json()["replayed"]
        for version, phase in [(1, "start"), (2, "verify"), (3, "health")]:
            payload = {"request_id": str(uuid4()), "version": version, "step": phase}
            if phase == "health":
                payload["healthy"] = True
            response = c.post(f"/api/operations/{oid}/advance", json=payload, headers=h)
            assert response.status_code == 200
        w = response.json()["workspace"]
        assert w["environments"]["production"]["generation"] == 2
        assert w["environments"]["production"]["release_id"] == r["id"]
        export = c.get(f'/api/releases/{r["id"]}/export')
        assert export.status_code == 200
        assert "evidence.json" in export.headers["content-disposition"]
        assert export.json()["sandbox"]
        assert "receipts" not in export.json()
        restore = c.post(
            "/api/restores",
            json={
                "request_id": str(uuid4()),
                "target_operation_id": old,
                "environment": "production",
                "generation": 2,
                "reason": "Restore the earlier successful sample artifact.",
            },
            headers=h,
        )
        assert restore.status_code == 200
        oid = restore.json()["operation_id"]
        for version, phase in [(1, "start"), (2, "verify"), (3, "health")]:
            payload = {"request_id": str(uuid4()), "version": version, "step": phase}
            if phase == "health":
                payload["healthy"] = True
            response = c.post(f"/api/operations/{oid}/advance", json=payload, headers=h)
            assert response.status_code == 200
        assert (
            response.json()["workspace"]["environments"]["production"]["generation"]
            == 3
        )
        assert (
            c.post(
                "/api/releases",
                json={
                    "request_id": str(uuid4()),
                    "manifest": {"version": "01.2.3"},
                    "notes": "Invalid",
                },
                headers=h,
            ).status_code
            == 422
        )
        assert (
            c.post("/api/demo", content=iter([b"x" * 60000, b"x" * 60000])).status_code
            == 413
        )
    s.close()


def test_foreign_workspace_ids_are_not_accessible_with_another_cookie():
    s = Store()
    app = create_app(s, secure=False)
    with TestClient(app) as first, TestClient(app) as second:
        first.post("/api/demo", json={"name": "First operator"})
        rid = first.get("/api/workspace").json()["releases"][1]["id"]
        second.post("/api/demo", json={"name": "Second operator"})
        assert second.get(f"/api/releases/{rid}/export").status_code == 404
    s.close()


def test_manual_evidence_requires_current_release_version_and_forbids_actor_injection():
    s = Store()
    with TestClient(create_app(s, secure=False)) as c:
        session = c.post("/api/demo", json={"name": "Operator"}).json()
        h = {"x-csrf-token": session["csrf"]}
        r = c.get("/api/workspace").json()["releases"][2]
        payload = {
            "request_id": str(uuid4()),
            "version": r["version"],
            "unit": "passed",
            "api": "passed",
            "security": "passed",
            "note": "Manually recorded sandbox evidence.",
        }
        result = c.post(f'/api/releases/{r["id"]}/evidence', json=payload, headers=h)
        assert result.status_code == 200
        record = result.json()["workspace"]["releases"][2]["evidence"][-1]
        assert record["actor"] == "Operator"
        assert record["provenance"] == "manual-sandbox"
        assert not record["sample"]
        assert (
            c.post(
                f'/api/releases/{r["id"]}/evidence',
                json={**payload, "request_id": str(uuid4())},
                headers=h,
            ).status_code
            == 409
        )
        assert (
            c.post(
                f'/api/releases/{r["id"]}/evidence',
                json={**payload, "request_id": str(uuid4()), "actor": "Someone else"},
                headers=h,
            ).status_code
            == 422
        )
    s.close()
