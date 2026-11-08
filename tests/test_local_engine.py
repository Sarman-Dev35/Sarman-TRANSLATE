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

    def test_model_added_line_break_is_normalized_for_single_line_source(self):
        class FakeModel:
            def __call__(self, prompt, **kwargs):
                return {"choices": [{"text": "Kapıyı\n aç"}]}

        with tempfile.TemporaryDirectory() as tmp, patch.object(local_engine, "APP_DATA", Path(tmp)):
            with patch.object(local_engine, "_get_model", return_value=FakeModel()), patch.object(
                local_engine, "_cache_get", return_value=None
            ), patch.object(local_engine, "_cache_put"):
                self.assertEqual(local_engine.translate_text("Open the door"), "Kapıyı aç")

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
            self.assertIn("without additional explanation", fake.prompt)
            self.assertNotIn("<|im_start|>", fake.prompt)
            self.assertEqual(fake.kwargs["temperature"], 0.7)
            self.assertEqual(fake.kwargs["top_k"], 20)

    def test_multiline_translation_preserves_exact_line_breaks(self):
        class FakeModel:
            def __call__(self, prompt, **kwargs):
                return {"choices": [{"text": "Çevrildi"}]}

        source = "First line\r\nSecond line\n\nFourth line\rLast line"
        expected = "Çevrildi\r\nÇevrildi\n\nÇevrildi\rÇevrildi"
        with tempfile.TemporaryDirectory() as tmp, patch.object(local_engine, "APP_DATA", Path(tmp)):
            with patch.object(local_engine, "_get_model", return_value=FakeModel()), patch.object(
                local_engine, "_cache_get", return_value=None
            ), patch.object(local_engine, "_cache_put"):
                self.assertEqual(local_engine.translate_text(source), expected)

    def test_model_metadata_targets_compact_translation_model(self):
        self.assertEqual(local_engine.MODEL_NAME, "Hy-MT2-1.8B-Q4_K_M.gguf")
        self.assertIn("tencent/Hy-MT2-1.8B-GGUF", local_engine.MODEL_URL)
        self.assertEqual(local_engine.MODEL_FILE_SIZE, 1_133_080_448)
        self.assertIn("1,13 GB", local_engine.model_status()["download_size"])
        self.assertIn("Hy-MT2", local_engine.model_status()["engine"])

    def test_model_inference_is_serialized_across_translation_threads(self):
        import threading
        import time

        class FakeModel:
            def __init__(self):
                self.guard = threading.Lock()
                self.active = 0
                self.max_active = 0

            def __call__(self, prompt, **kwargs):
                with self.guard:
                    self.active += 1
                    self.max_active = max(self.max_active, self.active)
                time.sleep(0.04)
                with self.guard:
                    self.active -= 1
                return {"choices": [{"text": "Kapıyı aç"}]}

        fake = FakeModel()
        results = []
        with patch.object(local_engine, "_get_model", return_value=fake), patch.object(
            local_engine, "_cache_get", return_value=None
        ), patch.object(local_engine, "_cache_put"):
            threads = [
                threading.Thread(target=lambda value=value: results.append(local_engine.translate_text(value)))
                for value in ("Open the door", "Unlock the gate")
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=5)
        self.assertEqual(len(results), 2)
        self.assertEqual(fake.max_active, 1)

    def test_glossary_change_invalidates_translation_memory(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(local_engine, "APP_DATA", Path(tmp)):
            local_engine._cache_put("Continue", "Devam")
            self.assertEqual(local_engine._cache_get("Continue"), "Devam")
            local_engine.set_glossary_term("Continue", "Sürdür")
            self.assertIsNone(local_engine._cache_get("Continue"))

    def test_single_word_glossary_does_not_override_contextual_sentence_translation(self):
        class FakeModel:
            def __init__(self):
                self.prompt = ""
            def __call__(self, prompt, **kwargs):
                self.prompt = prompt
                return {"choices": [{"text": "Motoru çalıştır"}]}

        with tempfile.TemporaryDirectory() as tmp, patch.object(local_engine, "APP_DATA", Path(tmp)):
            fake = FakeModel()
            with patch.object(local_engine, "_get_model", return_value=fake), patch.object(
                local_engine, "_cache_get", return_value=None
            ), patch.object(local_engine, "_cache_put"):
                result = local_engine.translate_text("Start the engine")
            self.assertEqual(result, "Motoru çalıştır")
            self.assertIn("Text: Start the engine", fake.prompt)
            self.assertNotIn("Text: SARMANTERM", fake.prompt)

    def test_cache_key_changes_when_translation_pipeline_changes(self):
        with patch.object(local_engine, "APP_DATA", Path(tempfile.gettempdir())):
            first = local_engine._cache_key("Start")
            with patch.object(local_engine, "TRANSLATION_PIPELINE_VERSION", "next"):
                second = local_engine._cache_key("Start")
        self.assertNotEqual(first, second)

    def test_download_uses_large_buffer(self):
        self.assertEqual(local_engine.DOWNLOAD_CHUNK_SIZE, 4 * 1024 * 1024)

    def test_translation_memory_writes_are_serialized_across_threads(self):
        import threading

        with tempfile.TemporaryDirectory() as tmp, patch.object(local_engine, "APP_DATA", Path(tmp)):
            errors = []
            def write(index):
                try:
                    local_engine._cache_put(f"source-{index}", f"çeviri-{index}")
                except Exception as exc:
                    errors.append(exc)
            threads = [threading.Thread(target=write, args=(index,)) for index in range(16)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)
            self.assertFalse(errors)
            for index in range(16):
                self.assertEqual(local_engine._cache_get(f"source-{index}"), f"çeviri-{index}")

    def test_empty_text_is_unchanged(self):
        self.assertEqual(local_engine.translate_text("  "), "  ")

    def test_status_is_safe_when_model_missing(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(local_engine, "MODEL_PATH", Path(tmp) / "missing.gguf"):
            self.assertFalse(local_engine.model_status()["installed"])

    def test_model_status_distinguishes_missing_partial_corrupt_and_installed_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            model_path = Path(tmp) / local_engine.MODEL_NAME
            partial_path = model_path.with_suffix(model_path.suffix + ".part")
            with patch.object(local_engine, "MODEL_PATH", model_path), patch.object(local_engine, "MODEL_FILE_SIZE", 8):
                self.assertEqual(local_engine.model_status()["state"], "missing")
                partial_path.write_bytes(b"part")
                self.assertEqual(local_engine.model_status()["state"], "partial")
                partial_path.unlink()
                model_path.write_bytes(b"bad")
                status = local_engine.model_status()
                self.assertEqual(status["state"], "corrupt")
                self.assertTrue(status["present"])
                self.assertFalse(status["installed"])
                model_path.write_bytes(b"GGUF1234")
                self.assertEqual(local_engine.model_status()["state"], "installed")

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
                self.assertTrue(local_engine.uninstall_english_turkish_model())
                self.assertFalse(partial_path.exists())

    def test_truncated_model_download_keeps_partial_file_for_resume(self):
        import hashlib

        payload = b"GGUF-short"
        class FakeResponse:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, _size):
                if getattr(self, "sent", False):
                    return b""
                self.sent = True
                return payload

        with tempfile.TemporaryDirectory() as tmp:
            model_path = Path(tmp) / local_engine.MODEL_NAME
            partial = model_path.with_suffix(model_path.suffix + ".part")
            with patch.object(local_engine, "MODEL_DIR", Path(tmp)), patch.object(
                local_engine, "MODEL_PATH", model_path
            ), patch.object(local_engine, "MODEL_FILE_SIZE", len(payload) + 4), patch.object(
                local_engine, "MODEL_SHA256", hashlib.sha256(payload).hexdigest()
            ), patch.object(local_engine.urllib.request, "urlopen", return_value=FakeResponse()):
                with self.assertRaisesRegex(local_engine.LocalTranslationError, "sürdürülebilir"):
                    local_engine.install_english_turkish_model()
            self.assertTrue(partial.is_file())
            self.assertEqual(partial.read_bytes(), payload)
            self.assertFalse(model_path.exists())

    def test_model_download_reports_bytes_speed_and_eta(self):
        import hashlib

        payload = b"small-test-model"
        events = []

        class FakeResponse:
            status = 200
            headers = {"Content-Length": str(len(payload))}

            def __init__(self):
                self.sent = False

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self, _size):
                if self.sent:
                    return b""
                self.sent = True
                return payload

        with tempfile.TemporaryDirectory() as tmp:
            model_path = Path(tmp) / "model.gguf"
            with patch.object(local_engine, "MODEL_DIR", Path(tmp)), patch.object(
                local_engine, "MODEL_PATH", model_path
            ), patch.object(local_engine, "MODEL_FILE_SIZE", len(payload)), patch.object(
                local_engine, "MODEL_SHA256", hashlib.sha256(payload).hexdigest()
            ), patch.object(local_engine.urllib.request, "urlopen", return_value=FakeResponse()):
                local_engine.install_english_turkish_model(lambda *values: events.append(values))

            self.assertTrue(model_path.is_file())
            self.assertTrue(events)
            self.assertTrue(all(len(event) == 4 for event in events))
            self.assertEqual(events[-1][0], len(payload))
            self.assertEqual(events[-1][1], len(payload))


if __name__ == "__main__":
    unittest.main()
