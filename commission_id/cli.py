from __future__ import annotations
import argparse
import sys

from .config import Config
from .pipeline import identify_all
from .organize import write_report, apply_plan
from . import drive


def _progress(i, n, item):
    print(f"  [{i}/{n}] {item.rel_path}", file=sys.stderr)


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="commission-id",
        description="Identify commission artists and group artwork by creator. "
                    "Accepts a local folder OR a Google Drive folder link/ID.")
    p.add_argument("folder",
                   help="A local folder of images, or a Google Drive folder URL/ID.")
    p.add_argument("-c", "--config", default="config.yaml", help="Path to config.yaml")
    p.add_argument("--reports", default="reports", help="Where to write the dry-run report.")
    p.add_argument("--cache", default="cache/cache.sqlite", help="SQLite cache path.")
    p.add_argument("--decisions", default="decisions.sqlite",
                   help="Store of your artist labels (from the review tool).")
    p.add_argument("--no-reverse", action="store_true",
                   help="Disable reverse image search (filename + metadata only).")
    p.add_argument("--skip-adult", action="store_true",
                   help="Skip reverse search for files/folders flagged adult "
                        "(adult files are included by default).")
    p.add_argument("--apply", action="store_true",
                   help="Actually place/move files (default is a dry-run report only).")
    p.add_argument("--dest", default="organized",
                   help="Destination root for a local sorted copy (with --apply).")
    p.add_argument("--move", action="store_true",
                   help="With --apply on a local copy, move instead of copy.")
    p.add_argument("--include-review", action="store_true",
                   help="With --apply, also place 'review' items.")

    g = p.add_argument_group("Google Drive")
    g.add_argument("--from-drive", action="store_true",
                   help="Treat 'folder' as a Google Drive folder ID even if it isn't a URL.")
    g.add_argument("--work-dir", default="drive_download",
                   help="Where Drive images are downloaded before identifying.")
    g.add_argument("--credentials", default="credentials.json",
                   help="OAuth client-secrets file for the Drive API.")
    g.add_argument("--token", default="token.json",
                   help="Where the Drive OAuth token is cached.")
    g.add_argument("--drive-apply", action="store_true",
                   help="Reorganize the files IN Google Drive into per-artist folders "
                        "(dry-run unless --apply is also given). Writes an undo manifest.")
    g.add_argument("--undo", metavar="MANIFEST",
                   help="Revert an in-Drive reorganization using its undo manifest, then exit.")
    args = p.parse_args(argv)

    # --- Drive undo shortcut: revert and exit ---
    if args.undo:
        service = drive.get_service(args.credentials, args.token, writable=True)
        n = drive.undo_from_manifest(service, args.undo)
        print(f"Reverted {n} file move(s) from {args.undo}.")
        return 0

    cfg = Config.load(args.config)
    if args.no_reverse:
        cfg.reverse_search.enabled = False
    if args.skip_adult:
        cfg.reverse_search.include_adult = False

    is_drive = drive.looks_like_drive(args.folder) or args.from_drive
    service = None
    id_by_rel = {}
    drive_root = None

    if is_drive:
        drive_root = drive.parse_folder_id(args.folder)
        if not drive_root:
            print(f"Could not parse a Drive folder ID from: {args.folder}", file=sys.stderr)
            return 2
        service = drive.get_service(args.credentials, args.token, writable=args.drive_apply)
        print(f"Listing Drive folder {drive_root} ...", file=sys.stderr)
        files = drive.list_images(service, drive_root)
        print(f"Downloading {len(files)} image(s) to {args.work_dir} ...", file=sys.stderr)
        local = drive.download_images(service, files, args.work_dir, progress=_progress)
        id_by_rel = {f["rel_path"]: f["id"] for f in local}
        scan_root = args.work_dir
    else:
        scan_root = args.folder

    print(f"Scanning {scan_root} ...", file=sys.stderr)
    idents = identify_all(scan_root, cfg, cache_path=args.cache,
                          decisions_path=args.decisions, progress=_progress)

    summary = write_report(idents, args.reports)
    print("\n=== Summary ===")
    print(f"Total images: {summary['total']}")
    print(f"By status:    {summary['by_status']}")
    print(f"By bucket:    {summary['by_bucket']}")
    print(f"Report (CSV): {summary['csv']}")
    print(f"Report (JSON): {summary['json']}")

    if is_drive and args.drive_apply:
        res = drive.apply_in_drive(service, idents, id_by_rel, drive_root,
                                   include_review=args.include_review, dry_run=not args.apply)
        if args.apply:
            print(f"\nMoved {res['files_moved']} file(s) in Drive into per-artist folders.")
            print(f"Undo manifest: {res['manifest']}")
            print(f"Undo with:  python -m commission_id.cli x --undo {res['manifest']}")
        else:
            print(f"\n(Drive dry run -- {res['files_moved']} file(s) would move. "
                  f"Plan written to {res['manifest']}. Re-run with --apply to execute.)")
    elif args.apply:
        mode = "move" if args.move else "copy"
        res = apply_plan(idents, args.dest, mode=mode, include_review=args.include_review)
        print(f"\nPlaced {res['files_placed']} files into '{args.dest}' ({mode}).")
        print(f"Undo manifest: {res['manifest']}")
    else:
        print("\n(Dry run -- no files moved. Review the CSV, then re-run with --apply.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
