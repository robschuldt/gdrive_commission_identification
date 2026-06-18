from __future__ import annotations
import time
from dataclasses import asdict

from .models import ArtistCandidate
from .config import Config
from .scanner import scan_folder, compute_phash, compute_avg_rgb
from .signals import filename_candidates, metadata_candidates
from .reverse import fluffle_search, saucenao_search
from .aggregate import aggregate
from .cache import Cache
from .decisions import Decisions, DECISION_WEIGHT
from .similarity import color_close


def _to_dict(c):
    return asdict(c)


def _from_dict(d):
    return ArtistCandidate(**d)


def identify_all(root, config: Config, cache_path="cache/cache.sqlite",
                 decisions_path=None, live=True, progress=None):
    """Scan + identify every image.

    decisions_path: if given, your stored labels override everything and skip the APIs.
    live: if False, reverse search uses cached results only (no new network calls) —
          used for fast, stall-free interactive review.
    """
    items = scan_folder(root, config)
    cache = Cache(cache_path)
    decisions = Decisions(decisions_path) if decisions_path else None
    rs = config.reverse_search
    results = []
    last_request = 0.0
    total = len(items)
    try:
        for idx, item in enumerate(items, 1):
            item.phash = compute_phash(item)
            item.avg_rgb = compute_avg_rgb(item)
            cands = []
            cands += filename_candidates(item, config)
            cands += metadata_candidates(item, config)

            decided = decisions.get(item.phash) if decisions else None
            use_decision = bool(decided) and color_close(item.avg_rgb, decided.get("avg"))
            if use_decision:
                cands.append(ArtistCandidate(
                    name=decided["artist"], source=decided["source"],
                    weight=DECISION_WEIGHT.get(decided["source"], 0.9),
                    detail=decided.get("note") or "your label"))
            if not use_decision and rs.enabled and (rs.include_adult or not item.is_adult_hint):
                for source, fn, on in (("fluffle", fluffle_search, rs.use_fluffle),
                                       ("saucenao", saucenao_search, rs.use_saucenao)):
                    if not on:
                        continue
                    cached = cache.get(item.phash, source) if item.phash else None
                    if cached is not None:
                        cands += [_from_dict(d) for d in cached]
                        continue
                    if not live:
                        continue  # cache-only: skip uncached lookups
                    wait = rs.min_seconds_between_requests - (time.time() - last_request)
                    if wait > 0:
                        time.sleep(wait)
                    found = fn(item, config)
                    last_request = time.time()
                    real = [c for c in found if c.name]
                    if item.phash:
                        cache.put(item.phash, source, [_to_dict(c) for c in real])
                    cands += found

            results.append(aggregate(item, cands, config))
            if progress:
                progress(idx, total, item)
    finally:
        cache.close()
        if decisions:
            decisions.close()
    return results
