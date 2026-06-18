from __future__ import annotations
import argparse
import sys

from .config import Config
from .pipeline import identify_all
from .organize import write_report, apply_plan


def _progress(i, n, item):
    print(f"  [{i}/{n}] {item.rel_path}", file=sys.stderr)


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="commission-id",
        description="Identify commission artists and group artwork by creator (local folder).")
    p.add_argument("folder", help="Path to a local folder of images (e.g. a downloaded Drive folder).")
    p.add_argument("-c", "--config", default="config.yaml", help="Path to config.yaml")
    p.add_argument("--reports", default="reports", help="Where to write the dry-run report.")
    p.add_argument("--cache", default="cache/cache.sqlite", help="SQLite cache path.")
    p.add_argument("--decisions", default="decisions.sqlite",
                   help="Store of your artist labels (from the review tool).")
    p.add_argument("--no-reverse", action="store_true",
                   help="Disable reverse image search (filename + metadata only).")
    p.add_argument("--include-adult", action="store_true",
                   help="Also reverse-search files flagged adult.")
    p.add_argument("--apply", action="store_true",
                   help="Place files into --dest (default is a dry-run report only).")
    p.add_argument("--dest", default="organized", help="Destination root for --apply.")
    p.add_argument("--move", action="store_true", help="With --apply, move instead of copy.")
    p.add_argument("--include-review", action="store_true",
                   help="With --apply, also place 'review' items.")
    args = p.parse_args(argv)

    cfg = Config.load(args.config)
    if args.no_reverse:
        cfg.reverse_search.enabled = False
    if args.include_adult:
        cfg.reverse_search.include_adult = True

    print(f"Scanning {args.folder} ...", file=sys.stderr)
    idents = identify_all(args.folder, cfg, cache_path=args.cache,
                          decisions_path=args.decisions, progress=_progress)

    summary = write_report(idents, args.reports)
    print("\n=== Summary ===")
    print(f"Total images: {summary['total']}")
    print(f"By status:    {summary['by_status']}")
    print(f"By bucket:    {summary['by_bucket']}")
    print(f"Report (CSV): {summary['csv']}")
    print(f"Report (JSON): {summary['json']}")

    if args.apply:
        mode = "move" if args.move else "copy"
        res = apply_plan(idents, args.dest, mode=mode, include_review=args.include_review)
        print(f"\nPlaced {res['files_placed']} files into '{args.dest}' ({mode}).")
        print(f"Undo manifest: {res['manifest']}")
    else:
        print("\n(Dry run — no files moved. Review the CSV, then re-run with --apply.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
