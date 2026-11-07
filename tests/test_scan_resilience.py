import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from game_discovery import _normal, discover_games
from translation_core import scan_game_texts


class ScanResilienceTests(unittest.TestCase):
    def test_repeated_text_scans_are_stable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "strings.json").write_text('{"title":"New Game"}', encoding="utf-8")
            first = scan_game_texts(root)
            second = scan_game_texts(root)
            self.assertEqual(
                [(item.entry_id, item.source) for item in first],
                [(item.entry_id, item.source) for item in second],
            )

    def test_game_path_symlink_loop_falls_back_without_crashing(self):
        candidate = Path("sample-game")
        expected = os.path.normcase(os.path.abspath(str(candidate)))
        with patch.object(Path, "resolve", side_effect=RuntimeError("symlink loop")):
            self.assertEqual(_normal(candidate), expected)

    def test_repeated_library_discovery_returns_a_list(self):
        first = discover_games([])
        second = discover_games([])
        self.assertIsInstance(first, list)
        self.assertIsInstance(second, list)


if __name__ == "__main__":
    unittest.main()
