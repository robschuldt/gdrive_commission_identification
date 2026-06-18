from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ImageItem:
    path: str                 # absolute path on disk
    rel_path: str             # path relative to the scanned root
    filename: str
    parent_folder: str
    phash: Optional[str] = None
    avg_rgb: Optional[tuple] = None   # mean colour, guards phash collisions on flat images
    is_adult_hint: bool = False   # inferred from folder/file naming


@dataclass
class ArtistCandidate:
    name: str                 # raw candidate (pre-canonicalization)
    source: str               # "filename" | "metadata" | "fluffle" | "saucenao"
    weight: float             # 0..1 contribution
    detail: str = ""          # human-readable evidence (e.g. a URL)
    platform: str = ""        # e621, furaffinity, twitter, ...
    canonical: str = ""       # filled in by the normalize step


@dataclass
class Identification:
    item: ImageItem
    candidates: list = field(default_factory=list)   # list[ArtistCandidate] after cleaning
    artist: Optional[str] = None      # chosen canonical artist, or None
    confidence: float = 0.0           # 0..1
    status: str = "unknown"           # "confident" | "review" | "unknown"
    notes: list = field(default_factory=list)
