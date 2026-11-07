import importlib
import unittest


class StartupImportTests(unittest.TestCase):
    def test_translation_studio_imports_without_game_palette_helper(self):
        # Importing the studio must not require the optional legacy per-game
        # palette API. This catches the exact frozen-app startup regression.
        module = importlib.import_module("translation_studio")
        self.assertTrue(hasattr(module, "TranslationStudio"))

    def test_main_module_imports_cleanly(self):
        # Importing the application entry point should resolve every direct
        # module dependency before a packaged Windows build is produced.
        module = importlib.import_module("main")
        self.assertTrue(callable(module.main))


if __name__ == "__main__":
    unittest.main()
