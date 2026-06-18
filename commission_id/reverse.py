from __future__ import annotations
import io
import re

from .models import ImageItem, ArtistCandidate
from .config import Config


def _shrink(path: str, target: int = 256):
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover
        return None
    try:
        with Image.open(path) as im:
            im = im.convert("RGB")
            w, h = im.size
            if min(w, h) > target:
                scale = target / min(w, h)
                im = im.resize((max(1, round(w * scale)), max(1, round(h * scale))))
            buf = io.BytesIO()
            im.save(buf, "PNG")
            return buf.getvalue()
    except Exception:
        return None


_FLUFFLE_WEIGHT = {"exact": 0.9, "probable": 0.55, "unlikely": 0.2}


def fluffle_search(item: ImageItem, config: Config, limit: int = 8):
    import requests
    data = _shrink(item.path)
    if data is None:
        return []
    headers = {"User-Agent": config.reverse_search.fluffle_user_agent}
    files = {"File": ("image.png", data, "image/png")}
    try:
        resp = requests.post("https://api.fluffle.xyz/exact-search-by-file",
                             headers=headers, files=files, data={"Limit": str(limit)}, timeout=60)
    except Exception as e:
        return [ArtistCandidate(name="", source="fluffle", weight=0.0, detail=f"request failed: {e}")]
    if resp.status_code == 429:
        return [ArtistCandidate(name="", source="fluffle", weight=0.0, detail="rate limited (429)")]
    if resp.status_code != 200:
        return [ArtistCandidate(name="", source="fluffle", weight=0.0, detail=f"HTTP {resp.status_code}")]
    out = []
    for r in resp.json().get("results", []):
        match = r.get("match", "unlikely")
        platform = (r.get("platform") or "").lower()
        url = r.get("url", "")
        base = _FLUFFLE_WEIGHT.get(match, 0.2)
        # On e621 the author name is the *artist*; elsewhere it's the uploader.
        platform_is_artist_source = "e621" in platform or "e6ai" in platform
        for a in r.get("authors", []) or []:
            name = (a.get("name") or "").strip()
            if not name:
                continue
            w = base if platform_is_artist_source else base * 0.6
            out.append(ArtistCandidate(name=name, source="fluffle", weight=w, platform=platform,
                                       detail=f"{match} match on {platform}: {url}"))
        handle = artist_from_url(url)
        if handle:
            out.append(ArtistCandidate(name=handle, source="fluffle", weight=base * 0.55,
                                       platform=platform,
                                       detail=f"handle parsed from {platform} url: {url}"))
    return out


def saucenao_search(item: ImageItem, config: Config, numres: int = 6):
    key = config.reverse_search.saucenao_api_key
    if not key:
        return []
    import requests
    data = _shrink(item.path, target=512)
    if data is None:
        return []
    params = {"output_type": "2", "numres": str(numres), "db": "999", "api_key": key}
    files = {"file": ("image.png", data, "image/png")}
    try:
        resp = requests.post("https://saucenao.com/search.php", params=params, files=files, timeout=60)
    except Exception as e:
        return [ArtistCandidate(name="", source="saucenao", weight=0.0, detail=f"request failed: {e}")]
    if resp.status_code == 429:
        return [ArtistCandidate(name="", source="saucenao", weight=0.0, detail="rate limited (429)")]
    if resp.status_code != 200:
        return [ArtistCandidate(name="", source="saucenao", weight=0.0, detail=f"HTTP {resp.status_code}")]
    out = []
    for r in resp.json().get("results", []):
        header = r.get("header", {})
        d = r.get("data", {})
        try:
            sim = float(header.get("similarity", "0"))
        except (TypeError, ValueError):
            sim = 0.0
        w = max(0.0, min(0.9, (sim / 100.0) * 0.9))
        name = ""
        for key_name in ("member_name", "author", "creator", "artist", "author_name"):
            v = d.get(key_name)
            if isinstance(v, list) and v:
                v = v[0]
            if v:
                name = str(v).strip()
                break
        urls = d.get("ext_urls", []) or []
        if not name and urls:
            name = artist_from_url(urls[0]) or ""
        if name:
            out.append(ArtistCandidate(name=name, source="saucenao", weight=w,
                                       detail=f"similarity {sim:.0f}%: {urls[0] if urls else ''}"))
    return out


# --- URL -> artist handle extraction ---------------------------------------
_PATTERNS = [
    ("twitter", re.compile(r"(?:twitter|x)\.com/([A-Za-z0-9_]{1,15})(?:/|$)")),
    ("deviantart", re.compile(r"(?:www\.)?deviantart\.com/([A-Za-z0-9\-]+)(?:/|$)")),
    ("furaffinity", re.compile(r"furaffinity\.net/user/([A-Za-z0-9\-_.~]+)")),
    ("weasyl", re.compile(r"weasyl\.com/~([A-Za-z0-9]+)")),
    ("bluesky", re.compile(r"bsky\.app/profile/([A-Za-z0-9_.\-]+)")),
    ("artstation", re.compile(r"artstation\.com/([A-Za-z0-9_\-]+)(?:/|$)")),
    ("newgrounds", re.compile(r"([A-Za-z0-9_\-]+)\.newgrounds\.com")),
]
_BAD_HANDLES = {"i", "home", "status", "intent", "share", "media",
                "submission", "view", "posts", "post", "gallery", "www"}


def artist_from_url(url: str):
    if not url:
        return None
    for _platform, rx in _PATTERNS:
        m = rx.search(url)
        if m:
            handle = m.group(1)
            if handle.lower() in _BAD_HANDLES:
                continue
            return handle
    return None
