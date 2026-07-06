from __future__ import annotations

import ctypes
import sys
from pathlib import Path

import customtkinter as ctk


ASSISTANT_FONT_FAMILY = "Assistant"
_FR_PRIVATE = 0x10
_FR_NOT_ENUM = 0x20
_RTL_MARK = "\u200F"


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS"))
    return Path(__file__).resolve().parents[1]


def load_assistant_font() -> None:
    font_path = app_root() / "assets" / "fonts" / "Assistant.ttf"
    if not font_path.exists() or sys.platform != "win32":
        return
    try:
        ctypes.windll.gdi32.AddFontResourceExW(str(font_path), _FR_PRIVATE | _FR_NOT_ENUM, 0)
    except Exception:
        # The app can still run with Windows font fallback.
        return


def ui_text(value: object) -> str:
    text = str(value)
    if not _has_hebrew(text):
        return text
    return "\n".join(_prepare_rtl_line(line) if _has_hebrew(line) else line for line in text.split("\n"))


def ui_title(value: object) -> str:
    return ui_text(value)


def ui_font(size: int = 14, weight: str | None = None) -> ctk.CTkFont:
    kwargs = {"family": ASSISTANT_FONT_FAMILY, "size": size}
    if weight:
        kwargs["weight"] = weight
    return ctk.CTkFont(**kwargs)


def _has_hebrew(text: str) -> bool:
    return any("\u0590" <= char <= "\u05ff" for char in text)


def _prepare_rtl_line(line: str) -> str:
    return f"{_RTL_MARK}{line}{_RTL_MARK}"
