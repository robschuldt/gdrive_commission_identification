from __future__ import annotations
import re
from difflib import SequenceMatcher

from .models import ArtistCandidate
from .config import Config


def _slug(s: str) -> str:
    s = (s or "").strip().lower().lstrip("@")
    s = re.sub(r"[\s_\-]+", "", s)
    s = re.sub(r"[^a-z0-9]", "", s)
    return s


def is_commissioner(name: str, config: Config) -> bool:
    n = _slug(name)
    if not n:
        return True
    for alias in config.commissioner_aliases:
        a = _slug(alias)
        if not a:
            continue
        if n == a or a in n or n in a:
            return True
        if SequenceMatcher(None, n, a).ratio() >= 0.9:
            return True
    return False


def canonicalize(name: str, config: Config) -> str:
    n = _slug(name)
    for canonical, aliases in config.artist_aliases.items():
        if _slug(canonical) == n:
            return canonical
        for al in aliases:
            if _slug(al) == n:
                return canonical
    return (name or "").strip().lstrip("@")


def clean_candidates(cands, config: Config):
    """Drop empties + commissioner self-references; attach canonical names."""
    out = []
    for c in cands:
        if not c.name or not c.name.strip():
            continue
        if is_commissioner(c.name, config):
            continue
        c.canonical = canonicalize(c.name, config)
        out.append(c)
    return out
