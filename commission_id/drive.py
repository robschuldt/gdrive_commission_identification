"""Google Drive front end: read a Drive folder, download its images, and
(optionally) reorganize them into per-artist folders *inside* Drive with a
dry-run and an undo manifest.

All google-api imports are lazy so the rest of the package keeps working without
them installed. The URL/ID parsing and the move-planning logic are pure and
unit-tested in tests/test_drive.py.
"""
from __future__ import annotations
import json
import os
import re

FOLDER_MIME = "application/vnd.google-apps.folder"
IMAGE_MIME_PREFIX = "image/"
SCOPES_READONLY = ["https://www.googleapis.com/auth/drive.readonly"]
SCOPES_RW = ["https://www.googleapis.com/auth/drive"]

_FOLDER_URL_PATTERNS = [
    re.compile(r"/folders/([A-Za-z0-9_\-]+)"),
    re.compile(r"[?&]id=([A-Za-z0-9_\-]+)"),
]


def looks_like_drive(s: str) -> bool:
    """True if the argument is obviously a Google Drive URL."""
    return bool(s) and ("drive.google.com" in s or "docs.google.com" in s)


def parse_folder_id(url_or_id: str):
    """Extract a Drive folder ID from a share URL, or accept a bare ID."""
    if not url_or_id:
        return None
    s = url_or_id.strip()
    for rx in _FOLDER_URL_PATTERNS:
        m = rx.search(s)
        if m:
            return m.group(1)
    if re.fullmatch(r"[A-Za-z0-9_\-]{10,}", s):
        return s
    return None


def target_folder_for(ident, include_review=False):
    """Pure: the folder name an identification should land in, or None to skip."""
    from .organize import _safe_folder
    if ident.status == "confident" and ident.artist:
        return _safe_folder(ident.artist)
    if ident.status == "review":
        if not include_review:
            return None
        return "_review-" + _safe_folder(ident.artist or "unknown")
    return "_unknown"


def plan_moves(idents, id_by_rel, include_review=False):
    """Pure: build [{id, rel_path, folder}] for files that should move.

    id_by_rel maps a scanned rel_path -> Drive file id. Items whose rel_path has
    no mapped id (or that should be skipped) are dropped.
    """
    plan = []
    for it in idents:
        folder = target_folder_for(it, include_review=include_review)
        if folder is None:
            continue
        fid = id_by_rel.get(it.item.rel_path)
        if not fid:
            continue
        plan.append({"id": fid, "rel_path": it.item.rel_path, "folder": folder})
    return plan


def get_service(credentials_path="credentials.json", token_path="token.json",
                writable=False):  # pragma: no cover
    """Build an authenticated Drive v3 service via the OAuth installed-app flow."""
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    scopes = SCOPES_RW if writable else SCOPES_READONLY
    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, scopes)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(credentials_path):
                raise RuntimeError(
                    f"Drive API client secrets not found at '{credentials_path}'. "
                    "Create an OAuth client (Desktop app) in Google Cloud Console, "
                    "enable the Drive API, and download it as credentials.json. See README.")
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, scopes)
            creds = flow.run_local_server(port=0)
        with open(token_path, "w", encoding="utf-8") as fh:
            fh.write(creds.to_json())
    return build("drive", "v3", credentials=creds)


def list_images(service, folder_id, _prefix=""):  # pragma: no cover
    """Recursively list image files under folder_id.

    Returns [{id, name, rel_path, parent}] preserving sub-folder structure in rel_path.
    """
    out = []
    page_token = None
    while True:
        resp = service.files().list(
            q=f"'{folder_id}' in parents and trashed=false",
            fields="nextPageToken, files(id, name, mimeType)",
            pageSize=1000, pageToken=page_token,
            includeItemsFromAllDrives=True, supportsAllDrives=True,
        ).execute()
        for f in resp.get("files", []):
            if f["mimeType"] == FOLDER_MIME:
                out += list_images(service, f["id"],
                                   _prefix=os.path.join(_prefix, f["name"]))
            elif f["mimeType"].startswith(IMAGE_MIME_PREFIX):
                rel = os.path.join(_prefix, f["name"]) if _prefix else f["name"]
                out.append({"id": f["id"], "name": f["name"],
                            "rel_path": rel, "parent": folder_id})
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return out


def download_images(service, files, dest_dir, progress=None):  # pragma: no cover
    """Download each listed file under dest_dir/<rel_path>. Skips files already
    present and non-empty. Returns the input records with a 'local_path' added."""
    from googleapiclient.http import MediaIoBaseDownload
    os.makedirs(dest_dir, exist_ok=True)
    local = []
    total = len(files)
    for i, f in enumerate(files, 1):
        target = os.path.join(dest_dir, f["rel_path"])
        os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
        if not os.path.exists(target) or os.path.getsize(target) == 0:
            req = service.files().get_media(fileId=f["id"])
            with open(target, "wb") as fh:
                downloader = MediaIoBaseDownload(fh, req)
                done = False
                while not done:
                    _status, done = downloader.next_chunk()
        rec = dict(f)
        rec["local_path"] = target
        local.append(rec)
        if progress:
            progress(i, total, type("_I", (), {"rel_path": f["rel_path"]}))
    return local


def _ensure_folder(service, name, parent_id, cache):  # pragma: no cover
    key = (parent_id, name)
    if key in cache:
        return cache[key]
    safe = name.replace("\\", "\\\\").replace("'", "\\'")
    resp = service.files().list(
        q=(f"'{parent_id}' in parents and name='{safe}' and "
           f"mimeType='{FOLDER_MIME}' and trashed=false"),
        fields="files(id, name)", pageSize=1,
        includeItemsFromAllDrives=True, supportsAllDrives=True,
    ).execute()
    found = resp.get("files", [])
    if found:
        fid = found[0]["id"]
    else:
        meta = {"name": name, "mimeType": FOLDER_MIME, "parents": [parent_id]}
        fid = service.files().create(body=meta, fields="id",
                                     supportsAllDrives=True).execute()["id"]
    cache[key] = fid
    return fid


def apply_in_drive(service, idents, id_by_rel, root_folder_id,
                   include_review=False, dry_run=True,
                   manifest_path="drive_apply_manifest.json"):  # pragma: no cover
    """Move files into root/<artist>/ inside Drive.

    Dry-run writes the planned moves only. A real run performs the moves and
    writes an undo manifest that `undo_from_manifest` can reverse.
    """
    plan = plan_moves(idents, id_by_rel, include_review=include_review)
    if dry_run:
        with open(manifest_path, "w", encoding="utf-8") as fh:
            json.dump({"dry_run": True, "root": root_folder_id, "moves": plan}, fh, indent=2)
        return {"files_moved": len(plan), "manifest": manifest_path}

    folder_cache = {}
    undo = []
    moved = 0
    for entry in plan:
        fid = entry["id"]
        meta = service.files().get(fileId=fid, fields="parents",
                                   supportsAllDrives=True).execute()
        old_parents = meta.get("parents", [])
        new_parent = _ensure_folder(service, entry["folder"], root_folder_id, folder_cache)
        if old_parents == [new_parent]:
            continue  # already in place
        service.files().update(
            fileId=fid, addParents=new_parent,
            removeParents=",".join(old_parents),
            fields="id, parents", supportsAllDrives=True,
        ).execute()
        undo.append({"id": fid, "add": old_parents, "remove": new_parent})
        moved += 1
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump({"dry_run": False, "root": root_folder_id, "undo": undo}, fh, indent=2)
    return {"files_moved": moved, "manifest": manifest_path}


def undo_from_manifest(service, manifest_path):  # pragma: no cover
    """Reverse the moves recorded by a non-dry-run apply_in_drive."""
    with open(manifest_path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    undo = data.get("undo", [])
    n = 0
    for entry in undo:
        service.files().update(
            fileId=entry["id"], addParents=",".join(entry["add"]),
            removeParents=entry["remove"],
            fields="id, parents", supportsAllDrives=True,
        ).execute()
        n += 1
    return n
