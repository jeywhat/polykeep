"""Automatic tag extraction from file name + parent directory.

Tags come from two sources:
  1. A curated keyword dictionary (configurable via settings / DB).
  2. The leading "tokens" of the file name (first meaningful words).
"""
from __future__ import annotations

import re

from ..config import settings

# Tokens that carry no meaning and should not become auto-tags.
_NOISE = {
    "the", "a", "an", "of", "and", "or", "for", "to", "in", "on", "with",
    "copy", "copie", "final", "v1", "v2", "stl", "lys", "model", "modelle",
    "file", "fichier", "new", "nouveau", "untitled",
}

_TOKEN_SPLIT = re.compile(r"[_\-. \-]+|\b\d+\b")


def normalize(text: str) -> str:
    return text.strip().lower()


def tokenize(text: str) -> list[str]:
    """Split a name/dir into lowercase meaningful tokens."""
    tokens = []
    for raw in _TOKEN_SPLIT.split(text.lower()):
        raw = raw.strip()
        if not raw or raw in _NOISE:
            continue
        tokens.append(raw)
    return tokens


def extract_tags(file_name: str, parent_dir: str, keywords: list[str] | None = None) -> list[str]:
    """Return auto-tags for a file.

    Keyword tags (e.g. 'warhammer', 'articulated') are matched as substrings
    on the whole name+dir. Then a couple of structural tokens are added as
    generic tags so related files can still be grouped even without keywords.
    """
    kw = keywords if keywords is not None else settings.keyword_list()
    haystack = f"{parent_dir} {file_name}".lower()

    tags: list[str] = []
    for k in kw:
        if k and k in haystack:
            # Pretty label (handles compound keywords like "no_support").
            tags.append(k.replace("_", " ").title())

    # A few leading structural tokens make decent free-form tags.
    struct_tokens = tokenize(file_name)[:2]
    for t in struct_tokens:
        label = t.title()
        if label not in tags:
            tags.append(label)

    return tags
