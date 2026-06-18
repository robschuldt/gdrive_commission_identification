from __future__ import annotations
import os

from .models import ImageItem
from .config import Config

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff", ".tif"}


def _is_adult(path_parts, filename, hints):
    hay = " ".join(list(path_parts) + [filename]).lower()
    return any(h in hay for h in hints)


def scan_folder(root: str, config: Config):
    """Walk a local folder and return image items (no hashing yet)."""
    root = os.path.abspath(root)
    items = []
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            ext = os.path.splitext(name)[1].lower()
            if ext not in IMAGE_EXTS:
                continue
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root)
            parent = os.path.basename(dirpath)
            parts = os.path.dirname(rel).split(os.sep) if os.path.dirname(rel) else []
            items.append(ImageItem(
                path=full, rel_path=rel, filename=name, parent_folder=parent,
                is_adult_hint=_is_adult(parts, name, config.adult_hints),
            ))
    return items


def compute_phash(item: ImageItem):
    """Perceptual hash for dedupe + cache key. Returns None if unreadable."""
    try:
        from PIL import Image
        import imagehash
    except ImportError:  # pragma: no cover
        return None
    try:
        with Image.open(item.path) as im:
            return str(imagehash.phash(im.convert("RGB")))
    except Exception:
        return None


def compute_avg_rgb(item: ImageItem):
    """Mean RGB (0-255 ints). Cheap, recompression-robust; used to tell apart
    low-detail images that share a degenerate perceptual hash."""
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover
        return None
    try:
        import numpy as np
        with Image.open(item.path) as im:
            arr = np.asarray(im.convert("RGB").resize((16, 16)), dtype=float).reshape(-1, 3)
        m = arr.mean(axis=0)
        return (int(m[0]), int(m[1]), int(m[2]))
    except Exception:
        return None
