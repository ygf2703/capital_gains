from __future__ import annotations

import ctypes
import re
import sys
from pathlib import Path

import customtkinter as ctk


ASSISTANT_FONT_FAMILY = "Assistant"
RTL_MARK = "\u200f"
_FR_PRIVATE = 0x10
_FR_NOT_ENUM = 0x20
_TOKEN_RE = re.compile(r"\S+")
_TRAILING_RTL_PUNCTUATION = ".,:;!?"


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
    return RTL_MARK + "\n".join(_visual_rtl_line(line) if _has_hebrew(line) else line for line in text.split("\n"))


def ui_title(value: object) -> str:
    return ui_text(value)


def ui_font(size: int = 14, weight: str | None = None) -> ctk.CTkFont:
    kwargs = {"family": ASSISTANT_FONT_FAMILY, "size": size}
    if weight:
        kwargs["weight"] = weight
    return ctk.CTkFont(**kwargs)


def _has_hebrew(text: str) -> bool:
    return any("\u0590" <= char <= "\u05ff" for char in text)


def _visual_rtl_line(line: str) -> str:
    tokens = _TOKEN_RE.findall(line)
    if not tokens:
        return line
    return " ".join(_visual_rtl_token(token) for token in reversed(tokens))


def _visual_rtl_token(token: str) -> str:
    if re.fullmatch(r"\d+[.)]", token):
        return token
    moved = ""
    while token and token[-1] in _TRAILING_RTL_PUNCTUATION:
        moved += token[-1]
        token = token[:-1]
    return f"{moved}{token}"
