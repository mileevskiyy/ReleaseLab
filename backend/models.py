import re
import hashlib
import json
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator

VERSION = r"(0|[1-9]\d{0,5})\.(0|[1-9]\d{0,5})\.(0|[1-9]\d{0,5})"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Dependency(Strict):
    name: str = Field(min_length=1, max_length=50, pattern=r"^[a-zA-Z0-9@/_.-]+$")
    version: str = Field(pattern="^" + VERSION + "$", max_length=20)


class Migration(Strict):
    name: str = Field(min_length=1, max_length=60, pattern=r"^[a-zA-Z0-9_.-]+$")
    backward_compatible: bool


class Manifest(Strict):
    service: Literal["atlas-api"] = "atlas-api"
    version: str = Field(pattern="^" + VERSION + "$", max_length=20)
    source_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    build_ref: str = Field(min_length=1, max_length=80)
    dependencies: list[Dependency] = Field(max_length=15, default_factory=list)
    migrations: list[Migration] = Field(max_length=10, default_factory=list)
    config_keys: list[str] = Field(max_length=20, default_factory=list)

    @model_validator(mode="after")
    def unique(self):
        for names in (
            [d.name.casefold() for d in self.dependencies],
            [m.name.casefold() for m in self.migrations],
            self.config_keys,
        ):
            if len(names) != len(set(names)):
                raise ValueError(
                    "Dependency, migration and config-key names must be unique."
                )
        if any(not re.fullmatch(r"[A-Z][A-Z0-9_]{0,49}", k) for k in self.config_keys):
            raise ValueError("Config keys must be uppercase names, without values.")
        return self


class Candidate(Strict):
    manifest: Manifest
    notes: str = Field(min_length=1, max_length=1500)


class Command(Strict):
    request_id: UUID


class Create(Command, Candidate):
    pass


class Evidence(Command):
    version: int = Field(ge=1)
    unit: Literal["passed", "failed"]
    api: Literal["passed", "failed"]
    security: Literal["passed", "failed"]
    note: str = Field(min_length=5, max_length=400)


class Approval(Command):
    version: int = Field(ge=1)
    note: str = Field(min_length=10, max_length=400)


class Queue(Command):
    release_id: str = Field(min_length=1, max_length=50)
    environment: Literal["staging", "production"]
    generation: int = Field(ge=0)


class Restore(Command):
    target_operation_id: str = Field(min_length=1, max_length=50)
    environment: Literal["staging", "production"]
    generation: int = Field(ge=0)
    reason: str = Field(min_length=10, max_length=400)


class Advance(Command):
    version: int = Field(ge=1)
    step: Literal["start", "verify", "health", "cancel"]
    healthy: bool | None = None
    note: str = Field(max_length=400, default="")

    @model_validator(mode="after")
    def signal(self):
        if self.step == "health" and self.healthy is None:
            raise ValueError("Choose a sandbox health outcome.")
        if self.step == "cancel" and len(self.note) < 10:
            raise ValueError("Record a cancellation reason of at least 10 characters.")
        return self


def digest(manifest):
    if isinstance(manifest, Manifest):
        manifest = manifest.model_dump(mode="json")
    return hashlib.sha256(
        json.dumps(
            manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    ).hexdigest()


def version_tuple(version):
    return tuple(map(int, version.split(".")))
