import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from game_discovery import Game
from game_visuals import GameArtService, WARM_PALETTE, make_placeholder_cover, theme_stylesheet


class GameVisualsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_placeholder_cover_is_high_resolution(self):
        image = make_placeholder_cover("Test Game", "Steam", *WARM_PALETTE)
        self.assertFalse(image.isNull())
        self.assertEqual((image.width(), image.height()), (420, 236))

    def test_stylesheet_uses_static_sarman_accent_without_color_gradients(self):
        style = theme_stylesheet()
        self.assertIn("#f06a3d", style)
        self.assertIn("QPushButton#primary", style)
        self.assertNotIn("qlineargradient", style.lower())

    def test_artwork_cache_survives_service_restart(self):
        game = Game("Example Game", "Steam · kurulu", r"C:\\Games\\Example", "12345")
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"LOCALAPPDATA": tmp}):
                first_service = GameArtService()
                first_service.cache_dir = Path(tmp) / "covers"
                first_service.cache_dir.mkdir()
                image = QImage(1920, 1080, QImage.Format.Format_RGB32)
                image.fill(0xFF3366CC)
                self.assertTrue(image.save(str(first_service.cache_path(game)), "JPG", 94))

                # A new service instance, as on the next application launch,
                # must load the already saved full-resolution cover.
                second_service = GameArtService()
                second_service.cache_dir = first_service.cache_dir
                cached = second_service.cached_cover(game)
                self.assertIsNotNone(cached)
                self.assertEqual((cached.width(), cached.height()), (1920, 1080))

    def test_cache_identity_does_not_depend_on_install_path(self):
        first = Game("Example Game", "Steam · kurulu", r"C:\\Games\\Example", "12345")
        moved = Game("Example Game", "Steam · kurulu", r"D:\\SteamLibrary\\Example", "12345")
        self.assertEqual(GameArtService.cache_key(first), GameArtService.cache_key(moved))

    def test_cache_identity_distinguishes_different_games(self):
        first = Game("Example Game", "Steam · kurulu", r"C:\\Games\\Example", "12345")
        second = Game("Different Game", "Steam · kurulu", r"C:\\Games\\Different", "67890")
        self.assertNotEqual(GameArtService.cache_key(first), GameArtService.cache_key(second))


if __name__ == "__main__":
    unittest.main()
