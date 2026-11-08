import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from game_discovery import Game
import translation_studio


class TranslationStudioUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_translation_studio_builds_with_fixed_sarman_palette(self):
        game_dir = tempfile.TemporaryDirectory()
        self.addCleanup(game_dir.cleanup)
        game = Game(
            name="UI Smoke Test",
            platform="Test",
            path=game_dir.name,
        )
        status = {
            "installed": False,
            "present": False,
            "partial_present": False,
            "message": "Model kurulmadı",
            "model_path": "",
        }
        with tempfile.TemporaryDirectory() as app_data:
            with patch.object(translation_studio, "APP_DATA", Path(app_data)):
                with patch.object(translation_studio, "model_status", return_value=status):
                    dialog = translation_studio.TranslationStudio(game)
                    self.addCleanup(dialog.close)
                    self.assertEqual(dialog.windowTitle(), "Çeviri Atölyesi · UI Smoke Test")
                    self.assertIsNotNone(dialog.scan_btn)
                    self.assertIsNotNone(dialog.table)
                    self.assertIn("#f06a3d", dialog.styleSheet())


    def test_dialog_refuses_to_close_while_worker_is_running(self):
        import tempfile
        from unittest.mock import patch
        from PySide6.QtGui import QCloseEvent
        from game_discovery import Game

        status = {
            "installed": False,
            "present": False,
            "partial_present": False,
            "message": "Model kurulmadı",
            "model_path": "",
        }

        class RunningWorker:
            def isRunning(self):
                return True

        with tempfile.TemporaryDirectory() as game_dir, tempfile.TemporaryDirectory() as app_data:
            game = Game(name="Close Guard Test", platform="Test", path=game_dir)
            with patch.object(translation_studio, "APP_DATA", Path(app_data)):
                with patch.object(translation_studio, "model_status", return_value=status):
                    dialog = translation_studio.TranslationStudio(game)
            dialog.worker = RunningWorker()
            event = QCloseEvent()
            with patch.object(translation_studio.QMessageBox, "information"):
                dialog.closeEvent(event)
            self.assertFalse(event.isAccepted())
            dialog.worker = None
            dialog.autosave_timer.stop()
            dialog.close()


if __name__ == "__main__":
    unittest.main()
