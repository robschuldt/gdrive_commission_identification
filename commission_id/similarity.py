"""Near-duplicate (reliable) and visual-style (suggestive) image similarity."""
from __future__ import annotations
import math


def hamming_hex(a, b):
    """Hamming distance between two hex perceptual hashes (0..64)."""
    if not a or not b or len(a) != len(b):
        return 64
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def is_near_dup(a, b, max_distance=6):
    """True if two images are almost certainly the same artwork."""
    return hamming_hex(a, b) <= max_distance


def _l1(v):
    import numpy as np
    s = float(v.sum())
    return v / s if s > 0 else v


def visual_descriptor(path):
    """A lightweight, dependency-free style fingerprint: linework-orientation
    histogram + coarse colour palette + value layout. Heuristic, NOT a true
    artist classifier — good enough to surface look-alikes for confirmation."""
    import numpy as np
    from PIL import Image
    try:
        with Image.open(path) as im:
            arr = np.asarray(im.convert("RGB").resize((64, 64)), dtype=float) / 255.0
    except Exception:
        return None
    gray = arr.mean(axis=2)
    gx = np.zeros_like(gray)
    gy = np.zeros_like(gray)
    gx[:, 1:] = np.diff(gray, axis=1)
    gy[1:, :] = np.diff(gray, axis=0)
    mag = np.sqrt(gx * gx + gy * gy)
    ori = np.arctan2(gy, gx)
    bins = 16
    idx = (((ori + math.pi) / (2 * math.pi)) * bins).astype(int) % bins
    ori_hist = np.array([mag[idx == b].sum() for b in range(bins)], dtype=float)
    ori_hist = _l1(ori_hist)
    q = np.clip((arr * 4).astype(int), 0, 3)
    color_idx = (q[..., 0] * 16 + q[..., 1] * 4 + q[..., 2]).ravel()
    color_hist = _l1(np.bincount(color_idx, minlength=64).astype(float))
    pooled = _l1(gray.reshape(8, 8, 8, 8).mean(axis=(1, 3)).ravel())
    vec = np.concatenate([ori_hist, color_hist, pooled])
    n = float(np.linalg.norm(vec))
    return (vec / n).tolist() if n > 0 else vec.tolist()


def cosine(a, b):
    import numpy as np
    if a is None or b is None:
        return 0.0
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def near_dup_keys(target_phash, pool, max_distance=6):
    """pool: list of (key, phash). Returns keys that are the same artwork."""
    return [key for key, ph in pool if ph and is_near_dup(target_phash, ph, max_distance)]


def style_neighbors(target_vec, pool, min_cosine=0.92):
    """pool: list of (key, vec). Returns [(key, similarity)] sorted desc."""
    out = [(key, cosine(target_vec, vec)) for key, vec in pool if vec is not None]
    out = [(k, s) for k, s in out if s >= min_cosine]
    out.sort(key=lambda x: x[1], reverse=True)
    return out


def color_dist(c1, c2):
    """Euclidean distance between two (r,g,b) means; large = different palette."""
    if not c1 or not c2:
        return 0.0
    return sum((a - b) ** 2 for a, b in zip(c1, c2)) ** 0.5


def color_close(c1, c2, max_dist=30.0):
    """True if mean colours match (or either is unknown, so we can't tell)."""
    if not c1 or not c2:
        return True
    return color_dist(c1, c2) <= max_dist
