from __future__ import annotations
import os
import re

from .models import ImageItem, ArtistCandidate
from .config import Config

_SEP_RE = re.compile(r"[ _\-.,()\[\]]+")
_DATE_RE = re.compile(r"^\d{4}[-_]?\d{2}[-_]?\d{2}$")
_HEX32_RE = re.compile(r"^[0-9a-f]{32}$")
_ALLDIGITS_RE = re.compile(r"^\d+$")
# Booru / Twitter-dump style: "<digits>.<artist>_<rest>"
_DUMP_RE = re.compile(r"^\d{6,}\.([a-z0-9][\w\-]+?)_", re.IGNORECASE)


def _tokens(stem: str):
    return [t for t in _SEP_RE.split(stem) if t]


def filename_candidates(item: ImageItem, config: Config):
    stem = os.path.splitext(item.filename)[0]
    out = []

    m = _DUMP_RE.match(stem)
    if m:
        out.append(ArtistCandidate(
            name=m.group(1), source="filename", weight=0.55,
            detail=f"dump-style filename '{item.filename}'",
        ))

    stop = set(config.filename_stopwords)
    aliases = {a.lower().replace(" ", "") for a in config.commissioner_aliases}
    toks = _tokens(stem)
    has_commissioner = any(t.lower() in aliases for t in toks)
    for t in toks:
        tl = t.lower()
        if tl in aliases or tl in stop:
            continue
        if _ALLDIGITS_RE.match(tl) or _DATE_RE.match(tl) or _HEX32_RE.match(tl):
            continue
        if len(tl) < 3:
            continue
        weight = 0.45 if has_commissioner else 0.30
        detail = f"token in filename '{item.filename}'"
        if has_commissioner:
            detail += " (paired with your name)"
        out.append(ArtistCandidate(name=t, source="filename", weight=weight, detail=detail))
    return out


_PNG_KEYS = ("Author", "Artist", "Creator", "Copyright", "artist", "author")
_EXIF_ARTIST = 0x013B
_EXIF_COPYRIGHT = 0x8298


def metadata_candidates(item: ImageItem, config: Config):
    out = []
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover
        return out
    try:
        with Image.open(item.path) as im:
            info = getattr(im, "text", None) or {}
            for k in _PNG_KEYS:
                if k in info and str(info[k]).strip():
                    out.append(ArtistCandidate(
                        name=str(info[k]).strip(), source="metadata", weight=0.6,
                        detail=f"PNG metadata '{k}'"))
            exif = im.getexif() if hasattr(im, "getexif") else None
            if exif:
                for tag in (_EXIF_ARTIST, _EXIF_COPYRIGHT):
                    val = exif.get(tag)
                    if val and str(val).strip():
                        out.append(ArtistCandidate(
                            name=str(val).strip(), source="metadata", weight=0.6,
                            detail="EXIF Artist/Copyright"))
    except Exception:
        return out
    return out
