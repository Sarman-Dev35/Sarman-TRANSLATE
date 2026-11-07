import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import patch_manager
from patch_manager import PatchError, inspect_patch, install_patch, uninstall_latest
from translation_core import (
    TextEntry, scan_game_texts, validate_translation, save_workspace,
    load_workspace, build_translated_files, create_translation_patch,
)


class TranslationCoreTests(unittest.TestCase):
    def test_json_extracts_strings_and_skips_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "strings.json").write_text('{"title":"New Game","id":"ABC123","items":["Load","Exit"]}', encoding="utf-8")
            entries = scan_game_texts(root)
            self.assertEqual({e.source for e in entries}, {"New Game", "Load", "Exit"})

    def test_placeholder_validation(self):
        self.assertEqual(validate_translation("Hello {player_name}", "Merhaba {player_name}"), [])
        self.assertTrue(validate_translation("Hello %s", "Merhaba"))

    def test_workspace_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "work.json"
            item = TextEntry("a", "a.json", "root.title", "Hello", "Merhaba", "translated")
            save_workspace(path, tmp, [item])
            self.assertEqual(load_workspace(path)["entries"][0]["translated"], "Merhaba")

    def test_json_translation_export_does_not_touch_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "strings.json"
            original = '{"menu":{"start":"Start"},"items":["Load","Exit"]}'
            source.write_text(original, encoding="utf-8")
            entries = scan_game_texts(root)
            for item in entries:
                item.translated = {"Start": "Başla", "Load": "Yükle", "Exit": "Çıkış"}[item.source]
                item.status = "translated"
            built = build_translated_files(root, entries)
            translated = json.loads(built["strings.json"].decode("utf-8"))
            self.assertEqual(translated["menu"]["start"], "Başla")
            self.assertEqual(translated["items"], ["Yükle", "Çıkış"])
            self.assertEqual(source.read_text(encoding="utf-8"), original)

    def test_ini_translation_export_preserves_comments_and_quotes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "lang.ini"
            original = '[menu]\nstart = "Start Game"\n; keep this comment\nexit=Exit\n'
            source.write_text(original, encoding="utf-8")
            entries = scan_game_texts(root)
            translations = {"Start Game": "Oyuna Başla", "Exit": "Çıkış"}
            for item in entries:
                item.translated = translations[item.source]
            output = build_translated_files(root, entries)["lang.ini"].decode("utf-8")
            self.assertIn('start = "Oyuna Başla"', output)
            self.assertIn("; keep this comment", output)
            self.assertIn("exit=Çıkış", output)
            self.assertEqual(source.read_text(encoding="utf-8"), original)

    def test_patch_package_manifest_and_contents(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "text.json").write_text('{"hello":"Hello"}', encoding="utf-8")
            entries = scan_game_texts(root)
            entries[0].translated = "Merhaba"
            archive = root / "patch.zip"
            create_translation_patch(root, entries, archive, "Demo")
            manifest = inspect_patch(archive)
            self.assertEqual(manifest["files"][0]["target"], "text.json")


class PatchManagerTests(unittest.TestCase):
    def test_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "bad.zip"
            manifest = {"name": "bad", "version": "1", "files": [{"source": "files/a.txt", "target": "../outside.txt"}]}
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("sarman-patch.json", json.dumps(manifest))
                zf.writestr("files/a.txt", "bad")
            with self.assertRaises(PatchError):
                inspect_patch(archive)

    def test_rejects_executable_patch_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "unsafe.zip"
            manifest = {"name": "unsafe", "version": "1", "files": [{"source": "files/game.exe", "target": "game.exe"}]}
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("sarman-patch.json", json.dumps(manifest))
                zf.writestr("files/game.exe", "not really an exe")
            with self.assertRaises(PatchError):
                inspect_patch(archive)

    def test_install_and_rollback_restore_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game = root / "Game"
            game.mkdir()
            target = game / "lang.json"
            target.write_text("original", encoding="utf-8")
            archive = root / "patch.zip"
            manifest = {"name": "Demo TR", "version": "1", "files": [{"source": "files/lang.json", "target": "lang.json"}]}
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("sarman-patch.json", json.dumps(manifest))
                zf.writestr("files/lang.json", "translated")
            with patch.object(patch_manager, "APP_DATA", root / "appdata"):
                install_patch(archive, game)
                self.assertEqual(target.read_text(encoding="utf-8"), "translated")
                self.assertEqual(uninstall_latest(game), "Demo TR")
                self.assertEqual(target.read_text(encoding="utf-8"), "original")


if __name__ == "__main__":
    unittest.main()
