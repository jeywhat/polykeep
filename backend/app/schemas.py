"""Pydantic v2 schemas (API I/O)."""
from __future__ import annotations

import datetime as dt
import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TagOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    source: str


class FileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    rel_path: str
    name: str
    parent_dir: str
    ext: str
    size: int
    hash: str | None = None
    status: str
    thumbnail_path: str | None = None
    file_created: dt.datetime | None = None
    scanned_at: dt.datetime
    tags: list[str] = Field(default_factory=list)
    preview_url: str | None = None

    @field_validator("tags", mode="before")
    @classmethod
    def _coerce_tags(cls, value):
        # Accept ORM relationship objects (FileTag / Tag) and extract names.
        if value is None:
            return []
        names = []
        for item in value:
            if isinstance(item, str):
                names.append(item)
            elif hasattr(item, "tag") and item.tag is not None:
                names.append(item.tag.name)
            elif hasattr(item, "name"):
                names.append(item.name)
        return names


class FileListOut(BaseModel):
    items: list[FileOut]
    total: int
    page: int
    page_size: int


class ScanResultOut(BaseModel):
    scanned: int
    added: int
    updated: int
    missing: int
    duration_ms: int


class SuggestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    type: str
    payload: dict[str, Any]
    status: str
    created_at: dt.datetime
    applied_at: dt.datetime | None = None

    @classmethod
    def from_model(cls, s) -> "SuggestionOut":
        return cls(
            id=s.id,
            type=s.type,
            payload=json.loads(s.payload) if s.payload else {},
            status=s.status,
            created_at=s.created_at,
            applied_at=s.applied_at,
        )


class MoveRequest(BaseModel):
    target_dir: str  # relative to /storage, e.g. "Trié/Guerre"


class TagRequest(BaseModel):
    tag: str
    source: str = "manual"


class HealthOut(BaseModel):
    status: str
    storage_dir: str
    file_count: int
