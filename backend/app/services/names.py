"""Human-readable names for display only.

This module deliberately never returns a path and never changes the stored file
name. The small, deterministic transformation is cheap enough for list pages.
"""
from __future__ import annotations

import re

_ACRONYMS = {
    "wh40k": "WH40K",
    "stl": "STL",
    "obj": "OBJ",
    "ply": "PLY",
    "glb": "GLB",
    "gltf": "GLTF",
    "3mf": "3MF",
    "fbx": "FBX",
    "dae": "DAE",
    "amf": "AMF",
}
_VERSION_SUFFIX = re.compile(r"(?:[ _.-]+(?:v\d+|version[ _.-]*\d+|final|new)|[ _.-]*\(\d+\))$", re.I)
_URL_RE = re.compile(r"(?:https?://|www\.)\S+", re.I)
_SUPPORT_RE = re.compile(r"pre[ _.-]*support(?:ed|e)?", re.I)
_SEPARATOR_RE = re.compile(r"[_.-]+")
_SPACE_RE = re.compile(r"\s+")


def _normal_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def humanize_name(name: str, tags: list[str] | None = None, ext: str | None = None) -> str:
    """Return a readable title while preserving the original filename elsewhere."""
    value = _URL_RE.sub(" ", name or "")
    if ext and value.lower().endswith(f".{ext.lower()}"):
        value = value[: -(len(ext) + 1)]
    else:
        value = re.sub(r"\.[a-z0-9]{2,5}$", "", value, flags=re.I)

    filename_has_support = bool(_SUPPORT_RE.search(value))
    previous = None
    while value != previous:
        previous = value
        value = _VERSION_SUFFIX.sub("", value).strip()
    value = _SEPARATOR_RE.sub(" ", value)
    value = _SPACE_RE.sub(" ", value).strip()

    tag_tokens = {_normal_token(tag) for tag in (tags or [])}
    support_tokens = {"presupport", "presupported", "presupports", "presupporte"}
    annotation = "pré-supporté" if filename_has_support or tag_tokens & support_tokens or any(
        _SUPPORT_RE.search(tag) for tag in (tags or [])
    ) else None
    value = _SUPPORT_RE.sub(" ", value)
    words: list[str] = []
    for raw in value.split(" "):
        token = _normal_token(raw)
        if not token:
            continue
        words.append(_ACRONYMS.get(token, raw[:1].upper() + raw[1:].lower()))

    result = " ".join(words) or (name or "Fichier")
    if annotation and annotation not in result.lower():
        result = f"{result} ({annotation})"
    return result
