from pathlib import Path
import unittest

from capital_gains_app.ui_text import ASSISTANT_FONT_FAMILY, app_root, ui_text


class UITextTests(unittest.TestCase):
    def test_hebrew_text_is_wrapped_in_rtl_marks(self) -> None:
        rendered = ui_text("היי ליאת, יש קבצים לניתוח?")

        self.assertEqual(rendered, "\u200Fהיי ליאת, יש קבצים לניתוח?\u200F")
        self.assertEqual(ASSISTANT_FONT_FAMILY, "Assistant")

    def test_mixed_rtl_text_keeps_ltr_terms_readable(self) -> None:
        rendered = ui_text("גררי לכאן קבצי Excel או לחצי על בחירת קבצים")

        self.assertEqual(rendered, "\u200Fגררי לכאן קבצי Excel או לחצי על בחירת קבצים\u200F")

    def test_non_hebrew_lines_are_not_reordered(self) -> None:
        rendered = ui_text("הדוח נשמר:\nC:\\Temp\\fifo_report.xlsx")

        self.assertEqual(rendered.splitlines()[1], "C:\\Temp\\fifo_report.xlsx")

    def test_assistant_font_asset_is_bundled(self) -> None:
        self.assertTrue((app_root() / "assets" / "fonts" / "Assistant.ttf").exists())
        self.assertTrue(Path(app_root()).exists())


if __name__ == "__main__":
    unittest.main()
