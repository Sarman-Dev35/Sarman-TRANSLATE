import ast
import unittest
from pathlib import Path

from translation_core import scan_game_texts


class RepeatedScanRegressionTests(unittest.TestCase):
    def test_scanning_same_game_repeatedly_is_deterministic(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "lang").mkdir()
            (root / "lang" / "en.json").write_text(
                '{"start":"Start Game","quit":"Quit"}', encoding="utf-8"
            )

            first = scan_game_texts(root, source_language="EN")
            second = scan_game_texts(root, source_language="EN")
            third = scan_game_texts(root, source_language="EN")

            self.assertEqual(
                [(e.entry_id, e.source) for e in first],
                [(e.entry_id, e.source) for e in second],
            )
            self.assertEqual(
                [(e.entry_id, e.source) for e in second],
                [(e.entry_id, e.source) for e in third],
            )

    def test_qthread_finished_cleanup_does_not_dereference_sender(self):
        # QThread.finished is also connected to deleteLater. Cleanup slots must
        # not inspect sender(), whose wrapped C++ object may already be deleted
        # by the time a queued GUI-thread callback runs.
        root = Path(__file__).resolve().parents[1]
        for filename, method_name in (
            ("main.py", "_scan_thread_finished"),
            ("translation_studio.py", "_scan_thread_finished"),
            ("translation_studio.py", "_worker_thread_finished"),
        ):
            tree = ast.parse((root / filename).read_text(encoding="utf-8"))
            method = next(
                node for node in ast.walk(tree)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == method_name
            )
            names = {
                node.id for node in ast.walk(method)
                if isinstance(node, ast.Name)
            }
            self.assertNotIn("sender", names, f"{filename}:{method_name} must not use sender()")


if __name__ == "__main__":
    unittest.main()
