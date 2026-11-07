import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QEventLoop, QObject, QTimer, Slot
from PySide6.QtWidgets import QApplication

from game_discovery import Game, _normal, discover_games
from translation_core import scan_game_texts
from translation_studio import TextScanWorker, TranslationStudio


class _ScanReceiver(QObject):
    def __init__(self, studio, loop):
        super().__init__()
        self.studio = studio
        self.loop = loop
        self.results = []

    @Slot(list)
    def completed(self, entries):
        self.results.append(len(entries))
        if len(self.results) == 1:
            QTimer.singleShot(60, self.studio.scan)
        else:
            QTimer.singleShot(60, self.loop.quit)


class ScanResilienceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

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

    def test_translation_studio_can_rescan_same_game_twice(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "strings.json").write_text('{"title":"New Game"}', encoding="utf-8")
            studio = TranslationStudio(Game("Rescan Test", "Test", str(root)))
            loop = QEventLoop()
            receiver = _ScanReceiver(studio, loop)
            original_start = TextScanWorker.start

            def observe_start(worker, *args, **kwargs):
                worker.completed.connect(receiver.completed)
                return original_start(worker, *args, **kwargs)

            with patch.object(TextScanWorker, "start", observe_start):
                studio.scan()
                QTimer.singleShot(10000, loop.quit)
                loop.exec()
            self.assertEqual(receiver.results, [1, 1])
            self.assertIsNone(studio.scan_worker)
            studio.close()


if __name__ == "__main__":
    unittest.main()
