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

    def test_glossary_and_placeholders_are_restored(self):
        class FakeModel:
            def __call__(self, prompt, **kwargs):
                self.prompt = prompt
                return {"choices": [{"text": "SARMANTERM0000X SARMANPH0001X"}]}

        with tempfile.TemporaryDirectory() as tmp, patch.object(local_engine, "APP_DATA", Path(tmp)):
            fake = FakeModel()
            with patch.object(local_engine, "_get_model", return_value=fake):
                result = local_engine.translate_text("Press any key {player}", game_name="Test Game")
            self.assertEqual(result, "Bir tuşa bas {player}")
            self.assertIn("professional video-game localization", fake.prompt)

    def test_glossary_change_invalidates_translation_memory(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(local_engine, "APP_DATA", Path(tmp)):
            local_engine._cache_put("Continue", "Devam")
            self.assertEqual(local_engine._cache_get("Continue"), "Devam")
            local_engine.set_glossary_term("Continue", "Sürdür")
            self.assertIsNone(local_engine._cache_get("Continue"))

    def test_empty_text_is_unchanged(self):
        self.assertEqual(local_engine.translate_text("  "), "  ")

    def test_status_is_safe_when_optional_engine_missing(self):
        with patch.dict("sys.modules", {"argostranslate": None, "argostranslate.translate": None}):
            self.assertFalse(local_engine.model_status()["installed"])


if __name__ == "__main__":
    unittest.main()
