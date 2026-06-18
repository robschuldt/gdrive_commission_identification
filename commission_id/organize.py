from __future__ import annotations
import csv
import json
import os
import re
import shutil
from collections import defaultdict

_SAFE_RE = re.compile(r"[^A-Za-z0-9 _.\-]+")


def _safe_folder(name: str) -> str:
    name = _SAFE_RE.sub("", name or "").strip()
    return name or "unknown"


def write_report(idents, out_dir: str):
    os.makedirs(out_dir, exist_ok=True)
    rows = []
    by_bucket = defaultdict(int)
    status_counts = defaultdict(int)
    for it in idents:
        if it.artist and it.status == "confident":
            bucket = _safe_folder(it.artist)
        elif it.status == "review":
            bucket = "_review"
        else:
            bucket = "_unknown"
        by_bucket[bucket] += 1
        status_counts[it.status] += 1
        rows.append({
            "file": it.item.rel_path,
            "proposed_artist": it.artist or "",
            "confidence": it.confidence,
            "status": it.status,
            "evidence": " | ".join(
                f"{c.source}:{c.canonical or c.name}({c.weight:.2f})" for c in it.candidates),
            "notes": "; ".join(it.notes),
        })

    fields = ["file", "proposed_artist", "confidence", "status", "evidence", "notes"]
    csv_path = os.path.join(out_dir, "identifications.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    json_path = os.path.join(out_dir, "identifications.json")
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(rows, fh, indent=2)

    return {"total": len(idents), "by_status": dict(status_counts),
            "by_bucket": dict(by_bucket), "csv": csv_path, "json": json_path}


def apply_plan(idents, dest_root: str, mode: str = "copy", include_review: bool = False):
    """Copy (default) or move files into dest_root/<artist>/. Confident always;
    review only if include_review; everything else into _unknown. Writes an undo manifest."""
    os.makedirs(dest_root, exist_ok=True)
    manifest = []
    placed = 0
    for it in idents:
        if it.status == "confident" and it.artist:
            folder = _safe_folder(it.artist)
        elif it.status == "review":
            if not include_review:
                continue
            folder = "_review-" + _safe_folder(it.artist or "unknown")
        else:
            folder = "_unknown"
        target_dir = os.path.join(dest_root, folder)
        os.makedirs(target_dir, exist_ok=True)
        target = os.path.join(target_dir, it.item.filename)
        base, ext = os.path.splitext(target)
        n = 1
        while os.path.exists(target):
            target = f"{base}_{n}{ext}"
            n += 1
        if mode == "move":
            shutil.move(it.item.path, target)
        else:
            shutil.copy2(it.item.path, target)
        manifest.append({"from": it.item.path, "to": target, "mode": mode})
        placed += 1
    manifest_path = os.path.join(dest_root, "_apply_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
    return {"files_placed": placed, "manifest": manifest_path}
