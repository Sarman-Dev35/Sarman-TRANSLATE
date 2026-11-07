import json
import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import patch_manager
from patch_manager import PatchError, inspect_patch, install_patch, uninstall_latest, installed_patch_languages
from translation_core import (
    TextEntry, scan_game_texts, validate_translation, save_workspace,
    load_workspace, build_translated_files, create_translation_patch, StaleSourceError,
    remove_incomplete_patch,
)


class TranslationCoreTests(unittest.TestCase):
    def test_text_scan_prunes_binary_asset_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Localization").mkdir()
            (root / "Binaries").mkdir()
            (root / "Localization" / "strings.json").write_text('{"hello":"Hello"}', encoding="utf-8")
            (root / "Binaries" / "noise.json").write_text('{"noise":"Do not translate"}', encoding="utf-8")
            entries = scan_game_texts(root)
            self.assertEqual([entry.source for entry in entries], ["Hello"])

    def test_json_extracts_strings_and_skips_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "strings.json").write_text('{"title":"New Game","id":"ABC123","items":["Load","Exit"]}', encoding="utf-8")
            entries = scan_game_texts(root)
            self.assertEqual({e.source for e in entries}, {"New Game", "Load", "Exit"})

    def test_placeholder_validation(self):
        self.assertEqual(validate_translation("Hello {player_name}", "Merhaba {player_name}"), [])
        self.assertTrue(validate_translation("Hello %s", "Merhaba"))

    def test_deeply_nested_json_does_not_abort_other_file_scans(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            nested = '{"a":' * 1100 + '"Deep text"' + '}' * 1100
            (root / "deep.json").write_text(nested, encoding="utf-8")
            (root / "valid.json").write_text('{"title":"Valid text"}', encoding="utf-8")
            entries = scan_game_texts(root)
            self.assertEqual([item.source for item in entries], ["Valid text"])

    def test_scan_selects_only_the_requested_locale_and_keeps_neutral_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Localization" / "en-US").mkdir(parents=True)
            (root / "Localization" / "tr-TR").mkdir(parents=True)
            (root / "Localization" / "de-DE").mkdir(parents=True)
            (root / "Localization" / "en-US" / "dialog.json").write_text('{"line":"Start Game"}', encoding="utf-8")
            (root / "Localization" / "tr-TR" / "dialog.json").write_text('{"line":"Oyuna Başla"}', encoding="utf-8")
            (root / "Localization" / "de-DE" / "dialog.json").write_text('{"line":"Spiel starten"}', encoding="utf-8")
            (root / "Data" / "English").mkdir(parents=True)
            (root / "Data" / "German").mkdir(parents=True)
            (root / "Data" / "English" / "menu.json").write_text('{"line":"English folder text"}', encoding="utf-8")
            (root / "Data" / "German" / "menu.json").write_text('{"line":"German folder text"}', encoding="utf-8")
            (root / "neutral.json").write_text('{"line":"Neutral text"}', encoding="utf-8")

            english = scan_game_texts(root, source_language="EN")
            german = scan_game_texts(root, source_language="DE")
            self.assertEqual({item.source for item in english}, {"Start Game", "English folder text", "Neutral text"})
            self.assertEqual({item.source for item in german}, {"Spiel starten", "German folder text", "Neutral text"})

    def test_csv_uses_selected_language_column(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "locale.csv").write_text(
                "key,en-US,de-DE,fr-FR\nstart,Start,Spiel starten,Démarrer\n",
                encoding="utf-8"
            )
            entries = scan_game_texts(root, source_language="DE")
            self.assertEqual([item.source for item in entries], ["Spiel starten"])

    def test_remove_incomplete_patch_only_removes_sarman_temp_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            partial = root / "unfinished.zip.tmp"
            unrelated = root / "notes.tmp"
            partial.write_bytes(b"partial zip")
            unrelated.write_bytes(b"keep")
            self.assertTrue(remove_incomplete_patch(partial))
            self.assertFalse(partial.exists())
            self.assertTrue(unrelated.exists())
            with self.assertRaisesRegex(ValueError, "Yalnızca"):
                remove_incomplete_patch(unrelated)

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

    def test_patch_export_appends_zip_extension_and_verifies_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "text.json").write_text('{"hello":"Hello"}', encoding="utf-8")
            entries = scan_game_texts(root)
            entries[0].translated = "Merhaba"
            created = create_translation_patch(root, entries, root / "generated", "Demo")
            self.assertEqual(created.name, "generated.zip")
            self.assertTrue(created.is_file())
            with zipfile.ZipFile(created) as archive:
                self.assertIsNone(archive.testzip())
                self.assertIn("sarman-patch.json", archive.namelist())
            self.assertFalse((root / "generated.zip.tmp").exists())

    def test_patch_export_rejects_lost_placeholders_with_clear_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "text.json").write_text('{"hello":"Hello {player_name}"}', encoding="utf-8")
            entries = scan_game_texts(root)
            entries[0].translated = "Merhaba"
            with self.assertRaisesRegex(ValueError, "Değişkenleri"):
                create_translation_patch(root, entries, root / "bad.zip", "Demo")
            self.assertFalse((root / "bad.zip").exists())

    def test_patch_export_does_not_leave_partial_zip_for_stale_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "text.json"
            source.write_text('{"hello":"Hello"}', encoding="utf-8")
            entries = scan_game_texts(root)
            entries[0].translated = "Merhaba"
            source.write_text('{"hello":"Changed"}', encoding="utf-8")
            with self.assertRaises(StaleSourceError):
                create_translation_patch(root, entries, root / "stale.zip", "Demo")
            self.assertFalse((root / "stale.zip").exists())
            self.assertFalse((root / "stale.zip.tmp").exists())


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

    def test_rejects_windows_reserved_patch_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for target in ("CON.txt", "folder/LPT1.ini", "bad?.json"):
                archive = root / (str(len(target)) + ".zip")
                manifest = {"name": "unsafe", "version": "1", "files": [{"source": "files/a.txt", "target": target}]}
                with zipfile.ZipFile(archive, "w") as zf:
                    zf.writestr("sarman-patch.json", json.dumps(manifest))
                    zf.writestr("files/a.txt", "text")
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


    def test_export_rejects_stale_source_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "strings.json"
            source.write_text('{"title":"Start"}', encoding="utf-8")
            entries = scan_game_texts(root)
            entries[0].translated = "Başla"
            source.write_text('{"title":"Continue"}', encoding="utf-8")
            with self.assertRaises(StaleSourceError):
                build_translated_files(root, entries)

    def test_ini_export_preserves_crlf_line_endings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "lang.ini"
            source.write_bytes(b"start=Start\r\nexit=Exit\r\n")
            entries = scan_game_texts(root)
            for item in entries:
                item.translated = {"Start": "Başla", "Exit": "Çıkış"}[item.source]
            output = build_translated_files(root, entries)["lang.ini"]
            self.assertIn(b"start=Ba\xc5\x9fla\r\n", output)
            self.assertNotIn(b"\n", output.replace(b"\r\n", b""))

    def test_json_root_string_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "root.json"
            source.write_text('"Start Game"', encoding="utf-8")
            entries = scan_game_texts(root)
            self.assertEqual(len(entries), 1)
            entries[0].translated = "Oyuna Başla"
            output = build_translated_files(root, entries)["root.json"].decode("utf-8")
            self.assertEqual(json.loads(output), "Oyuna Başla")

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


    def test_csv_semicolon_dialect_and_utf8_bom_are_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "locale.csv"
            source.write_bytes(b"\xef\xbb\xbfkey;en;fr\r\nstart;\"Start, now\";\"Demarrer\"\r\n")
            entries = scan_game_texts(root)
            self.assertEqual(len(entries), 1)
            entries[0].translated = "Şimdi Başla; lütfen"
            output = build_translated_files(root, entries)["locale.csv"]
            self.assertTrue(output.startswith(b"\xef\xbb\xbf"))
            self.assertIn("start;\"Şimdi Başla; lütfen\";Demarrer\r\n".encode("utf-8"), output)
            self.assertNotIn('start,"Şimdi'.encode("utf-8"), output)

    def test_json_bom_indent_and_final_newline_are_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "strings.json"
            source.write_bytes(b"\xef\xbb\xbf{\r\n    \"title\": \"Start\"\r\n}\r\n")
            entries = scan_game_texts(root)
            entries[0].translated = "Başla"
            output = build_translated_files(root, entries)["strings.json"]
            self.assertTrue(output.startswith(b"\xef\xbb\xbf"))
            self.assertIn(b'    \"title\": \"Ba\xc5\x9fla\"', output)
            self.assertTrue(output.endswith(b"\r\n"))
            self.assertNotIn(b"\n", output.replace(b"\r\n", b""))

if __name__ == "__main__":
    unittest.main()
