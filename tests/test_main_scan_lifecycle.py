import os
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from main import MainWindow


class MainWindowScanLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_repeated_library_scans_release_each_worker(self):
        with patch("main.discover_games", return_value=[]):
            window = MainWindow(auto_scan=False)
            try:
                for _ in range(20):
                    window.start_scan()
                    deadline = time.monotonic() + 8
                    while window.worker is not None and time.monotonic() < deadline:
                        self.app.processEvents()
                        time.sleep(0.005)
                    self.app.processEvents()
                    self.assertIsNone(window.worker, "library scan worker was not released")
                    self.assertTrue(window.scan_btn.isEnabled())
                    self.assertEqual(window.table.rowCount(), 0)
            finally:
                window.close()
                self.app.processEvents()

    def test_stale_finish_cannot_clear_newer_library_scan(self):
        with patch("main.QTimer.singleShot"), patch("main.discover_games", return_value=[]):
            window = MainWindow()
            try:
                class CurrentWorker:
                    def isRunning(self):
                        return True

                current_worker = CurrentWorker()
                window._scan_generation = 2
                window.worker = current_worker

                window._scan_thread_finished(1)

                self.assertIs(window.worker, current_worker)
            finally:
                window.worker = None
                window.close()
                self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
