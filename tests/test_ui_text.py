from pathlib import Path

from capital_gains_app.ui_text import ASSISTANT_FONT_FAMILY, app_root, ui_text


def test_hebrew_text_is_prepared_for_ltr_tk_widgets() -> None:
    rendered = ui_text("היי ליאת, יש קבצים לניתוח?")

    assert rendered == "?היי ליאת, יש קבצים לניתוח"
    assert ASSISTANT_FONT_FAMILY == "Assistant"


def test_mixed_rtl_text_keeps_ltr_terms_readable() -> None:
    rendered = ui_text("גררי לכאן קבצי Excel או לחצי על בחירת קבצים")

    assert rendered == "גררי לכאן קבצי Excel או לחצי על בחירת קבצים"


def test_non_hebrew_lines_are_not_reordered() -> None:
    rendered = ui_text("הדוח נשמר:\nC:\\Temp\\fifo_report.xlsx")

    assert rendered.splitlines()[1] == "C:\\Temp\\fifo_report.xlsx"


def test_assistant_font_asset_is_bundled() -> None:
    assert (app_root() / "assets" / "fonts" / "Assistant.ttf").exists()
    assert Path(app_root()).exists()
