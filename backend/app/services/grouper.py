"""Name-based grouping.

Detects files that probably belong together by comparing normalised name
tokens. Two strategies:

  1. **Common prefix** — files sharing a long leading token group
     ("SpaceMarine_Helmet", "SpaceMarine_Bolter" => group "SpaceMarine").
  2. **Pairwise similarity** — difflib ratio above a threshold, for files
     whose names are close but don't share a clean prefix.
"""
from __future__ import annotations

import difflib
from collections import defaultdict

from ..config import settings
from .tagger import tokenize


def _first_token(name: str) -> str | None:
    toks = tokenize(name)
    return toks[0] if toks else None


def group_by_prefix(names: dict[int, str]) -> list[list[int]]:
    """Group file-ids whose first token is identical and "long enough".

    ``names`` maps id -> file name. Returns clusters of >= 2 ids.
    """
    by_token: dict[str, list[int]] = defaultdict(list)
    for fid, name in names.items():
        tok = _first_token(name)
        if tok and len(tok) >= 4:
            by_token[tok].append(fid)
    return [ids for ids in by_token.values() if len(ids) >= 2]


def group_by_similarity(names: dict[int, str], threshold: float | None = None) -> list[list[int]]:
    """Cluster file-ids by pairwise difflib similarity."""
    thr = threshold if threshold is not None else settings.similarity_threshold
    ids = list(names.keys())
    # Union-find over ids.
    parent: dict[int, int] = {i: i for i in ids}

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            a, b = ids[i], ids[j]
            ratio = difflib.SequenceMatcher(None, names[a].lower(), names[b].lower()).ratio()
            if ratio >= thr:
                union(a, b)

    clusters: dict[int, list[int]] = defaultdict(list)
    for i in ids:
        clusters[find(i)].append(i)
    return [c for c in clusters.values() if len(c) >= 2]


def suggested_group_name(file_names: list[str]) -> str:
    """Pick a clean label for a proposed group folder.

    Uses the longest common prefix of the (tokenised) names, falling back to
    the first file's leading token.
    """
    token_lists = [tokenize(n) for n in file_names]
    if not token_lists or not token_lists[0]:
        return "Groupe"
    # Longest common token prefix.
    common: list[str] = []
    for k in range(min(len(t) for t in token_lists)):
        token = token_lists[0][k]
        if all(len(t) > k and t[k] == token for t in token_lists):
            common.append(token)
        else:
            break
    if common:
        return "_".join(common).title()
    return (token_lists[0][0] or "Groupe").title()
