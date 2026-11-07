import unittest
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication
from game_visuals import WARM_PALETTE, dominant_palette, make_placeholder_cover, palette_for_game, theme_stylesheet

class GameVisualsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_adofai_uses_red_blue_palette(self):
        self.assertEqual(palette_for_game("A Dance of Fire and Ice"), ("#f04459", "#397ee8"))
        self.assertEqual(palette_for_game("ADOFAI"), ("#f04459", "#397ee8"))

    def test_geometry_dash_uses_blue_yellow_palette(self):
        self.assertEqual(palette_for_game("Geometry Dash"), ("#3988ef", "#f3c744"))

    def test_unknown_game_uses_sarman_warm_palette(self):
        self.assertEqual(palette_for_game("Unknown Indie Game"), WARM_PALETTE)

    def test_placeholder_cover_is_rendered(self):
        image = make_placeholder_cover("Test Game", "Steam", "#f04459", "#397ee8")
        self.assertFalse(image.isNull())
        self.assertEqual((image.width(), image.height()), (220, 124))

    def test_artwork_palette_returns_two_colors(self):
        image = QImage(32, 32, QImage.Format.Format_ARGB32)
        image.fill(0xFF3366CC)
        first, second = dominant_palette(image)
        self.assertTrue(first.startswith("#") and second.startswith("#"))

    def test_stylesheet_uses_selected_game_accents(self):
        style = theme_stylesheet("#f04459", "#397ee8")
        self.assertIn("#f04459", style)
        self.assertIn("#397ee8", style)
        self.assertIn("#44f04459", style)
        self.assertNotIn("#f0445930", style)

if __name__ == "__main__":
    unittest.main()
