import hashlib
import json
import secrets
import sqlite3
import threading
import time
from copy import deepcopy
from .models import Candidate, digest
from .seed import seed, candidate
from .domain import Fault, require, view


class Store:
    def __init__(self, path=":memory:", clock=lambda: int(time.time() * 1000)):
        self.clock = clock
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS workspaces(token TEXT PRIMARY KEY,touched INTEGER NOT NULL,payload TEXT NOT NULL)"
        )

    def hash(self, token):
        return hashlib.sha256(token.encode()).hexdigest()

    def budget(self, payload, key=""):
        size = len(payload.encode())
        require(
            size < 1536 * 1024,
            "This demo workspace is full. Start a fresh session.",
            422,
        )
        total = self.db.execute(
            "SELECT coalesce(sum(length(CAST(payload AS BLOB))),0) FROM workspaces WHERE token<>?",
            (key,),
        ).fetchone()[0]
        require(
            total + size < 48 * 1024 * 1024, "The demo is busy. Please try later.", 503
        )

    def create(self, actor):
        require(
            isinstance(actor, str) and 2 <= len(actor.strip()) <= 30,
            "Choose a display name with 2–30 characters.",
            422,
        )
        with self.lock:
            self.db.execute(
                "DELETE FROM workspaces WHERE touched<?", (self.clock() - 86400000,)
            )
            require(
                self.db.execute("SELECT count(*) FROM workspaces").fetchone()[0] < 100,
                "The demo is busy. Please try later.",
                503,
            )
            token = secrets.token_urlsafe(32)
            payload = json.dumps(seed(actor.strip(), self.clock()))
            self.budget(payload)
            self.db.execute(
                "INSERT INTO workspaces VALUES (?,?,?)",
                (self.hash(token), self.clock(), payload),
            )
            return token

    def get(self, token):
        with self.lock:
            row = self.db.execute(
                "SELECT * FROM workspaces WHERE token=?", (self.hash(token),)
            ).fetchone()
            require(
                row and row["touched"] >= self.clock() - 86400000,
                "Your demo expired. Open a fresh workspace.",
                401,
            )
            self.db.execute(
                "UPDATE workspaces SET touched=? WHERE token=?",
                (self.clock(), self.hash(token)),
            )
            return json.loads(row["payload"])

    def snapshot(self, token):
        return view(self.get(token), self.clock())

    def mutate(self, token, action, data, fn):
        payload_data = data.model_dump(mode="json", exclude={"request_id"})
        key = str(data.request_id)
        fingerprint = self.hash(
            json.dumps(
                {"action": action, "payload": payload_data},
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                w = self.get(token)
                previous = next((r for r in w["receipts"] if r["key"] == key), None)
                if previous:
                    require(
                        previous["fingerprint"] == fingerprint,
                        "This request ID belongs to a different operation.",
                    )
                    self.db.execute("COMMIT")
                    return {
                        "workspace": view(w, self.clock()),
                        "replayed": True,
                        **previous["result"],
                    }
                require(
                    len(w["receipts"]) < 2000,
                    "This workspace reached its command limit. Start a fresh demo.",
                    422,
                )
                before = deepcopy(w["environments"])
                event = fn(w, self.clock())
                w["revision"] += 1
                record = {
                    "id": w["revision"],
                    "at": self.clock(),
                    "actor": w["actor"],
                    **event,
                    "before": before,
                    "after": deepcopy(w["environments"]),
                }
                w["events"].append(record)
                w["events"] = w["events"][-200:]
                result = {
                    k: event[k] for k in ["release_id", "operation_id"] if k in event
                }
                w["receipts"].append(
                    {"key": key, "fingerprint": fingerprint, "result": result}
                )
                payload = json.dumps(w)
                self.budget(payload, self.hash(token))
                self.db.execute(
                    "UPDATE workspaces SET payload=? WHERE token=?",
                    (payload, self.hash(token)),
                )
                self.db.execute("COMMIT")
                return {"workspace": view(w, self.clock()), "replayed": False, **result}
            except BaseException:
                self.db.execute("ROLLBACK")
                raise

    def create_release(self, token, data):
        def apply(w, now):
            require(
                len(w["releases"]) < 25,
                "This workspace supports up to 25 candidates.",
                422,
            )
            require(
                not any(
                    r["manifest"]["version"] == data.manifest.version
                    for r in w["releases"]
                ),
                "That version already exists. Create a new version instead of replacing its artifact.",
            )
            r = candidate(data.manifest, data.notes, now)
            w["releases"].append(r)
            return {
                "kind": "release.created",
                "text": f"Created immutable candidate v{data.manifest.version}",
                "release_id": r["id"],
                "detail": r["digest"],
            }

        return self.mutate(token, "release.create", data, apply)

    def close(self):
        self.db.close()
