import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import local_engine


class LocalEngineTests(unittest.TestCase):
    def test_cache_reuses_previous_translation_without_model(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(local_engine, "APP_DATA", Path(tmp)):
            local_engine._cache_put("Start Game", "Oyuna Başla")
            with patch.dict("sys.modules", {"argostranslate": None, "argostranslate.translate": None}):
                self.assertEqual(local_engine.translate_text("Start Game"), "Oyuna Başla")

    def test_empty_text_is_unchanged(self):
        self.assertEqual(local_engine.translate_text("  "), "  ")

    def test_status_is_safe_when_optional_engine_missing(self):
        with patch.dict("sys.modules", {"argostranslate": None, "argostranslate.translate": None}):
            self.assertFalse(local_engine.model_status()["installed"])


if __name__ == "__main__":
    unittest.main()
