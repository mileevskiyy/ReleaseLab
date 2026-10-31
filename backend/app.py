import hashlib
import hmac
import os
import secrets
import threading
import time
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response, Depends
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ConfigDict
from .models import Create, Evidence, Approval, Queue, Restore, Advance
from .store import Store
from .domain import Fault, release, evidence, approve, queue, advance


class Start(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=2, max_length=30)


def create_app(store=None, origin=None, secure=None):
    owned = store is None
    path = os.getenv("DATABASE_PATH", ":memory:")
    if owned and path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    storage = store or Store(path)
    secret = secrets.token_bytes(32)
    limits = {}
    limit_lock = threading.Lock()
    origins = {
        v
        for v in [
            "http://127.0.0.1:3800",
            "http://127.0.0.1:3801",
            origin or os.getenv("APP_ORIGIN") or os.getenv("RENDER_EXTERNAL_URL"),
        ]
        if v
    }
    secure = os.getenv("COOKIE_SECURE") == "true" if secure is None else secure

    @asynccontextmanager
    async def lifespan(app):
        yield
        if owned:
            storage.close()

    app = FastAPI(
        title="ReleaseLab",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    def csrf(token):
        return hmac.new(secret, token.encode(), hashlib.sha256).hexdigest()

    def cookie(response, token):
        response.set_cookie(
            "releaselab_session",
            token,
            max_age=86400,
            httponly=True,
            samesite="strict",
            secure=secure,
        )

    def check_origin(req):
        if req.headers.get("origin") and req.headers["origin"] not in origins:
            raise Fault(403, "This origin is not allowed.")

    @app.middleware("http")
    async def guard(req, call_next):
        if (
            req.headers.get("content-length", "").isdigit()
            and int(req.headers["content-length"]) > 100000
        ):
            return JSONResponse(
                {"error": "Request body is too large."}, status_code=413
            )
        if req.method in {"POST", "PUT", "PATCH"}:
            body = bytearray()
            async for chunk in req.stream():
                body.extend(chunk)
                if len(body) > 100000:
                    return JSONResponse(
                        {"error": "Request body is too large."}, status_code=413
                    )
            req._body = bytes(body)
        response = await call_next(req)
        response.headers.update(
            {
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY",
                "Referrer-Policy": "no-referrer",
            }
        )
        if req.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(Fault)
    async def error(_req, exc):
        return JSONResponse({"error": exc.message}, status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def invalid(_req, exc):
        return JSONResponse(
            {
                "error": "; ".join(
                    f"{'.'.join(map(str,e['loc'][1:]))}: {e['msg']}"
                    for e in exc.errors()
                )
            },
            status_code=422,
        )

    def auth(req: Request, response: Response):
        token = req.cookies.get("releaselab_session", "")
        storage.get(token)
        cookie(response, token)
        if req.method not in {"GET", "HEAD"}:
            check_origin(req)
            if not hmac.compare_digest(
                req.headers.get("x-csrf-token", "").encode(), csrf(token).encode()
            ):
                raise Fault(403, "Refresh the page before recording changes.")
        return token

    @app.get("/api/health")
    def health():
        return {"ok": True, "app": "ReleaseLab"}

    @app.post("/api/demo")
    def start(body: Start, req: Request, response: Response):
        check_origin(req)
        now = time.time()
        peer = req.client.host if req.client else "unknown"
        with limit_lock:
            for k in list(limits):
                if limits[k]["until"] < now:
                    del limits[k]
            r = limits.setdefault(peer, {"until": now + 900, "count": 0})
            if len(limits) > 1000 or r["count"] >= 20:
                raise Fault(429, "Too many demo sessions. Please return later.")
            r["count"] += 1
        token = storage.create(body.name)
        cookie(response, token)
        return {"csrf": csrf(token)}

    @app.get("/api/session")
    def session(req: Request, response: Response):
        token = req.cookies.get("releaselab_session", "")
        try:
            storage.get(token)
        except Fault:
            return {"authenticated": False}
        cookie(response, token)
        return {"authenticated": True, "csrf": csrf(token)}

    @app.get("/api/workspace")
    def workspace(token=Depends(auth)):
        return storage.snapshot(token)

    @app.post("/api/releases")
    def create(body: Create, token=Depends(auth)):
        return storage.create_release(token, body)

    @app.post("/api/releases/{rid}/evidence")
    def record(rid: str, body: Evidence, token=Depends(auth)):
        return storage.mutate(
            token, "evidence:" + rid, body, lambda w, now: evidence(w, rid, body, now)
        )

    @app.post("/api/releases/{rid}/approve")
    def signoff(rid: str, body: Approval, token=Depends(auth)):
        return storage.mutate(
            token, "approve:" + rid, body, lambda w, now: approve(w, rid, body, now)
        )

    @app.post("/api/operations")
    def deploy(body: Queue, token=Depends(auth)):
        return storage.mutate(token, "queue", body, lambda w, now: queue(w, body, now))

    @app.post("/api/restores")
    def restore(body: Restore, token=Depends(auth)):
        return storage.mutate(
            token, "restore", body, lambda w, now: queue(w, body, now, restore=True)
        )

    @app.post("/api/operations/{oid}/advance")
    def step(oid: str, body: Advance, token=Depends(auth)):
        return storage.mutate(
            token, "advance:" + oid, body, lambda w, now: advance(w, oid, body, now)
        )

    @app.get("/api/releases/{rid}/export")
    def export(rid: str, token=Depends(auth)):
        w = storage.get(token)
        r = release(w, rid)
        return JSONResponse(
            {
                "format": "releaselab-evidence",
                "version": 1,
                "sandbox": True,
                "release": r,
                "operations": [o for o in w["operations"] if o["release_id"] == rid],
                "audit": [e for e in w["events"] if e.get("release_id") == rid],
            },
            headers={
                "Content-Disposition": f'attachment; filename="releaselab-{r["manifest"]["version"]}-evidence.json"'
            },
        )

    @app.api_route(
        "/api/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"]
    )
    def unknown(path):
        raise Fault(404, "API route not found.")

    dist = Path(__file__).resolve().parents[1] / "frontend/dist"
    if dist.exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}")
        def index(path):
            return FileResponse(dist / "index.html")

    return app
