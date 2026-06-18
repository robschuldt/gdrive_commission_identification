from __future__ import annotations
import os
from dataclasses import dataclass, field
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

DEFAULT_COMMISSIONER_ALIASES = ["jaiy", "jaiydawoof", "jaiy deer", "jaiydeer"]

DEFAULT_STOPWORDS = [
    "img", "image", "untitled", "artwork", "final", "ref", "sheet", "reference",
    "comm", "commission", "commissioned", "ych", "adopt", "sketch", "sketches",
    "doodle", "clean", "questionable", "adult", "nsfw", "sfw", "wip", "flat",
    "flats", "color", "colour", "colored", "coloured", "lineart", "lines", "page",
    "copy", "edit", "screenshot", "photo", "pic",
]

DEFAULT_ADULT_HINTS = ["adult", "nsfw", "questionable", "saucy", "explicit"]


@dataclass
class ReverseSearchConfig:
    enabled: bool = True
    use_fluffle: bool = True
    use_saucenao: bool = False
    saucenao_api_key: str = ""
    include_adult: bool = False
    fluffle_user_agent: str = "gdrive-commission-id/0.1 (by user on GitHub)"
    min_seconds_between_requests: float = 2.0


@dataclass
class Config:
    commissioner_aliases: list = field(default_factory=lambda: list(DEFAULT_COMMISSIONER_ALIASES))
    artist_aliases: dict = field(default_factory=dict)
    filename_stopwords: list = field(default_factory=lambda: list(DEFAULT_STOPWORDS))
    adult_hints: list = field(default_factory=lambda: list(DEFAULT_ADULT_HINTS))
    reverse_search: ReverseSearchConfig = field(default_factory=ReverseSearchConfig)

    @staticmethod
    def load(path):
        cfg = Config()
        if not path or not os.path.exists(path):
            return cfg
        if yaml is None:  # pragma: no cover
            raise RuntimeError("PyYAML is required to read a config file: pip install pyyaml")
        with open(path, "r", encoding="utf-8") as fh:
            data: dict[str, Any] = yaml.safe_load(fh) or {}
        if data.get("commissioner_aliases"):
            cfg.commissioner_aliases = [str(x) for x in data["commissioner_aliases"]]
        if data.get("artist_aliases"):
            cfg.artist_aliases = {str(k): [str(v) for v in vals]
                                  for k, vals in data["artist_aliases"].items()}
        if data.get("filename_stopwords"):
            cfg.filename_stopwords = [str(x).lower() for x in data["filename_stopwords"]]
        if data.get("adult_hints"):
            cfg.adult_hints = [str(x).lower() for x in data["adult_hints"]]
        rs = data.get("reverse_search", {}) or {}
        cfg.reverse_search = ReverseSearchConfig(
            enabled=bool(rs.get("enabled", True)),
            use_fluffle=bool(rs.get("use_fluffle", True)),
            use_saucenao=bool(rs.get("use_saucenao", False)),
            saucenao_api_key=str(rs.get("saucenao_api_key", "")),
            include_adult=bool(rs.get("include_adult", False)),
            fluffle_user_agent=str(rs.get("fluffle_user_agent",
                                          ReverseSearchConfig.fluffle_user_agent)),
            min_seconds_between_requests=float(rs.get("min_seconds_between_requests", 2.0)),
        )
        return cfg
