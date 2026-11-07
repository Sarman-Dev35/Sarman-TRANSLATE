import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

import translation_studio
from game_discovery import Game
from translation_studio import TranslationStudio


class TranslationStudioWorkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_repeated_sequential_scans_do_not_reuse_or_leak_workers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Game"
            root.mkdir()
            (root / "strings.json").write_text('{"title":"Start Game"}', encoding="utf-8")
            with patch.object(translation_studio, "APP_DATA", Path(tmp) / "appdata"):
                studio = TranslationStudio(Game("Worker Stress", "Test", str(root)))
                try:
                    for _ in range(20):
                        studio.scan()
                        deadline = time.monotonic() + 8
                        while studio.scan_worker is not None and time.monotonic() < deadline:
                            self.app.processEvents()
                            time.sleep(0.005)
                        self.app.processEvents()
                        self.assertIsNone(studio.scan_worker, "scan worker did not release after completion")
                        self.assertTrue(studio.scan_btn.isEnabled())
                        self.assertEqual(len(studio.entries), 1)
                finally:
                    studio.close()
                    self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
