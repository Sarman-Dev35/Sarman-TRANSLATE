import tempfile
import unittest
from pathlib import Path

from translation_core import scan_game_texts, validate_translation, save_workspace, load_workspace, TextEntry


class TranslationCoreTests(unittest.TestCase):
    def test_json_extracts_strings_and_skips_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "strings.json").write_text('{"title":"New Game","id":"ABC123","items":["Load","Exit"]}', encoding="utf-8")
            entries = scan_game_texts(root)
            self.assertEqual({e.source for e in entries}, {"New Game", "Load", "Exit"})

    def test_placeholder_validation(self):
        self.assertEqual(validate_translation("Hello {player_name}", "Merhaba {player_name}"), [])
        self.assertTrue(validate_translation("Hello %s", "Merhaba"),)

    def test_workspace_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "work.json"
            item = TextEntry("a", "a.json", "root.title", "Hello", "Merhaba", "translated")
            save_workspace(path, tmp, [item])
            self.assertEqual(load_workspace(path)["entries"][0]["translated"], "Merhaba")


if __name__ == "__main__":
    unittest.main()
