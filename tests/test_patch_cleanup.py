import json
import tempfile
import unittest
import zipfile
import os
from pathlib import Path
from unittest.mock import patch

import patch_manager


class PatchCleanupTests(unittest.TestCase):
    def test_interrupted_install_can_be_recovered_from_journal(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            game = base / "Game"
            game.mkdir()
            first = game / "first.json"
            second = game / "second.json"
            first.write_text("first-original", encoding="utf-8")
            second.write_text("second-original", encoding="utf-8")
            archive = base / "multi.zip"
            manifest = {
                "name": "Interrupted TR",
                "version": "1",
                "language": "tr",
                "files": [
                    {"source": "files/first.json", "target": "first.json"},
                    {"source": "files/second.json", "target": "second.json"},
                ],
            }
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("sarman-patch.json", json.dumps(manifest))
                zf.writestr("files/first.json", "first-translated")
                zf.writestr("files/second.json", "second-translated")

            real_replace = os.replace
            replace_calls = {"count": 0}

            def crash_during_second_file(source, destination):
                replace_calls["count"] += 1
                if replace_calls["count"] == 5:
                    raise SystemExit("simulated power loss")
                return real_replace(source, destination)

            with patch.object(patch_manager, "APP_DATA", base / "appdata"):
                with patch.object(patch_manager.os, "replace", side_effect=crash_during_second_file):
                    with self.assertRaises(SystemExit):
                        patch_manager.install_patch(archive, game)

                self.assertEqual(first.read_text(encoding="utf-8"), "first-translated")
                self.assertEqual(second.read_text(encoding="utf-8"), "second-original")
                pending = patch_manager.incomplete_patch_installs(game)
                self.assertEqual(len(pending), 1)
                self.assertEqual(pending[0]["name"], "Interrupted TR")
                self.assertEqual(patch_manager.installed_patch_languages(game), set())

                recovered = patch_manager.rollback_incomplete_patches(game)
                self.assertEqual(recovered, ["Interrupted TR"])
                self.assertEqual(first.read_text(encoding="utf-8"), "first-original")
                self.assertEqual(second.read_text(encoding="utf-8"), "second-original")
                self.assertEqual(patch_manager.incomplete_patch_installs(game), [])

    def test_new_installs_are_blocked_until_interrupted_patch_is_recovered(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            game = base / "Game"
            game.mkdir()
            target = game / "lang.json"
            target.write_text("original", encoding="utf-8")
            archive = base / "patch.zip"
            manifest = {"name": "TR Patch", "version": "1", "language": "tr",
                        "files": [{"source": "files/lang.json", "target": "lang.json"}]}
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("sarman-patch.json", json.dumps(manifest))
                zf.writestr("files/lang.json", "translated")
            with patch.object(patch_manager, "APP_DATA", base / "appdata"):
                # Seed a recovery journal using the same crash path as the previous test.
                backup_dir = base / "appdata" / "backups" / "Game" / "unfinished"
                backup_dir.mkdir(parents=True)
                (backup_dir / "install.json").write_text(json.dumps({
                    "schema": 1, "name": "unfinished", "status": "installing",
                    "game_dir": str(game.resolve()), "files": []
                }), encoding="utf-8")
                with self.assertRaisesRegex(patch_manager.PatchError, "yarım kalmış"):
                    patch_manager.install_patch(archive, game)
                patch_manager.rollback_incomplete_patches(game)
                result = patch_manager.install_patch(archive, game)
                self.assertEqual(result["name"], "TR Patch")
                self.assertEqual(target.read_text(encoding="utf-8"), "translated")

    def test_uninstall_all_restores_game_and_clears_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            game = base / "Game"
            game.mkdir()
            target = game / "lang.json"
            target.write_text("original", encoding="utf-8")
            archive = base / "patch.zip"
            import zipfile
            manifest = {"name": "TR Patch", "version": "1", "language": "tr",
                        "files": [{"source": "files/lang.json", "target": "lang.json"}]}
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("sarman-patch.json", json.dumps(manifest))
                zf.writestr("files/lang.json", "translated")
            with patch.object(patch_manager, "APP_DATA", base / "appdata"):
                patch_manager.install_patch(archive, game)
                removed = patch_manager.uninstall_all(game)
                self.assertEqual(removed, ["TR Patch"])
                self.assertEqual(target.read_text(encoding="utf-8"), "original")
                self.assertEqual(patch_manager.installed_patch_languages(game), set())
                self.assertEqual(patch_manager.uninstall_all(game), [])


if __name__ == "__main__":
    unittest.main()
