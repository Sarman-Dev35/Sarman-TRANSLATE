import tempfile
import unittest
from pathlib import Path
from engine_support import inspect_game_engine


class EngineSupportTests(unittest.TestCase):
    def test_detects_gamemaker_without_modifying_game(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data.win").write_bytes(b"FORM")
            (root / "lang.json").write_text('{"hello":"Hello"}', encoding="utf-8")
            report = inspect_game_engine(root)
            self.assertEqual(report.engine, "GameMaker")
            self.assertEqual(report.native_localization_files, 1)
            self.assertEqual(report.supported_text_files, 1)
            self.assertTrue((root / "data.win").is_file())

    def test_detects_unity_and_reports_partial_support(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "UnityPlayer.dll").write_bytes(b"MZ")
            (root / "StreamingAssets").mkdir()
            (root / "StreamingAssets" / "Menus_tr.json").write_text('{"start":"Başla"}', encoding="utf-8")
            report = inspect_game_engine(root)
            self.assertEqual(report.engine, "Unity")
            self.assertIn("Kısmi", report.status)
            self.assertEqual(report.supported_text_files, 1)

    def test_unknown_engine_is_not_claimed_as_supported(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = inspect_game_engine(tmp)
            self.assertEqual(report.engine, "Belirlenemedi")
            self.assertEqual(report.confidence, "Düşük")


if __name__ == "__main__":
    unittest.main()
