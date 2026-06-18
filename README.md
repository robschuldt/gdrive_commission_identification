# gdrive_commission_identification

Identify the **artist** behind each piece of commission art and group the artwork
into per-artist folders. Built for furry/anime commission collections (where the
files are usually unhelpfully named `IMG_8578.PNG`, `Untitled_Artwork.png`, etc.).

> **Status: v0.3 — identification engine + interactive review/labelling + dry-run
> report + a Google Drive front end.** Paste a Drive folder link and it will
> download, identify, and (optionally) reorganize the folder in Drive — or just
> produce a sorted local copy. The hard part (identifying the artist) is proven on
> real images first; Drive is wired on top of it.

## How it identifies an artist

It combines several signals per image, cheapest first, then scores them:

1. **Filename** — tokens, dump-style names (`1483300700.artist_desc.png`), with your
   own character name (`jaiy`, `jaiydawoof`) stripped out. If your name appears in a
   filename, the *other* token gets boosted as the likely artist.
2. **Embedded metadata** — PNG text chunks / EXIF `Artist` / `Copyright`.
3. **Reverse image search** — the workhorse for this kind of collection:
   - **Fluffle** (`api.fluffle.xyz`) — furry-focused: e621, Fur Affinity, Weasyl,
     Inkbunny, Twitter/X, Bluesky, DeviantArt. On **e621** the returned author is the
     real artist (from artist tags); on other platforms it's the *uploader*, which
     might be the artist **or you** — so your name is filtered out there too.
   - **SauceNAO** (optional, needs an API key) — broader anime/Pixiv coverage.

Each image ends up `confident`, `review` (ambiguous — you decide), or `unknown`
(nothing found — likely a privately delivered piece).

## Honest limitations

- Reverse search only finds art that was **publicly posted** to an indexed site.
  Private/Discord-only deliveries won't be found → expect a real `unknown` bucket.
- The APIs are **rate-limited** (Fluffle: one request at a time; SauceNAO free tier:
  ~ a few per 30s / ~100–200 per day). Results are cached by perceptual hash, so
  large libraries are a resumable multi-session job, not instant.
- Filename-only matches are marked `review`, never auto-`confident`.

## Install

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp config.example.yaml config.yaml                  # then edit config.yaml
```

## Use — a Google Drive link (the easy path)

Point it straight at a Drive folder. It downloads the images to `--work-dir`,
identifies them, and writes the dry-run report. Nothing in Drive changes unless you
ask. (First run opens a browser for Google sign-in — see **Drive setup** below.)

```bash
# 1) DRY RUN — download + identify + report, touches nothing in Drive
python -m commission_id.cli "https://drive.google.com/drive/folders/XXXX" --config config.yaml

# 2a) Sorted LOCAL copy into organized/<artist>/ (safe, reversible)
python -m commission_id.cli "https://drive.google.com/drive/folders/XXXX" \
    --config config.yaml --apply --dest organized --include-review

# 2b) Reorganize IN Drive into per-artist folders (dry-run first, then --apply)
python -m commission_id.cli "https://drive.google.com/drive/folders/XXXX" \
    --config config.yaml --drive-apply                 # shows what WOULD move
python -m commission_id.cli "https://drive.google.com/drive/folders/XXXX" \
    --config config.yaml --drive-apply --apply         # actually moves, writes undo manifest

# undo an in-Drive reorganization
python -m commission_id.cli x --undo drive_apply_manifest.json
```

In-Drive moves only ever change a file's parent folder (no copies, no renames,
nothing trashed), and every move is recorded so `--undo` can put it all back.

## Use — a local folder

Download your Drive folder yourself (Drive → right-click → Download) and unzip it,
or point at any local folder:

```bash
python -m commission_id.cli "/path/to/Jaiy Deer" --config config.yaml          # dry run
python -m commission_id.cli "/path/to/Jaiy Deer" --config config.yaml \
    --apply --dest organized --include-review                                  # sorted copy
python -m commission_id.cli "/path/to/folder" --no-reverse                     # filename + metadata only
```

`--apply` always writes `organized/_apply_manifest.json` so any move can be undone.
Adult-flagged files are reverse-searched by default; pass `--skip-adult` to skip them.

## Drive setup (one time)

The Drive API needs your own OAuth client (free):

1. In the [Google Cloud Console](https://console.cloud.google.com/), create/select a
   project and **enable the Google Drive API**.
2. Create an **OAuth client ID** of type **Desktop app**, download it, and save it as
   `credentials.json` next to the tool.
3. First run opens a browser to authorize; the resulting token is cached in
   `token.json`. Both files are git-ignored. A dry run only needs read-only access;
   `--drive-apply` requests read/write.

## Review & label it yourself (recommended)

For your own commissions, you're the best signal there is. The review tool pops up
each image the bots couldn't pin down and lets you name the artist — then spreads
that label intelligently:

```bash
# pop up every "review"/"unknown" image (run the dry-run first so results are cached)
python -m commission_id.review "/path/to/Jaiy Deer" --config config.yaml
```

- **Quick-pick** the tool's guesses (click or press `1`-`9`), or type the artist and
  press Enter. `Skip` leaves it unlabeled; `Back` revisits the previous one.
- **Exact duplicates** (alt versions, the clean/NSFW pair, crops, resaves) get the
  same label automatically — matched by perceptual hash and guarded by mean colour
  so a flat red icon never gets confused with a flat blue one.
- **Style look-alikes** are shown as a thumbnail grid; tick the ones that really are
  the same artist and they're labelled too. This is a *suggestion* surfaced for your
  confirmation, never an automatic assignment (style is not a reliable proxy for
  artist; that's a deliberate design choice).

Your labels are stored in `decisions.sqlite`, keyed so they survive re-runs and skip
the rate-limited APIs entirely. Then sort using them (locally or in Drive) exactly as
above.

Useful review flags: `--scope all|review|unknown|both`, `--style-threshold 0.92`
(stricter = fewer look-alikes), `--dup-threshold 6` (perceptual-hash distance),
`--live` (allow on-the-fly API lookups instead of cache-only).

## Config (`config.yaml`)

- `commissioner_aliases` — every handle/nickname that means *you*, not an artist.
- `artist_aliases` — collapse one artist's handles across sites into one folder name.
- `reverse_search` — toggle Fluffle/SauceNAO, set the SauceNAO key, `include_adult`
  (default `true`), throttle, and the required Fluffle `User-Agent`.
- `filename_stopwords` / `adult_hints` — tune token filtering and adult detection.

## Layout

```
commission_id/
  scanner.py     find images + perceptual hash
  signals.py     filename + metadata signals
  reverse.py     Fluffle + SauceNAO clients + URL->artist extraction
  normalize.py   commissioner filter + alias canonicalization
  aggregate.py   combine signals -> confidence + status
  similarity.py  near-duplicate (reliable) + visual-style (suggestive) matching
  decisions.py   your stored artist labels (highest-priority signal)
  organize.py    dry-run report + apply (copy/move) + undo manifest
  cache.py       SQLite cache (reverse results + style fingerprints) by phash
  drive.py       Google Drive: list/download + in-Drive reorganize (dry-run + undo)
  pipeline.py    orchestration
  review.py      interactive pop-up review + dup/style propagation (Tkinter)
  cli.py         command-line entry point (local folder OR Drive link)
tests/           unit tests for the deterministic logic
```

## Roadmap

- **Done (v0.3):** Google Drive front end — paste a folder link, read via the Drive
  API, and either produce a sorted local copy or reorganize in-place in Drive with
  dry-run + undo.
- **Phase 3:** optional CLIP-style embedder backend for stronger style matching;
  e621 post-ID → artist-tag lookups; alias auto-merge; web-based review queue.
