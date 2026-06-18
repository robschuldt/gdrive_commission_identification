# gdrive_commission_identification

Identify the **artist** behind each piece of commission art and group the artwork
into per-artist folders. Built for furry/anime commission collections (where the
files are usually unhelpfully named `IMG_8578.PNG`, `Untitled_Artwork.png`, etc.).

> **Status: v0.2 — identification engine + interactive review/labelling + dry-run report.**
> The "paste a Google Drive link and it sorts your Drive" front end is Phase 2.
> We're building the *hard* part first (identifying the artist) and proving it on
> real images before wiring up Drive (the easy part).

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

## Use

Download your Drive folder (Drive → right-click the folder → Download) and unzip it,
then point the tool at that local folder.

```bash
# 1) DRY RUN — writes a report, moves nothing
python -m commission_id.cli "/path/to/Jaiy Deer" --config config.yaml

# inspect reports/identifications.csv, fix any aliases in config.yaml, re-run

# 2) APPLY — copy files into organized/<artist>/ (add --move to move instead)
python -m commission_id.cli "/path/to/Jaiy Deer" --config config.yaml \
    --apply --dest organized --include-review

# filename + metadata only (no network):
python -m commission_id.cli "/path/to/folder" --no-reverse
```

`--apply` always writes `organized/_apply_manifest.json` so any move can be undone.

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
the rate-limited APIs entirely. Then sort using them:

```bash
python -m commission_id.cli "/path/to/Jaiy Deer" --config config.yaml \
    --apply --dest organized --include-review
```

Useful review flags: `--scope all|review|unknown|both`, `--style-threshold 0.92`
(stricter = fewer look-alikes), `--dup-threshold 6` (perceptual-hash distance),
`--live` (allow on-the-fly API lookups instead of cache-only).

## Config (`config.yaml`)

- `commissioner_aliases` — every handle/nickname that means *you*, not an artist.
- `artist_aliases` — collapse one artist's handles across sites into one folder name.
- `reverse_search` — toggle Fluffle/SauceNAO, set the SauceNAO key, `include_adult`,
  throttle, and the required Fluffle `User-Agent`.
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
  pipeline.py    orchestration
  review.py      interactive pop-up review + dup/style propagation (Tkinter)
  cli.py         command-line entry point
tests/           unit tests for the deterministic logic
```

## Roadmap

- **Phase 2:** Google Drive front end — paste a folder link, read via the Drive API,
  and (optionally) reorganize in-place in Drive with dry-run + undo.
- **Phase 3:** optional CLIP-style embedder backend for stronger style matching;
  e621 post-ID → artist-tag lookups; alias auto-merge; web-based review queue.
