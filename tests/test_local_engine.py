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

    def test_packaged_model_lives_next_to_executable(self):
        with patch.object(local_engine.sys, "frozen", True, create=True), patch.object(
            local_engine.sys, "executable", r"C:\\Portable\\Sarman TRANSLATE\\Sarman TRANSLATE.exe"
        ):
            self.assertEqual(
                local_engine._model_directory(),
                Path(r"C:\\Portable\\Sarman TRANSLATE")
            )

    def test_model_uninstall_unloads_and_removes_weights_and_partial(self):
        class FakeModel:
            closed = False

            def close(self):
                self.closed = True

        with tempfile.TemporaryDirectory() as tmp:
            model_path = Path(tmp) / local_engine.MODEL_NAME
            partial_path = model_path.with_suffix(model_path.suffix + ".part")
            model_path.write_bytes(b"model")
            partial_path.write_bytes(b"partial")
            fake = FakeModel()
            with patch.object(local_engine, "MODEL_PATH", model_path), patch.object(local_engine, "_MODEL", fake):
                self.assertTrue(local_engine.uninstall_english_turkish_model())
                self.assertTrue(fake.closed)
                self.assertIsNone(local_engine._MODEL)
                self.assertFalse(model_path.exists())
                self.assertFalse(partial_path.exists())

    def test_model_uninstall_keeps_user_translation_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model_path = root / local_engine.MODEL_NAME
            model_path.write_bytes(b"model")
            with patch.object(local_engine, "MODEL_PATH", model_path), patch.object(local_engine, "APP_DATA", root):
                glossary = root / "glossary.json"
                glossary.write_text('{"Boss":"Patron"}', encoding="utf-8")
                local_engine.uninstall_english_turkish_model()
                self.assertTrue(glossary.exists())

    def test_partial_model_download_is_visible_for_resume_and_removal(self):
        with tempfile.TemporaryDirectory() as tmp:
            model_path = Path(tmp) / local_engine.MODEL_NAME
            partial_path = model_path.with_suffix(model_path.suffix + ".part")
            partial_path.write_bytes(b"partial")
            with patch.object(local_engine, "MODEL_PATH", model_path):
                status = local_engine.model_status()
                self.assertFalse(status["installed"])
                self.assertFalse(status["present"])
                self.assertTrue(status["partial_present"])
                self.assertTrue(local_engine.uninstall_english_turkish_model() is False or not partial_path.exists())
                self.assertFalse(partial_path.exists())


if __name__ == "__main__":
    unittest.main()
