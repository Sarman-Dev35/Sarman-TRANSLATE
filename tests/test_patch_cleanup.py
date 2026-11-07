import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import patch_manager


class PatchCleanupTests(unittest.TestCase):
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
