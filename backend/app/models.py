"""SQLAlchemy ORM models."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class File(Base):
    __tablename__ = "files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Path relative to /storage (POSIX style, forward slashes).
    rel_path: Mapped[str] = mapped_column(String, unique=True, index=True)
    name: Mapped[str] = mapped_column(String, index=True)
    parent_dir: Mapped[str] = mapped_column(String, default="", index=True)
    ext: Mapped[str] = mapped_column(String(8), index=True)  # 'stl' | 'lys'
    size: Mapped[int] = mapped_column(Integer, default=0)
    hash: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    # unsorted | sorted | archived | deleted | missing
    status: Mapped[str] = mapped_column(String(16), default="unsorted", index=True)
    thumbnail_path: Mapped[str | None] = mapped_column(String, nullable=True)

    file_created: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    scanned_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )

    tags: Mapped[list["FileTag"]] = relationship(
        back_populates="file", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<File {self.id} {self.rel_path}>"


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, index=True)
    # 'auto' | 'manual'
    source: Mapped[str] = mapped_column(String(8), default="auto")

    files: Mapped[list["FileTag"]] = relationship(
        back_populates="tag", cascade="all, delete-orphan"
    )


class FileTag(Base):
    __tablename__ = "file_tags"

    file_id: Mapped[int] = mapped_column(ForeignKey("files.id", ondelete="CASCADE"), primary_key=True)
    tag_id: Mapped[int] = mapped_column(ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True)

    file: Mapped[File] = relationship(back_populates="tags")
    tag: Mapped[Tag] = relationship(back_populates="files")


class Suggestion(Base):
    """A proposed action, never executed until the user applies it."""
    __tablename__ = "suggestions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # 'group' | 'duplicate' | 'move'
    type: Mapped[str] = mapped_column(String(16), index=True)
    # JSON string: depends on type, see services.sorter
    payload: Mapped[str] = mapped_column(String)
    # pending | applied | rejected
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow)
    applied_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)


class Setting(Base):
    """Key/value store for user-tunable settings (keyword list, thresholds)."""
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(String, default="")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Setting {self.key}={self.value}>"
