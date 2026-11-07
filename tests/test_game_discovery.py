import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from game_discovery import _scan_epic, _scan_steam, _detect_language_files, discover_games


class GameDiscoveryTests(unittest.TestCase):
    def test_steam_manifest_discovers_installed_game(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            steam = base / "Steam"
            game = steam / "steamapps" / "common" / "Sample Game"
            game.mkdir(parents=True)
            manifest = steam / "steamapps" / "appmanifest_123.acf"
            manifest.write_text('"AppState" { "appid" "123" "name" "Sample Game" "installdir" "Sample Game" }', encoding="utf-8")
            env = {"PROGRAMFILES": str(base), "PROGRAMFILES(X86)": str(base)}
            with patch.dict(os.environ, env):
                found = _scan_steam()
            self.assertTrue(any(item.name == "Sample Game" and item.app_id == "123" for item in found))

    def test_epic_manifest_discovers_installed_game(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            game = base / "EpicGame"
            game.mkdir()
            manifest_dir = base / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests"
            manifest_dir.mkdir(parents=True)
            (manifest_dir / "sample.item").write_text(json.dumps({
                "InstallLocation": str(game), "DisplayName": "Epic Sample", "AppName": "EpicSample"
            }), encoding="utf-8")
            with patch.dict(os.environ, {"PROGRAMDATA": str(base)}):
                found = _scan_epic()
            self.assertTrue(any(item.name == "Epic Sample" and item.path == str(game) for item in found))

    def test_detects_language_codes_from_locale_folders(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            locale = root / "Data" / "Localization"
            locale.mkdir(parents=True)
            (locale / "tr-TR.json").write_text('{"hello":"Merhaba"}', encoding="utf-8")
            (locale / "en-US.json").write_text('{"hello":"Hello"}', encoding="utf-8")
            (locale / "ar.json").write_text('{"hello":"مرحبا"}', encoding="utf-8")
            (locale / "id.json").write_text('{"hello":"Halo"}', encoding="utf-8")
            (root / "Data").mkdir()
            (root / "Data" / "strings.hi.json").write_text('{"hello":"नमस्ते"}', encoding="utf-8")
            self.assertEqual(_detect_language_files(root), ("AR", "EN", "HI", "ID", "TR"))

    def test_user_added_folder_discovers_game_executable(self):
        with tempfile.TemporaryDirectory() as tmp:
            library = Path(tmp) / "Library"
            game = library / "SampleGame"
            game.mkdir(parents=True)
            (game / "SampleGame.exe").write_bytes(b"MZ")
            found = discover_games([str(library)])
            self.assertTrue(any(item.name == "SampleGame" for item in found))


if __name__ == "__main__":
    unittest.main()
