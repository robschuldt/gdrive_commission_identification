import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from commission_id import drive
from commission_id.models import ImageItem, Identification


def _ident(rel, artist, status):
    it = ImageItem(path="/x/" + rel, rel_path=rel,
                   filename=os.path.basename(rel), parent_folder="")
    return Identification(item=it, artist=artist, status=status)


class TestDriveParsing(unittest.TestCase):
    def test_folders_url(self):
        self.assertEqual(
            drive.parse_folder_id(
                "https://drive.google.com/drive/folders/0ABCdef_123-XYZ?usp=sharing"),
            "0ABCdef_123-XYZ")

    def test_u_number_url(self):
        self.assertEqual(
            drive.parse_folder_id("https://drive.google.com/drive/u/2/folders/abcDEF123456"),
            "abcDEF123456")

    def test_open_id_url(self):
        self.assertEqual(
            drive.parse_folder_id("https://drive.google.com/open?id=ZZ_topSecret99"),
            "ZZ_topSecret99")

    def test_bare_id(self):
        self.assertEqual(drive.parse_folder_id("1A2B3C4D5E6F7G"), "1A2B3C4D5E6F7G")

    def test_junk(self):
        self.assertIsNone(drive.parse_folder_id("not a real link"))
        self.assertIsNone(drive.parse_folder_id(""))

    def test_looks_like_drive(self):
        self.assertTrue(drive.looks_like_drive("https://drive.google.com/drive/folders/x"))
        self.assertFalse(drive.looks_like_drive("/home/me/Jaiy Deer"))


class TestDrivePlanning(unittest.TestCase):
    def test_target_folder(self):
        self.assertEqual(
            drive.target_folder_for(_ident("a.png", "Kari Wanz", "confident")), "Kari Wanz")
        self.assertIsNone(drive.target_folder_for(_ident("b.png", "Maybe", "review")))
        self.assertEqual(
            drive.target_folder_for(_ident("b.png", "Maybe", "review"), include_review=True),
            "_review-Maybe")
        self.assertEqual(
            drive.target_folder_for(_ident("c.png", None, "unknown")), "_unknown")

    def test_plan_moves_maps_ids_and_excludes_review(self):
        idents = [_ident("a.png", "Artie", "confident"),
                  _ident("sub/b.png", "Dunno", "review"),
                  _ident("c.png", None, "unknown")]
        id_by_rel = {"a.png": "ID_A", "sub/b.png": "ID_B", "c.png": "ID_C"}
        plan = drive.plan_moves(idents, id_by_rel)  # review excluded by default
        folders = {p["rel_path"]: p["folder"] for p in plan}
        self.assertEqual(folders, {"a.png": "Artie", "c.png": "_unknown"})
        ids = {p["rel_path"]: p["id"] for p in plan}
        self.assertEqual(ids["a.png"], "ID_A")

    def test_plan_moves_includes_review_when_asked(self):
        idents = [_ident("b.png", "Dunno", "review")]
        plan = drive.plan_moves(idents, {"b.png": "ID_B"}, include_review=True)
        self.assertEqual(plan, [{"id": "ID_B", "rel_path": "b.png", "folder": "_review-Dunno"}])

    def test_plan_skips_files_without_a_mapped_id(self):
        idents = [_ident("a.png", "Artie", "confident")]
        plan = drive.plan_moves(idents, {}, include_review=True)
        self.assertEqual(plan, [])


if __name__ == "__main__":
    unittest.main()
