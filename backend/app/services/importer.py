"""Discovery and safe import of files outside the library."""
from __future__ import annotations

import json
import re
import shutil
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from ..config import settings
from ..models import File, Setting
from .paths import safe_join, storage_root, to_rel
from .scanner import _iter_files

_WATCH_SETTING = "watch_dirs"


def watch_dirs(session: Session) -> list[Path]:
    stored = session.get(Setting, _WATCH_SETTING)
    raw = stored.value if stored else settings.watch_dirs
    if stored:
        try:
            values = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            values = []
    else:
        values = [item.strip() for item in raw.split(",") if item.strip()]
    result = []
    storage = storage_root()
    for value in values:
        path = Path(value).expanduser().resolve()
        if path.is_dir() and path != storage and path not in storage.parents and storage not in path.parents:
            result.append(path)
    return list(dict.fromkeys(result))


def save_watch_dirs(session: Session, values: list[str]) -> list[str]:
    paths = []
    storage = storage_root()
    for value in values:
        path = Path(value.strip()).expanduser().resolve()
        if not path.is_dir():
            raise ValueError(f"Répertoire introuvable : {value}")
        if path == storage or path in storage.parents or storage in path.parents:
            raise ValueError("Un répertoire surveillé ne peut pas être dans /storage")
        paths.append(str(path))
    paths = list(dict.fromkeys(paths))
    setting = session.get(Setting, _WATCH_SETTING)
    if setting is None:
        session.add(Setting(key=_WATCH_SETTING, value=json.dumps(paths)))
    else:
        setting.value = json.dumps(paths)
    session.commit()
    return paths


def _presumed_source(path: Path) -> str | None:
    text = str(path).lower()
    if "makerworld" in text or "maker world" in text:
        return "Makerworld"
    if "thingiverse" in text:
        return "Thingiverse"
    return None


def discover(session: Session) -> list[dict]:
    supported = {ext.lstrip(".") for ext in settings.supported_ext_set}
    existing = {
        (name, file.size)
        for file in session.query(File).all()
        for name in _name_keys(file.name)
    }
    found: list[dict] = []
    seen: set[tuple[str, int]] = set()
    for root in watch_dirs(session):
        for info in _iter_files(root, supported, root):
            keys = {(name, info.size) for name in _name_keys(info.name)}
            if keys & existing or keys & seen:
                continue
            seen.update(keys)
            found.append({
                "source_path": str(info.full_path),
                "name": info.name,
                "size": info.size,
                "source_dir": str(info.full_path.parent),
                "presumed_source": _presumed_source(info.full_path),
            })
    return found


def _clean_name(name: str) -> str:
    path = Path(name)
    stem = re.sub(r"https?[^\s]*", "", path.stem, flags=re.IGNORECASE)
    stem = re.sub(r"(?:[ _-]+v\d+|[ _-]+\(\d+\)|[ _-]+copy)$", "", stem, flags=re.IGNORECASE)
    stem = re.sub(r"[ _-]+$", "", stem)
    return f"{stem or 'modele'}{path.suffix.lower()}"


def _name_keys(name: str) -> set[str]:
    """Match both the downloaded name and the cleaned library name."""
    return {name.casefold(), _clean_name(name).casefold()}


def _allowed_source(source: Path, roots: list[Path]) -> bool:
    resolved = source.resolve()
    return any(root == resolved or root in resolved.parents for root in roots)


def _upload_path(entry: dict) -> Path:
    name = _clean_name(str(entry.get("name") or "modele.stl"))
    if Path(name).suffix.lower() not in settings.supported_ext_set:
        raise ValueError("Format 3D non pris en charge")
    destination = str(entry.get("destination") or "Importés").replace("\\", "/").strip("/")
    if not destination or any(part in {".", ".."} for part in Path(destination).parts):
        raise ValueError("Destination invalide")
    folder = safe_join(destination)
    folder.mkdir(parents=True, exist_ok=True)
    return safe_join(destination, name)


async def write_upload(upload, entry: dict, session: Session) -> Path | None:
    """Write one browser upload atomically and never overwrite library data."""
    destination = _upload_path(entry)
    temporary = destination.parent / f".polykeep-upload-{uuid.uuid4().hex}.tmp"
    try:
        with temporary.open("wb") as target:
            while chunk := await upload.read(1024 * 1024):
                target.write(chunk)
        size = temporary.stat().st_size
        # A browser rename may differ from the original download name, so check
        # the final proposed name as well as the physical destination.
        if destination.exists() or session.query(File).filter(
            File.name == destination.name, File.size == size
        ).first() is not None:
            return None
        temporary.replace(destination)
        return destination
    finally:
        temporary.unlink(missing_ok=True)


def import_files(session: Session, source_paths: list[str], mode: str) -> tuple[int, int]:
    roots = watch_dirs(session)
    existing = {
        (name, file.size)
        for file in session.query(File).all()
        for name in _name_keys(file.name)
    }
    imported = skipped = 0
    for raw_path in source_paths:
        source = Path(raw_path).expanduser()
        if not source.is_file() or not _allowed_source(source, roots):
            skipped += 1
            continue
        size = source.stat().st_size
        keys = {(name, size) for name in _name_keys(source.name)}
        if keys & existing:
            skipped += 1
            continue
        destination_dir = storage_root() / source.parent.name
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination = destination_dir / _clean_name(source.name)
        counter = 2
        while destination.exists():
            destination = destination_dir / f"{destination.stem} ({counter}){destination.suffix}"
            counter += 1
        if mode == "move":
            shutil.move(str(source), str(destination))
        else:
            shutil.copy2(source, destination)
        existing.update(keys)
        imported += 1
    return imported, skipped
