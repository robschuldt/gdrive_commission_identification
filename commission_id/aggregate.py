from __future__ import annotations
from collections import defaultdict

from .models import ImageItem, Identification
from .config import Config
from .normalize import clean_candidates

CONFIDENT = 0.75
REVIEW = 0.40


def aggregate(item: ImageItem, raw_candidates, config: Config) -> Identification:
    ident = Identification(item=item)
    cands = clean_candidates(raw_candidates, config)
    ident.candidates = cands
    if not cands:
        ident.status = "unknown"
        ident.notes.append("no artist signal found")
        return ident

    by_artist = defaultdict(list)
    for c in cands:
        by_artist[c.canonical].append(c)

    scored = []
    for artist, group in by_artist.items():
        sources = {g.source for g in group}
        best = max(g.weight for g in group)
        extra = sum(sorted((g.weight for g in group), reverse=True)[1:]) * 0.3
        multi_source_bonus = 0.15 * (len(sources) - 1)
        score = min(0.99, best + extra + multi_source_bonus)
        scored.append((artist, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    top_artist, top_score = scored[0]
    ident.artist = top_artist
    ident.confidence = round(top_score, 3)

    if len(scored) > 1 and (top_score - scored[1][1]) < 0.15:
        ident.status = "review"
        ident.notes.append(
            f"close call: {top_artist} ({top_score:.2f}) vs {scored[1][0]} ({scored[1][1]:.2f})")
    elif top_score >= CONFIDENT:
        ident.status = "confident"
    elif top_score >= REVIEW:
        ident.status = "review"
    else:
        ident.status = "unknown"
    return ident
