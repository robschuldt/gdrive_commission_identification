import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from commission_id.config import Config
from commission_id.models import ImageItem, ArtistCandidate
from commission_id.signals import filename_candidates
from commission_id.normalize import is_commissioner, canonicalize
from commission_id.reverse import artist_from_url
from commission_id.aggregate import aggregate


def _item(fn, folder="Regular Clean"):
    return ImageItem(path="/x/" + fn, rel_path=folder + "/" + fn, filename=fn, parent_folder=folder)


def test_commissioner_filter():
    c = Config()
    assert is_commissioner("Jaiy", c)
    assert is_commissioner("jaiydawoof", c)
    assert is_commissioner("JaiyDeer", c)
    assert not is_commissioner("kariwanz", c)


def test_filename_dump_pattern():
    c = Config()
    cands = filename_candidates(_item("1483300700.neltruin_pocket.png"), c)
    assert "neltruin" in [x.name.lower() for x in cands]


def test_filename_pairs_with_commissioner():
    c = Config()
    cands = filename_candidates(_item("kariwanz_jaiy_ref.png"), c)
    kari = [x for x in cands if x.name.lower() == "kariwanz"]
    assert kari and kari[0].weight >= 0.45


def test_filename_ignores_junk():
    c = Config()
    cands = filename_candidates(_item("IMG_8578.png"), c)
    assert all(x.name.lower() != "img" for x in cands)
    assert not any(x.name.isdigit() for x in cands)


def test_url_extraction():
    assert artist_from_url("https://twitter.com/kariwanz/status/123") == "kariwanz"
    assert artist_from_url("https://www.deviantart.com/someartist/art/Foo-123") == "someartist"
    assert artist_from_url("https://www.furaffinity.net/user/coffeefish/") == "coffeefish"
    assert artist_from_url("https://e621.net/posts/12345") is None


def test_canonicalize_aliases():
    c = Config()
    c.artist_aliases = {"Kari Wanz": ["kariwanz", "kari"]}
    assert canonicalize("kariwanz", c) == "Kari Wanz"
    assert canonicalize("KARI", c) == "Kari Wanz"


def test_aggregate_confident_on_e621_exact():
    c = Config()
    cands = [
        ArtistCandidate(name="kariwanz", source="fluffle", weight=0.9, platform="e621",
                        detail="exact match on e621"),
        ArtistCandidate(name="kariwanz", source="filename", weight=0.3, detail="token"),
    ]
    ident = aggregate(_item("IMG_0236.png"), cands, c)
    assert ident.artist.lower() == "kariwanz"
    assert ident.status == "confident"
    assert ident.confidence >= 0.75


def test_aggregate_drops_commissioner():
    c = Config()
    cands = [ArtistCandidate(name="Jaiy", source="fluffle", weight=0.9, platform="twitter")]
    ident = aggregate(_item("art.png"), cands, c)
    assert ident.status == "unknown"
    assert ident.artist is None


def test_aggregate_review_on_close_call():
    c = Config()
    cands = [
        ArtistCandidate(name="artistA", source="fluffle", weight=0.55, platform="twitter"),
        ArtistCandidate(name="artistB", source="saucenao", weight=0.55, platform="pixiv"),
    ]
    ident = aggregate(_item("art.png"), cands, c)
    assert ident.status == "review"


# ---- decisions, similarity, review helpers, decision injection ----

import tempfile
from PIL import Image
from PIL.PngImagePlugin import PngInfo  # noqa: F401

from commission_id.decisions import Decisions
from commission_id import similarity
from commission_id.review import build_guesses, in_scope
from commission_id.pipeline import identify_all
from commission_id.scanner import compute_phash
from commission_id.models import Identification


def _png(path, color, size=(120, 120)):
    Image.new("RGB", size, color).save(path)


def test_decisions_roundtrip():
    with tempfile.TemporaryDirectory() as d:
        dec = Decisions(d + "/dec.sqlite")
        assert dec.get("abc") is None
        dec.set("abc", "kariwanz", "human")
        assert dec.get("abc")["artist"] == "kariwanz"
        assert dec.count() == 1
        dec.delete("abc")
        assert dec.get("abc") is None
        dec.close()


def test_hamming_and_near_dup():
    assert similarity.hamming_hex("ffffffffffffffff", "ffffffffffffffff") == 0
    assert similarity.hamming_hex("ffffffffffffffff", "fffffffffffffffe") == 1
    assert similarity.is_near_dup("ffffffffffffffff", "fffffffffffffffe", 6)
    assert not similarity.is_near_dup("ffffffffffffffff", "0000000000000000", 6)


def test_descriptor_discriminates_style():
    with tempfile.TemporaryDirectory() as d:
        import numpy as np
        # A: smooth horizontal gradient; A2: same gradient brighter (similar);
        # C: high-frequency checkerboard (different structure)
        a = np.tile(np.linspace(0, 255, 120, dtype="uint8"), (120, 1))
        Image.fromarray(np.stack([a, a, a], -1)).save(d + "/a.png")
        a2 = np.clip(a.astype(int) + 20, 0, 255).astype("uint8")
        Image.fromarray(np.stack([a2, a2, a2], -1)).save(d + "/a2.png")
        chk = (((np.add.outer(range(120), range(120))) % 2) * 255).astype("uint8")
        Image.fromarray(np.stack([chk, chk, chk], -1)).save(d + "/c.png")
        va = similarity.visual_descriptor(d + "/a.png")
        va2 = similarity.visual_descriptor(d + "/a2.png")
        vc = similarity.visual_descriptor(d + "/c.png")
        assert similarity.cosine(va, va2) > similarity.cosine(va, vc)


def test_style_neighbors_threshold():
    va = [1.0, 0.0, 0.0]
    pool = [("near", [0.99, 0.01, 0.0]), ("far", [0.0, 1.0, 0.0])]
    res = similarity.style_neighbors(va, pool, min_cosine=0.9)
    keys = [k for k, _ in res]
    assert "near" in keys and "far" not in keys


def test_build_guesses_dedupes_and_ranks():
    ident = Identification(item=_item("x.png"))
    ident.candidates = [
        ArtistCandidate(name="kari", source="filename", weight=0.3, canonical="Kari"),
        ArtistCandidate(name="Kari", source="fluffle", weight=0.9, canonical="Kari"),
        ArtistCandidate(name="Other", source="fluffle", weight=0.5, canonical="Other"),
    ]
    gs = build_guesses(ident)
    assert gs[0][0] == "Kari" and gs[0][1] == 0.9     # best weight kept, deduped
    assert [g[0] for g in gs] == ["Kari", "Other"]


def test_in_scope():
    rev = Identification(item=_item("x.png")); rev.status = "review"
    unk = Identification(item=_item("y.png")); unk.status = "unknown"
    con = Identification(item=_item("z.png")); con.status = "confident"
    assert in_scope(rev, "both") and in_scope(unk, "both") and not in_scope(con, "both")
    assert in_scope(con, "all")
    assert in_scope(rev, "review") and not in_scope(unk, "review")


def test_decision_injection_overrides_to_confident():
    with tempfile.TemporaryDirectory() as d:
        import os
        os.makedirs(d + "/art", exist_ok=True)
        img = d + "/art/IMG_0001.png"
        _png(img, (123, 200, 64))
        from commission_id.models import ImageItem
        ph = compute_phash(ImageItem(path=img, rel_path="art/IMG_0001.png",
                                     filename="IMG_0001.png", parent_folder="art"))
        dec = Decisions(d + "/dec.sqlite")
        dec.set(ph, "kariwanz", "human")
        dec.close()
        cfg = Config()
        cfg.reverse_search.enabled = False
        idents = identify_all(d, cfg, cache_path=d + "/c.sqlite",
                              decisions_path=d + "/dec.sqlite", live=False)
        assert len(idents) == 1
        assert idents[0].artist.lower() == "kariwanz"
        assert idents[0].status == "confident"


def test_color_guard_prevents_flat_phash_collision():
    """Two different solid colours share a degenerate phash; a label on one must
    NOT bleed onto the other once mean colours are recorded."""
    with tempfile.TemporaryDirectory() as d:
        import os
        os.makedirs(d + "/art", exist_ok=True)
        from commission_id.models import ImageItem
        from commission_id.scanner import compute_phash, compute_avg_rgb
        red, blue = d + "/art/red.png", d + "/art/blue.png"
        _png(red, (185, 30, 30)); _png(blue, (30, 45, 175))
        ir = ImageItem(path=red, rel_path="art/red.png", filename="red.png", parent_folder="art")
        ib = ImageItem(path=blue, rel_path="art/blue.png", filename="blue.png", parent_folder="art")
        assert compute_phash(ir) == compute_phash(ib)              # collision confirmed
        dec = Decisions(d + "/dec.sqlite")
        dec.set(compute_phash(ir), "redartist", "human", avg=compute_avg_rgb(ir))
        dec.close()
        cfg = Config(); cfg.reverse_search.enabled = False
        idents = identify_all(d, cfg, cache_path=d + "/c.sqlite",
                              decisions_path=d + "/dec.sqlite", live=False)
        by = {i.item.filename: i for i in idents}
        assert by["red.png"].artist.lower() == "redartist"        # label sticks to red
        assert (by["blue.png"].artist or "").lower() != "redartist"  # guard blocks blue
