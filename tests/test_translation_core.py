import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import patch_manager
from patch_manager import PatchError, inspect_patch, install_patch, uninstall_latest, installed_patch_languages
from gemini_translator import GeminiTranslationError, translate_batch
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

    def test_gemini_batch_response_and_placeholders(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self):
                result = {"translations": [
                    {"id": "row1", "text": "Merhaba {player}"},
                    {"id": "row2", "text": "Yükle %s"}
                ]}
                payload = {"candidates": [{"content": {"parts": [{"text": json.dumps(result, ensure_ascii=False)}]}}]}
                return json.dumps(payload).encode("utf-8")
        with patch("gemini_translator.urllib.request.urlopen", return_value=Response()):
            result = translate_batch("fake-key", "gemini-test", [("row1", "Hello {player}"), ("row2", "Load %s")])
        self.assertEqual(result["row1"], "Merhaba {player}")
        self.assertEqual(result["row2"], "Yükle %s")

    def test_gemini_batch_rejects_lost_placeholders(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self):
                result = {"translations": [{"id": "row1", "text": "Merhaba"}]}
                payload = {"candidates": [{"content": {"parts": [{"text": json.dumps(result)}]}}]}
                return json.dumps(payload).encode("utf-8")
        with patch("gemini_translator.urllib.request.urlopen", return_value=Response()):
            with self.assertRaises(GeminiTranslationError):
                translate_batch("fake-key", "gemini-test", [("row1", "Hello {player}")])

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

    def test_csv_uses_english_column_without_overwriting_other_languages(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "strings.csv"
            original = chr(10).join(("key,en,fr", "start,Start,Demarrer", ""))
            source.write_text(original, encoding="utf-8")
            entries = scan_game_texts(root)
            self.assertEqual([entry.source for entry in entries], ["Start"])
            entries[0].translated = "Başla"
            output = build_translated_files(root, entries)["strings.csv"].decode("utf-8")
            self.assertIn("start,Başla,Demarrer", output)

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

    def test_ignores_malformed_local_install_journal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game = root / "Game"
            game.mkdir()
            journal = root / "appdata" / "backups" / "Game" / "broken" / "install.json"
            journal.parent.mkdir(parents=True)
            journal.write_text("[]", encoding="utf-8")
            with patch.object(patch_manager, "APP_DATA", root / "appdata"):
                with self.assertRaises(PatchError):
                    uninstall_latest(game)

    def test_install_and_rollback_restore_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game = root / "Game"
            game.mkdir()
            target = game / "lang.json"
            target.write_text("original", encoding="utf-8")
            archive = root / "patch.zip"
            manifest = {"name": "Demo TR", "version": "1", "language": "tr", "files": [{"source": "files/lang.json", "target": "lang.json"}]}
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("sarman-patch.json", json.dumps(manifest))
                zf.writestr("files/lang.json", "translated")
            with patch.object(patch_manager, "APP_DATA", root / "appdata"):
                install_patch(archive, game)
                self.assertEqual(target.read_text(encoding="utf-8"), "translated")
                self.assertEqual(installed_patch_languages(game), {"tr"})
                self.assertEqual(uninstall_latest(game), "Demo TR")
                self.assertEqual(installed_patch_languages(game), set())
                self.assertEqual(target.read_text(encoding="utf-8"), "original")


    def test_json_keys_with_dots_slashes_and_brackets_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "special.json"
            original = {"menu.title": "Start", "path/key": "Load", "array[0]": ["Exit"], "tilde~key": "Options"}
            source.write_text(json.dumps(original), encoding="utf-8")
            entries = scan_game_texts(root)
            translations = {"Start": "Başla", "Load": "Yükle", "Exit": "Çıkış", "Options": "Seçenekler"}
            for item in entries:
                item.translated = translations[item.source]
            output = json.loads(build_translated_files(root, entries)["special.json"].decode("utf-8"))
            self.assertEqual(output["menu.title"], "Başla")
            self.assertEqual(output["path/key"], "Yükle")
            self.assertEqual(output["array[0]"], ["Çıkış"])
            self.assertEqual(output["tilde~key"], "Seçenekler")

    def test_csv_locale_headers_select_english_column_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "locale.csv"
            source.write_text("key,en-US,fr-FR\nstart,Start,Démarrer\n", encoding="utf-8")
            entries = scan_game_texts(root)
            self.assertEqual([item.source for item in entries], ["Start"])
            entries[0].translated = "Başla"
            output = build_translated_files(root, entries)["locale.csv"].decode("utf-8")
            self.assertIn("start,Başla,Démarrer", output)

if __name__ == "__main__":
    unittest.main()
