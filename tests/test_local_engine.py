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
                self.kwargs = kwargs
                return {"choices": [{"text": "SARMANTERM0000X SARMANPH0001X"}]}

        with tempfile.TemporaryDirectory() as tmp, patch.object(local_engine, "APP_DATA", Path(tmp)):
            fake = FakeModel()
            with patch.object(local_engine, "_get_model", return_value=fake):
                result = local_engine.translate_text("Press any key {player}", game_name="Test Game")
            self.assertEqual(result, "Bir tuşa bas {player}")
            self.assertIn("Translate the following video-game text from English into Turkish", fake.prompt)
            self.assertIn("Return only the Turkish translation", fake.prompt)
            self.assertNotIn("<|im_start|>", fake.prompt)
            self.assertEqual(fake.kwargs["temperature"], 0.3)
            self.assertEqual(fake.kwargs["top_k"], 20)

    def test_model_metadata_targets_compact_translation_model(self):
        self.assertEqual(local_engine.MODEL_NAME, "Hy-MT2-1.8B-Q4_K_M.gguf")
        self.assertIn("tencent/Hy-MT2-1.8B-GGUF", local_engine.MODEL_URL)
        self.assertEqual(local_engine.MODEL_FILE_SIZE, 1_133_080_448)
        self.assertIn("1,13 GB", local_engine.model_status()["download_size"])
        self.assertIn("Hy-MT2", local_engine.model_status()["engine"])

    def test_glossary_change_invalidates_translation_memory(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(local_engine, "APP_DATA", Path(tmp)):
            local_engine._cache_put("Continue", "Devam")
            self.assertEqual(local_engine._cache_get("Continue"), "Devam")
            local_engine.set_glossary_term("Continue", "Sürdür")
            self.assertIsNone(local_engine._cache_get("Continue"))

    def test_empty_text_is_unchanged(self):
        self.assertEqual(local_engine.translate_text("  "), "  ")

    def test_status_is_safe_when_model_missing(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(local_engine, "MODEL_PATH", Path(tmp) / "missing.gguf"):
            self.assertFalse(local_engine.model_status()["installed"])


if __name__ == "__main__":
    unittest.main()
