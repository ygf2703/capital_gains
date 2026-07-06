from __future__ import annotations

import random
import threading
import tkinter as tk
from datetime import date, datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk

from .application import AnalysisPreparation, CapitalGainsWorkflow, ExportOutcome
from .auth import (
    AuthConfigurationError,
    AuthService,
    AuthSession,
    DuplicateUserError,
    GoogleAuthError,
    InvalidCredentialsError,
    LocalAuthError,
    WeakPasswordError,
)
from .dashboard import build_dashboard_summary
from .exchange_rates import parse_user_date
from .models import CalculationResult, ExchangeRateSnapshot, Transaction, ValidationIssue
from .parsers import HeaderPreview, _normalize_header_text
from .services import save_generic_report_template
from .ui_text import ASSISTANT_FONT_FAMILY, app_root, load_assistant_font, ui_font, ui_text, ui_title
from .user_identity import UserIdentity, greeting_for_user

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except Exception:  # pragma: no cover - optional dependency
    DND_FILES = None
    TkinterDnD = None


PALETTE = {
    "bg": "#05070B",
    "granite": "#08101A",
    "granite_light": "#1A2230",
    "graph_pattern": "#2A3341",
    "panel": "#0F141B",
    "panel_alt": "#0A0F15",
    "panel_glass": "#131A23",
    "mist": "#1A2230",
    "line": "#313B49",
    "text": "#F6F1E8",
    "muted": "#C2B7A6",
    "primary": "#CFA85A",
    "primary_hover": "#E1C57D",
    "primary_border": "#9D7B3B",
    "button_text": "#10151C",
    "secondary": "#1B2736",
    "secondary_hover": "#26384D",
    "secondary_border": "#415066",
    "card_blue": "#102838",
    "card_pink": "#2C1928",
    "card_yellow": "#372E16",
    "card_silver": "#17202C",
    "chart_white": "#FFFFFF",
    "chart_blue": "#8FD8FF",
    "chart_pink": "#FF8FB8",
    "chart_yellow": "#FFE27A",
    "warning": "#FFE27A",
    "negative": "#FF8FB8",
    "positive": "#8FD8FF",
}
CHART_COLORS = [PALETTE["chart_white"], PALETTE["chart_blue"], PALETTE["chart_pink"], PALETTE["chart_yellow"]]


if TkinterDnD is not None:

    class BaseWindow(ctk.CTk, TkinterDnD.DnDWrapper):  # type: ignore[misc]
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)
            self.TkdndVersion = TkinterDnD._require(self)

else:
    BaseWindow = ctk.CTk


class GraniteBackground(tk.Canvas):
    def __init__(self, parent) -> None:
        super().__init__(parent, highlightthickness=0, bd=0, bg=PALETTE["bg"])
        self.bind("<Configure>", self._redraw)

    def _redraw(self, _event=None) -> None:
        width = max(self.winfo_width(), 1)
        height = max(self.winfo_height(), 1)
        self.delete("all")
        self.create_rectangle(0, 0, width, height, fill=PALETTE["bg"], outline="")

        rng = random.Random(2703)
        for _ in range(max(120, width * height // 5200)):
            x = rng.randrange(0, width)
            y = rng.randrange(0, height)
            shade = rng.choice(["#14171A", "#1C2024", "#272B30", "#343941"])
            size = rng.choice([1, 1, 1, 2])
            self.create_oval(x, y, x + size, y + size, fill=shade, outline="")

        for _ in range(34):
            x = rng.randrange(-80, width)
            y = rng.randrange(0, height)
            length = rng.randrange(70, 190)
            color = rng.choice(["#1B1F24", "#242930", "#303640"])
            self.create_line(x, y, x + length, y - rng.randrange(8, 34), fill=color, width=1)

        for band in range(5):
            base_y = height - 90 - band * 76
            points: list[int] = []
            for step in range(8):
                x = 40 + step * max(90, width // 8)
                y = base_y - step * 18 + rng.randrange(-24, 25)
                points.extend([x, y])
            self.create_line(*points, fill=PALETTE["graph_pattern"], width=2, smooth=True, dash=(7, 8))

        for index in range(9):
            x0 = width - 60 - index * 44
            h = 34 + index * 17
            self.create_rectangle(x0, height - 42 - h, x0 + 16, height - 42, fill="#181C21", outline="")


class CapitalGainsApp(BaseWindow):
    def __init__(self) -> None:
        super().__init__()
        load_assistant_font()
        self.title(ui_title("ניתוח רווחי הון - פיפו"))
        self.geometry("1180x760")
        self.minsize(1020, 680)
        self.configure(fg_color=PALETTE["bg"])
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")
        self.background = GraniteBackground(self)
        self.background.place(x=0, y=0, relwidth=1, relheight=1)
        self.background.tk.call("lower", self.background._w)

        self.workflow = CapitalGainsWorkflow()
        self.exchange_date_var = tk.StringVar(value=date.today().isoformat())
        self.kpi_labels: dict[str, ctk.CTkLabel] = {}
        self.dashboard_meta_labels: dict[str, ctk.CTkLabel] = {}
        self.insight_labels: list[ctk.CTkLabel] = []
        self.greeting_label: ctk.CTkLabel | None = None
        self.profile_label: ctk.CTkLabel | None = None
        self.auth_hint_label: ctk.CTkLabel | None = None
        self.auth_button: ctk.CTkButton | None = None
        self.dashboard_note_label: ctk.CTkLabel | None = None
        self.question_var = tk.StringVar()
        self.chat_box: ctk.CTkTextbox | None = None
        self.login_dialog: LoginDialog | None = None

        self._build_ui()

    @property
    def files(self) -> list[Path]:
        return self.workflow.state.files

    @property
    def last_result(self) -> CalculationResult | None:
        return self.workflow.state.result

    @last_result.setter
    def last_result(self, value: CalculationResult | None) -> None:
        self.workflow.state.result = value

    @property
    def last_exchange_rate(self) -> ExchangeRateSnapshot | None:
        return self.workflow.state.exchange_rate

    @last_exchange_rate.setter
    def last_exchange_rate(self, value: ExchangeRateSnapshot | None) -> None:
        self.workflow.state.exchange_rate = value

    @property
    def auth_session(self) -> AuthSession:
        return self.workflow.state.auth_session

    @auth_session.setter
    def auth_session(self, value: AuthSession) -> None:
        self.workflow.state.auth_session = value

    @property
    def user_identity(self) -> UserIdentity:
        return self.workflow.state.user_identity

    @user_identity.setter
    def user_identity(self, value: UserIdentity) -> None:
        self.workflow.state.user_identity = value

    @property
    def auth_service(self) -> AuthService:
        return self.workflow.auth_service

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        header = ctk.CTkFrame(self, corner_radius=0, fg_color=PALETTE["panel_alt"])
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        self.greeting_label = ctk.CTkLabel(
            header,
            text=ui_text(greeting_for_user(self.user_identity)),
            font=ui_font(28, "bold"),
            text_color=PALETTE["text"],
            anchor="e",
        )
        self.greeting_label.grid(row=0, column=0, padx=28, pady=(20, 4), sticky="ew")
        ctk.CTkLabel(
            header,
            text=ui_text("מחשבון פיפו מקומי לדוחות אגיס ולאומי, עם דשבורד וייצוא אקסל"),
            font=ui_font(15),
            text_color=PALETTE["muted"],
            anchor="e",
        ).grid(row=1, column=0, padx=28, pady=(0, 18), sticky="ew")

        auth_frame = ctk.CTkFrame(
            header,
            corner_radius=8,
            fg_color=PALETTE["panel_glass"],
            border_width=1,
            border_color=PALETTE["primary_border"],
        )
        auth_frame.grid(row=0, column=1, rowspan=2, padx=(0, 28), pady=18, sticky="e")
        auth_frame.grid_columnconfigure(0, weight=1)

        self.profile_label = ctk.CTkLabel(
            auth_frame,
            text="",
            font=ui_font(13, "bold"),
            text_color=PALETTE["text"],
            anchor="e",
        )
        self.profile_label.grid(row=0, column=0, padx=14, pady=(10, 2), sticky="ew")

        self.auth_hint_label = ctk.CTkLabel(
            auth_frame,
            text="",
            font=ui_font(11),
            text_color=PALETTE["muted"],
            anchor="e",
            justify="right",
            wraplength=260,
        )
        self.auth_hint_label.grid(row=1, column=0, padx=14, pady=(0, 10), sticky="ew")

        self.auth_button = self._button(auth_frame, "התחברות", self.toggle_auth_session, width=164)
        self.auth_button.grid(row=2, column=0, padx=14, pady=(0, 12), sticky="e")

        toolbar = ctk.CTkFrame(
            self,
            corner_radius=10,
            fg_color=PALETTE["panel_glass"],
            border_width=1,
            border_color=PALETTE["primary_border"],
        )
        toolbar.grid(row=1, column=0, padx=18, pady=14, sticky="ew")
        toolbar.grid_columnconfigure(4, weight=1)

        self._button(toolbar, "בחר קבצים", self.add_files).grid(row=0, column=0, padx=(12, 8), pady=12)
        self._button(toolbar, "נקה", self.clear_files, fg_color=PALETTE["secondary"]).grid(row=0, column=1, padx=8, pady=12)
        self._button(toolbar, "צור קובץ אקסל", self.calculate_and_export).grid(row=0, column=2, padx=8, pady=12)
        self._button(toolbar, "התאמת עמודות", self.configure_columns, fg_color=PALETTE["secondary"], width=132).grid(
            row=0, column=3, padx=8, pady=12
        )

        exchange_box = ctk.CTkFrame(toolbar, corner_radius=8, fg_color=PALETTE["mist"])
        exchange_box.grid(row=0, column=5, padx=12, pady=10, sticky="e")
        ctk.CTkLabel(
            exchange_box,
            text=ui_text("תאריך מבוקש"),
            font=ui_font(13),
            text_color=PALETTE["muted"],
            anchor="e",
        ).grid(
            row=0, column=0, padx=(12, 6), pady=8
        )
        self.exchange_date_entry = ctk.CTkEntry(
            exchange_box,
            width=116,
            textvariable=self.exchange_date_var,
            fg_color=PALETTE["panel"],
            border_color=PALETTE["line"],
            text_color=PALETTE["text"],
            justify="right",
            font=ui_font(13),
        )
        self.exchange_date_entry.grid(row=0, column=1, padx=6, pady=8)
        self._button(exchange_box, "שער דולר", self.fetch_exchange_rate, width=92).grid(
            row=0, column=2, padx=(6, 12), pady=8
        )

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=2, column=0, padx=18, pady=(0, 14), sticky="nsew")
        body.grid_columnconfigure(0, weight=3)
        body.grid_columnconfigure(1, weight=2)
        body.grid_rowconfigure(0, weight=1)

        self._build_file_panel(body)
        self._build_dashboard_panel(body)

        bottom = ctk.CTkFrame(self, corner_radius=8, fg_color=PALETTE["panel_glass"], border_width=1, border_color=PALETTE["line"])
        bottom.grid(row=3, column=0, padx=18, pady=(0, 18), sticky="ew")
        bottom.grid_columnconfigure(0, weight=1)
        self.status = ctk.CTkLabel(
            bottom,
            text=ui_text("מוכן"),
            font=ui_font(13),
            text_color=PALETTE["muted"],
            anchor="e",
            justify="right",
        )
        self.status.grid(row=0, column=0, padx=14, pady=10, sticky="ew")

        self._refresh_identity_ui()
        self.after(200, self._draw_empty_dashboard)
        self.after(80, self._require_authentication)

    def _build_file_panel(self, parent: ctk.CTkFrame) -> None:
        panel = ctk.CTkFrame(parent, corner_radius=10, fg_color=PALETTE["panel"], border_width=1, border_color=PALETTE["line"])
        panel.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        panel.grid_rowconfigure(3, weight=1)
        panel.grid_rowconfigure(6, weight=1)
        panel.grid_columnconfigure(0, weight=1)

        label_text = "גרור לכאן קבצי אקסל או לחץ על בחירת קבצים"
        if DND_FILES is None:
            label_text = "בחר דוחות אקסל לניתוח"
        ctk.CTkLabel(
            panel,
            text=ui_text(label_text),
            font=ui_font(18, "bold"),
            text_color=PALETTE["text"],
            anchor="e",
        ).grid(row=0, column=0, padx=20, pady=(20, 4), sticky="ew")
        ctk.CTkLabel(
            panel,
            text=ui_text("הדוחות נשארים מקומית במחשב. קבצי מקור לא נדחפים לגיט."),
            font=ui_font(13),
            text_color=PALETTE["muted"],
            anchor="e",
        ).grid(row=1, column=0, padx=20, pady=(0, 14), sticky="ew")
        ctk.CTkLabel(
            panel,
            text=ui_text("אפשר לנתח גם קובץ יחיד של נייר ערך אחד, והייצוא יישאר זמין."),
            font=ui_font(13),
            text_color=PALETTE["muted"],
            anchor="e",
        ).grid(row=2, column=0, padx=20, pady=(0, 8), sticky="ew")

        drop_frame = ctk.CTkFrame(panel, border_width=1, border_color=PALETTE["primary_border"], corner_radius=10, fg_color=PALETTE["panel_alt"])
        drop_frame.grid(row=3, column=0, padx=20, pady=(0, 20), sticky="nsew")
        drop_frame.grid_columnconfigure(0, weight=1)
        drop_frame.grid_rowconfigure(0, weight=1)

        self.file_list = tk.Listbox(
            drop_frame,
            height=10,
            activestyle="none",
            bg=PALETTE["panel_alt"],
            fg=PALETTE["text"],
            highlightthickness=0,
            borderwidth=0,
            selectbackground="#233243",
            selectforeground=PALETTE["chart_white"],
            font=(ASSISTANT_FONT_FAMILY, 11),
        )
        self.file_list.grid(row=0, column=0, padx=14, pady=14, sticky="nsew")

        if DND_FILES is not None:
            drop_frame.drop_target_register(DND_FILES)
            drop_frame.dnd_bind("<<Drop>>", self._on_drop)
            panel.drop_target_register(DND_FILES)
            panel.dnd_bind("<<Drop>>", self._on_drop)

        self.exchange_status = ctk.CTkLabel(
            panel,
            text=ui_text("שער דולר: טרם נטען"),
            font=ui_font(13),
            text_color=PALETTE["muted"],
            anchor="e",
        )
        self.exchange_status.grid(row=4, column=0, padx=20, pady=(0, 18), sticky="ew")

        ctk.CTkLabel(
            panel,
            text=ui_text("שאל את הדוח"),
            font=ui_font(16, "bold"),
            text_color=PALETTE["text"],
            anchor="e",
        ).grid(row=5, column=0, padx=20, pady=(0, 6), sticky="ew")

        chat_frame = ctk.CTkFrame(panel, corner_radius=10, fg_color=PALETTE["panel_alt"], border_width=1, border_color=PALETTE["line"])
        chat_frame.grid(row=6, column=0, padx=20, pady=(0, 20), sticky="nsew")
        chat_frame.grid_columnconfigure(0, weight=1)
        chat_frame.grid_rowconfigure(0, weight=1)

        self.chat_box = ctk.CTkTextbox(
            chat_frame,
            fg_color=PALETTE["panel_alt"],
            text_color=PALETTE["text"],
            border_width=0,
            font=ui_font(12),
            wrap="word",
        )
        self.chat_box.grid(row=0, column=0, columnspan=2, padx=12, pady=(12, 8), sticky="nsew")
        self.chat_box.insert("1.0", ui_text("אחרי ניתוח הקובץ אפשר לשאול כאן על רווחים, תנועות, פוזיציות פתוחות, התראות ושער הדולר."))
        self.chat_box.configure(state="disabled")

        question_entry = ctk.CTkEntry(
            chat_frame,
            textvariable=self.question_var,
            placeholder_text=ui_text("למשל: כמה תנועות יש בקובץ?"),
            border_color=PALETTE["line"],
            justify="right",
            font=ui_font(12),
        )
        question_entry.grid(row=1, column=0, padx=(12, 8), pady=(0, 12), sticky="ew")
        question_entry.bind("<Return>", lambda _event: self.ask_report_question())
        self._button(chat_frame, "שאל", self.ask_report_question, width=84).grid(row=1, column=1, padx=(0, 12), pady=(0, 12))

        suggestions = ctk.CTkFrame(chat_frame, fg_color="transparent")
        suggestions.grid(row=2, column=0, columnspan=2, padx=12, pady=(0, 12), sticky="ew")
        suggestions.grid_columnconfigure((0, 1, 2), weight=1)
        self._button(
            suggestions,
            "מה הרווח הכולל?",
            lambda: self._ask_suggested_question("מה הרווח הכולל?"),
            fg_color=PALETTE["secondary"],
            width=140,
        ).grid(row=0, column=0, padx=(0, 6), sticky="ew")
        self._button(
            suggestions,
            "מה הנייר הכי בולט?",
            lambda: self._ask_suggested_question("מה הנייר הכי בולט בדוח?"),
            fg_color=PALETTE["secondary"],
            width=140,
        ).grid(row=0, column=1, padx=6, sticky="ew")
        self._button(
            suggestions,
            "מה פתוח כרגע?",
            lambda: self._ask_suggested_question("מה הפוזיציות הפתוחות?"),
            fg_color=PALETTE["secondary"],
            width=140,
        ).grid(row=0, column=2, padx=(6, 0), sticky="ew")

    def _build_dashboard_panel(self, parent: ctk.CTkFrame) -> None:
        dashboard = ctk.CTkScrollableFrame(parent, corner_radius=10, fg_color=PALETTE["panel"], border_width=1, border_color=PALETTE["line"])
        dashboard.grid(row=0, column=1, sticky="nsew")
        dashboard.grid_columnconfigure((0, 1), weight=1)
        dashboard.grid_rowconfigure(7, weight=1)

        hero = ctk.CTkFrame(
            dashboard,
            corner_radius=10,
            fg_color=PALETTE["panel_alt"],
            border_width=1,
            border_color=PALETTE["primary_border"],
        )
        hero.grid(row=0, column=0, columnspan=2, padx=16, pady=(16, 10), sticky="ew")
        hero.grid_columnconfigure((0, 1, 2), weight=1)
        ctk.CTkLabel(
            hero,
            text=ui_text("דשבורד"),
            font=ui_font(21, "bold"),
            text_color=PALETTE["text"],
            anchor="e",
        ).grid(row=0, column=0, columnspan=3, padx=16, pady=(14, 2), sticky="ew")
        ctk.CTkLabel(
            hero,
            text=ui_text("תמונת מצב מהירה של הדוח, החריגים והחשיפות הפעילות."),
            font=ui_font(12),
            text_color=PALETTE["muted"],
            anchor="e",
        ).grid(row=1, column=0, columnspan=3, padx=16, pady=(0, 12), sticky="ew")

        meta_cards = [
            ("open_lots", "פוזיציות פתוחות"),
            ("corporate_actions", "אירועי הון"),
            ("inferred_rows", "שורות עם אומדן"),
        ]
        for index, (key, title) in enumerate(meta_cards):
            card = ctk.CTkFrame(hero, corner_radius=8, fg_color=PALETTE["panel_glass"], border_width=1, border_color=PALETTE["line"])
            card.grid(row=2, column=index, padx=(16 if index == 0 else 6, 16 if index == 2 else 6), pady=(0, 12), sticky="ew")
            ctk.CTkLabel(
                card,
                text=ui_text(title),
                font=ui_font(11),
                text_color=PALETTE["muted"],
                anchor="e",
            ).pack(fill="x", padx=12, pady=(9, 0))
            value_label = ctk.CTkLabel(
                card,
                text="-",
                font=ui_font(18, "bold"),
                text_color=PALETTE["text"],
                anchor="e",
            )
            value_label.pack(fill="x", padx=12, pady=(0, 8))
            self.dashboard_meta_labels[key] = value_label

        self.dashboard_note_label = ctk.CTkLabel(
            hero,
            text=ui_text("לאחר טעינת קובץ יוצגו כאן ריכוזים, חריגים ומדדי עומק לחישוב."),
            font=ui_font(12),
            text_color=PALETTE["muted"],
            anchor="e",
            justify="right",
            wraplength=360,
        )
        self.dashboard_note_label.grid(row=3, column=0, columnspan=3, padx=16, pady=(0, 14), sticky="ew")

        cards = [
            ("transactions", "תנועות", PALETTE["card_blue"]),
            ("securities", "ניירות", PALETTE["card_silver"]),
            ("realized", "שורות פיפו", PALETTE["card_pink"]),
            ("issues", "התראות", PALETTE["card_yellow"]),
        ]
        for index, (key, title, color) in enumerate(cards):
            card = ctk.CTkFrame(dashboard, corner_radius=10, fg_color=color, border_width=1, border_color=PALETTE["line"])
            card.grid(row=1 + index // 2, column=index % 2, padx=10, pady=8, sticky="ew")
            ctk.CTkLabel(card, text=ui_text(title), font=ui_font(12), text_color=PALETTE["muted"], anchor="e").pack(
                fill="x", padx=14, pady=(12, 2)
            )
            value_label = ctk.CTkLabel(
                card,
                text="-",
                font=ui_font(25, "bold"),
                text_color=PALETTE["text"],
                anchor="e",
            )
            value_label.pack(fill="x", padx=14, pady=(0, 2))
            ctk.CTkLabel(
                card,
                text=ui_text("מדד מרכזי לניתוח הנוכחי"),
                font=ui_font(10),
                text_color=PALETTE["muted"],
                anchor="e",
            ).pack(fill="x", padx=14, pady=(0, 12))
            self.kpi_labels[key] = value_label

        insights_frame = ctk.CTkFrame(
            dashboard,
            corner_radius=10,
            fg_color=PALETTE["panel_alt"],
            border_width=1,
            border_color=PALETTE["line"],
        )
        insights_frame.grid(row=3, column=0, columnspan=2, padx=16, pady=(10, 6), sticky="ew")
        insights_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            insights_frame,
            text=ui_text("תובנות מרכזיות"),
            font=ui_font(16, "bold"),
            text_color=PALETTE["text"],
            anchor="e",
        ).grid(row=0, column=0, padx=14, pady=(12, 2), sticky="ew")
        ctk.CTkLabel(
            insights_frame,
            text=ui_text("המערכת מסכמת את עיקרי התמונה העסקית והחשבונאית מתוך הקובץ."),
            font=ui_font(11),
            text_color=PALETTE["muted"],
            anchor="e",
        ).grid(row=1, column=0, padx=14, pady=(0, 10), sticky="ew")
        for index in range(5):
            row = ctk.CTkFrame(insights_frame, fg_color=PALETTE["panel_glass"], corner_radius=8)
            row.grid(row=index + 2, column=0, padx=12, pady=(0, 6), sticky="ew")
            row.grid_columnconfigure(0, weight=1)
            label = ctk.CTkLabel(
                row,
                text=ui_text("התובנות יופיעו אחרי החישוב"),
                font=ui_font(13),
                text_color=PALETTE["muted"],
                anchor="e",
                justify="right",
                wraplength=320,
            )
            label.grid(row=0, column=0, padx=(12, 6), pady=10, sticky="ew")
            ctk.CTkLabel(
                row,
                text=f"{index + 1}.",
                font=ui_font(13),
                text_color=PALETTE["primary_hover"],
                anchor="e",
                width=26,
            ).grid(row=0, column=1, padx=(6, 12), pady=10, sticky="e")
            self.insight_labels.append(label)

        gain_frame = ctk.CTkFrame(
            dashboard,
            corner_radius=10,
            fg_color=PALETTE["panel_alt"],
            border_width=1,
            border_color=PALETTE["line"],
        )
        gain_frame.grid(row=4, column=0, columnspan=2, padx=16, pady=(10, 6), sticky="ew")
        ctk.CTkLabel(
            gain_frame,
            text=ui_text("רווח והפסד לפי נייר"),
            font=ui_font(15, "bold"),
            text_color=PALETTE["text"],
            anchor="e",
        ).pack(fill="x", padx=14, pady=(12, 0))
        ctk.CTkLabel(
            gain_frame,
            text=ui_text("הצגה של הניירות בעלי ההשפעה הגבוהה ביותר על התוצאה."),
            font=ui_font(11),
            text_color=PALETTE["muted"],
            anchor="e",
        ).pack(fill="x", padx=14, pady=(0, 8))
        self.gain_canvas = tk.Canvas(
            gain_frame,
            width=420,
            height=190,
            bg=PALETTE["panel_alt"],
            highlightthickness=0,
        )
        self.gain_canvas.pack(fill="x", padx=12, pady=(0, 12))

        action_frame = ctk.CTkFrame(
            dashboard,
            corner_radius=10,
            fg_color=PALETTE["panel_alt"],
            border_width=1,
            border_color=PALETTE["line"],
        )
        action_frame.grid(row=5, column=0, columnspan=2, padx=16, pady=(6, 16), sticky="nsew")
        ctk.CTkLabel(
            action_frame,
            text=ui_text("פילוח פעולות"),
            font=ui_font(15, "bold"),
            text_color=PALETTE["text"],
            anchor="e",
        ).pack(fill="x", padx=14, pady=(12, 0))
        ctk.CTkLabel(
            action_frame,
            text=ui_text("התפלגות הקניות, המכירות ושאר הפעולות שנקלטו מהדוח."),
            font=ui_font(11),
            text_color=PALETTE["muted"],
            anchor="e",
        ).pack(fill="x", padx=14, pady=(0, 8))
        self.action_canvas = tk.Canvas(
            action_frame,
            width=420,
            height=190,
            bg=PALETTE["panel_alt"],
            highlightthickness=0,
        )
        self.action_canvas.pack(fill="x", padx=12, pady=(0, 12))

    def _button(self, parent, text: str, command, fg_color: str | None = None, width: int = 120) -> ctk.CTkButton:
        is_secondary = fg_color == PALETTE["secondary"]
        return ctk.CTkButton(
            parent,
            text=ui_text(text),
            font=ui_font(14, "bold"),
            width=width,
            command=command,
            fg_color=fg_color or PALETTE["primary"],
            hover_color=PALETTE["secondary_hover"] if is_secondary else PALETTE["primary_hover"],
            text_color=PALETTE["text"] if is_secondary else PALETTE["button_text"],
            corner_radius=8,
            border_width=1,
            border_color=PALETTE["secondary_border"] if is_secondary else PALETTE["primary_border"],
        )

    def _refresh_identity_ui(self) -> None:
        if self.greeting_label is not None:
            self.greeting_label.configure(text=ui_text(greeting_for_user(self.user_identity)))

        if self.profile_label is None or self.auth_hint_label is None or self.auth_button is None:
            return

        if self.auth_session.connected and self.auth_session.email:
            profile_text = self.auth_session.email
            provider_label = "Google" if self.auth_session.provider == "google" else "אימייל וסיסמה"
            hint_text = f"מחוברת דרך {provider_label}. הקבצים והניתוחים נשארים מקומיים על המחשב."
            button_text = "התנתקות"
        else:
            profile_text = "נדרש חיבור משתמש"
            if self.auth_service.has_google_configuration():
                hint_text = "אפשר להתחבר עם אימייל וסיסמה או עם Google לפני שימוש באפליקציה."
            else:
                hint_text = "אפשר להתחבר עם אימייל וסיסמה. חיבור Google זמין אחרי הגדרת client secret."
            button_text = "התחברות / הרשמה"

        self.profile_label.configure(text=ui_text(profile_text))
        self.auth_hint_label.configure(text=ui_text(hint_text))
        self.auth_button.configure(text=ui_text(button_text), state="normal")

    def _require_authentication(self) -> None:
        if self.auth_session.connected:
            return
        if self.login_dialog is not None and self.login_dialog.winfo_exists():
            self.login_dialog.lift()
            return
        self.login_dialog = LoginDialog(self)

    def toggle_auth_session(self) -> None:
        if self.auth_session.connected and self.auth_session.email:
            self.workflow.sign_out()
            self.status.configure(text=ui_text("ההתנתקות הושלמה"))
            self._refresh_identity_ui()
            self._require_authentication()
            return

        self._require_authentication()

    def _apply_auth_session(self, session: AuthSession) -> None:
        self.auth_session = session
        self.user_identity = session.identity if session.email else self.workflow.state.user_identity
        provider_label = "Google" if session.provider == "google" else "אימייל"
        self.status.configure(text=ui_text(f"התחברות דרך {provider_label} הושלמה"))
        if self.login_dialog is not None and self.login_dialog.winfo_exists():
            self.login_dialog.destroy()
        self.login_dialog = None
        self._refresh_identity_ui()

    def configure_columns(self) -> None:
        if not self.files:
            messagebox.showwarning(ui_title("אין קבצים"), ui_text("בחר קודם קובץ אקסל אחד לפחות."))
            return
        previews = self.workflow.preview_current_headers()
        if not previews:
            messagebox.showwarning(ui_title("לא נמצאו כותרות"), ui_text("לא הצלחתי למצוא שורת כותרות מתאימה בקבצים שנבחרו."))
            return
        dialog = MappingTemplateDialog(self, previews[0])
        self.wait_window(dialog)
        if dialog.saved:
            self.status.configure(text=ui_text("תבנית עמודות נשמרה. אפשר להריץ שוב את הניתוח."))

    def ask_report_question(self) -> None:
        question = self.question_var.get().strip()
        if not question:
            return
        answer = self.workflow.answer_question(question)
        self._append_chat_entry("שאלה", question)
        self._append_chat_entry("תשובה", answer)
        self.question_var.set("")

    def _ask_suggested_question(self, question: str) -> None:
        self.question_var.set(question)
        self.ask_report_question()

    def _append_chat_entry(self, role: str, text: str) -> None:
        if self.chat_box is None:
            return
        self.chat_box.configure(state="normal")
        if self.chat_box.get("1.0", "end-1c").strip():
            self.chat_box.insert("end", "\n\n")
        self.chat_box.insert("end", ui_text(f"{role}: {text}"))
        self.chat_box.see("end")
        self.chat_box.configure(state="disabled")

    def add_files(self) -> None:
        selected = filedialog.askopenfilenames(
            title=ui_title("בחר דוחות אקסל"),
            filetypes=[("קבצי אקסל", "*.xlsx *.xlsm *.xls"), ("כל הקבצים", "*.*")],
        )
        self._add_paths(selected)

    def clear_files(self) -> None:
        self.workflow.clear_files()
        self.file_list.delete(0, tk.END)
        self.status.configure(text=ui_text("הרשימה נוקתה"))
        self._draw_empty_dashboard()

    def fetch_exchange_rate(self) -> None:
        try:
            requested_date = parse_user_date(self.exchange_date_var.get())
        except ValueError as exc:
            messagebox.showwarning(ui_title("תאריך לא תקין"), ui_text(str(exc)))
            return
        self.exchange_status.configure(text=ui_text("טוען שער יציג מבנק ישראל..."))
        self.status.configure(text=ui_text("טוען שער דולר מבנק ישראל"))
        threading.Thread(target=self._exchange_worker, args=(requested_date,), daemon=True).start()

    def _exchange_worker(self, requested_date: date) -> None:
        try:
            rate = self.workflow.fetch_exchange_rate(requested_date)
            self.after(0, lambda: self._set_exchange_rate(rate))
        except Exception as exc:  # pragma: no cover - network boundary
            error = str(exc)
            self.after(0, lambda: self._set_exchange_error(error))

    def _set_exchange_rate(self, rate: ExchangeRateSnapshot) -> None:
        self.last_exchange_rate = rate
        note = f"שער דולר ל-{rate.published_date:%Y-%m-%d}: {rate.rate:.4f}"
        if rate.published_date != rate.lookup_date:
            note += f" (תאריך יעד: {rate.lookup_date:%Y-%m-%d})"
        self.exchange_status.configure(text=ui_text(note), text_color=PALETTE["primary_hover"])
        self.status.configure(text=ui_text("שער הדולר נטען מבנק ישראל"))

    def _set_exchange_error(self, error: str) -> None:
        self.exchange_status.configure(text=ui_text(f"לא ניתן לטעון שער דולר: {error}"), text_color=PALETTE["warning"])
        self.status.configure(text=ui_text("טעינת שער הדולר נכשלה"))

    def _on_drop(self, event) -> None:
        paths = self.tk.splitlist(event.data)
        self._add_paths(paths)

    def _add_paths(self, paths) -> None:
        added = self.workflow.add_files(list(paths))
        for path in added:
            self.file_list.insert(tk.END, ui_text(path.name))
        self.status.configure(text=ui_text(f"{len(self.files)} קבצים ברשימה"))

    def calculate_and_export(self) -> None:
        if not self.files:
            messagebox.showwarning(ui_title("אין קבצים"), ui_text("בחר לפחות קובץ אקסל אחד."))
            return
        try:
            preparation = self.workflow.prepare_analysis(self.exchange_date_var.get())
            transactions, issues = preparation.transactions, preparation.issues
        except Exception as exc:
            messagebox.showerror(ui_title("שגיאה בקריאת הקבצים"), ui_text(str(exc)))
            self.status.configure(text=ui_text("שגיאה בקריאת הקבצים"))
            return

        unsupported_headers = preparation.unsupported_headers
        if unsupported_headers:
            matching_previews = preparation.previews
            preview = next(
                (
                    item
                    for item in matching_previews
                    if item.source_file == unsupported_headers[0].source_file and item.sheet == unsupported_headers[0].sheet
                ),
                matching_previews[0] if matching_previews else None,
            )
            if preview is not None:
                dialog = MappingTemplateDialog(self, preview)
                self.wait_window(dialog)
                if dialog.saved:
                    self.status.configure(text=ui_text("נשמרה תבנית חדשה. מריץ שוב את הניתוח עם המיפוי המעודכן..."))
                    self.calculate_and_export()
                    return
            messagebox.showwarning(
                ui_title("כותרות לא מזוהות"),
                ui_text("לא זוהתה שורת כותרות נתמכת. אפשר להשתמש ב'התאמת עמודות' כדי ללמד את המערכת את הדוח."),
            )
            self.status.configure(text=ui_text("נדרש מיפוי עמודות לדוח החדש"))
            return

        serious = [issue for issue in issues if issue.severity == "error"]
        if serious:
            dialog = CorrectionsDialog(self, transactions, serious)
            self.wait_window(dialog)
            if not dialog.confirmed:
                self.status.configure(text=ui_text("החישוב בוטל עד לתיקון הנתונים"))
                return
            corrected_keys = set(dialog.corrections)
            _apply_corrections(transactions, dialog.corrections)
            issues = [
                issue
                for issue in issues
                if (issue.source_file, issue.sheet, issue.row_number, issue.field) not in corrected_keys
            ]
            unresolved = [issue for issue in issues if issue.severity == "error"]
            if unresolved:
                messagebox.showwarning(ui_title("נותרו שגיאות"), ui_text("לא כל שורות השגיאה תוקנו. החישוב נעצר."))
                self.status.configure(text=ui_text("נותרו שגיאות לתיקון"))
                return

        output = filedialog.asksaveasfilename(
            title=ui_title("שמרי דוח פיפו"),
            defaultextension=".xlsx",
            initialfile=f"fifo_report_{datetime.now():%Y%m%d_%H%M}.xlsx",
            filetypes=[("חוברת אקסל", "*.xlsx")],
        )
        if not output:
            return

        self.status.configure(text=ui_text("מחשב פיפו, מושך שער דולר ומייצא דוח..."))
        threading.Thread(
            target=self._calculate_worker,
            args=(transactions, issues, output, preparation.requested_date),
            daemon=True,
        ).start()

    def _calculate_worker(
        self,
        transactions: list[Transaction],
        issues: list[ValidationIssue],
        output: str,
        requested_date: date,
    ) -> None:
        try:
            outcome = self.workflow.export(transactions, issues, output, requested_date)
            self.after(0, lambda: self._done(outcome))
        except Exception as exc:  # pragma: no cover - GUI boundary
            error = str(exc)
            self.after(0, lambda: messagebox.showerror(ui_title("שגיאה"), ui_text(error)))
            self.after(0, lambda: self.status.configure(text=ui_text("שגיאה בחישוב")))

    def _done(self, outcome: ExportOutcome) -> None:
        path = outcome.output_path
        result = outcome.result
        exchange_error = outcome.exchange_error
        self.last_result = result
        if result.exchange_rate:
            self.last_exchange_rate = result.exchange_rate
            self._set_exchange_rate(result.exchange_rate)
        self._update_dashboard(result)
        self.status.configure(text=ui_text(f"הדוח נשמר: {path}"))
        self._append_chat_entry("מערכת", "הניתוח הושלם. אפשר לשאול עכשיו שאלות על הדוח באזור השיחה.")
        extra = f"\nשער דולר: {result.exchange_rate.rate:.4f}" if result.exchange_rate else ""
        if exchange_error:
            extra += f"\nלא נטען שער דולר: {exchange_error}"
        messagebox.showinfo(
            ui_title("הסתיים"),
            ui_text(f"הדוח נוצר בהצלחה.\nשורות פיפו: {len(result.realized)}\nהתראות: {len(result.issues)}{extra}\n\n{path}"),
        )

    def _update_dashboard(self, result: CalculationResult) -> None:
        summary = build_dashboard_summary(result)
        self.kpi_labels["transactions"].configure(text=f"{summary.total_transactions:,}")
        self.kpi_labels["securities"].configure(text=f"{summary.unique_securities:,}")
        self.kpi_labels["realized"].configure(text=f"{summary.realized_rows:,}")
        self.kpi_labels["issues"].configure(text=f"{summary.issue_count:,}")
        self.dashboard_meta_labels["open_lots"].configure(text=f"{summary.open_lots:,}")
        self.dashboard_meta_labels["corporate_actions"].configure(text=f"{summary.corporate_actions:,}")
        self.dashboard_meta_labels["inferred_rows"].configure(text=f"{summary.inferred_rows:,}")
        if self.dashboard_note_label is not None:
            note = (
                f"הדוח כולל {summary.total_transactions:,} תנועות, "
                f"{summary.unique_securities:,} ניירות ו-{summary.open_lots:,} פוזיציות פתוחות."
            )
            self.dashboard_note_label.configure(text=ui_text(note))
        for index, label in enumerate(self.insight_labels):
            insight = summary.key_insights[index] if index < len(summary.key_insights) else ""
            label.configure(text=ui_text(insight) if insight else "")
        self._draw_gain_chart(summary.top_securities)
        self._draw_action_chart(summary.action_counts)

    def _draw_empty_dashboard(self) -> None:
        for label in self.kpi_labels.values():
            label.configure(text="-")
        for label in self.dashboard_meta_labels.values():
            label.configure(text="-")
        if self.dashboard_note_label is not None:
            self.dashboard_note_label.configure(text=ui_text("לאחר טעינת קובץ יוצגו כאן ריכוזים, חריגים ומדדי עומק לחישוב."))
        for label in self.insight_labels:
            label.configure(text=ui_text("התובנות יופיעו אחרי החישוב"))
        self._draw_gain_chart([])
        self._draw_action_chart([])

    def _draw_gain_chart(self, rows: list[tuple[str, str, float]]) -> None:
        canvas = self.gain_canvas
        canvas.delete("all")
        width = max(canvas.winfo_width(), 420)
        height = max(canvas.winfo_height(), 190)
        if not rows:
            canvas.create_text(
                width / 2,
                height / 2,
                text=ui_text("אין עדיין נתוני חישוב"),
                fill=PALETTE["muted"],
                font=(ASSISTANT_FONT_FAMILY, 12),
            )
            return

        rows = rows[:6]
        values = [value for _, _, value in rows]
        max_abs = max(abs(value) for value in values) or 1
        chart_left = 24
        chart_right = width - 24
        baseline = 106
        bar_area = chart_right - chart_left
        step = bar_area / len(rows)

        canvas.create_line(chart_left, baseline, chart_right, baseline, fill=PALETTE["line"])
        for index, (label, currency, value) in enumerate(rows):
            bar_width = min(34, step * 0.48)
            center = chart_left + step * index + step / 2
            bar_height = max(4, abs(value) / max_abs * 58)
            y0 = baseline - bar_height if value >= 0 else baseline
            y1 = baseline if value >= 0 else baseline + bar_height
            color = PALETTE["chart_blue"] if value >= 0 else PALETTE["chart_pink"]
            if index % 4 == 0:
                color = PALETTE["chart_white"]
            elif index % 4 == 3:
                color = PALETTE["chart_yellow"]
            canvas.create_rectangle(center - bar_width / 2, y0, center + bar_width / 2, y1, fill=color, outline="")
            canvas.create_text(center, y1 + 12 if value >= 0 else y1 + 12, text=currency, fill=PALETTE["chart_white"], font=(ASSISTANT_FONT_FAMILY, 8))
            canvas.create_text(
                center,
                164,
                text=ui_text(_short_label(label)),
                fill=PALETTE["muted"],
                font=(ASSISTANT_FONT_FAMILY, 8),
                width=58,
                justify="center",
            )

    def _draw_action_chart(self, rows: list[tuple[str, int]]) -> None:
        canvas = self.action_canvas
        canvas.delete("all")
        width = max(canvas.winfo_width(), 420)
        height = max(canvas.winfo_height(), 190)
        if not rows:
            canvas.create_text(
                width / 2,
                height / 2,
                text=ui_text("הפילוח יופיע אחרי חישוב"),
                fill=PALETTE["muted"],
                font=(ASSISTANT_FONT_FAMILY, 12),
            )
            return

        colors = CHART_COLORS
        total = sum(value for _, value in rows) or 1
        center_x = 94
        center_y = 96
        radius = 54
        start = 90
        for index, (_label, value) in enumerate(rows):
            extent = -360 * value / total
            canvas.create_arc(
                center_x - radius,
                center_y - radius,
                center_x + radius,
                center_y + radius,
                start=start,
                extent=extent,
                fill=colors[index % len(colors)],
                outline=PALETTE["panel"],
            )
            start += extent

        legend_x = width - 18
        legend_y = 52
        for index, (label, value) in enumerate(rows[:7]):
            y = legend_y + index * 18
            canvas.create_rectangle(legend_x - 10, y - 6, legend_x, y + 4, fill=colors[index % len(colors)], outline="")
            percent = value / total * 100
            canvas.create_text(
                legend_x - 16,
                y,
                text=ui_text(f"{label}: {value:,} ({percent:.0f}%)"),
                anchor="e",
                fill=PALETTE["muted"],
                font=(ASSISTANT_FONT_FAMILY, 9),
            )


class LoginDialog(ctk.CTkToplevel):
    def __init__(self, parent: CapitalGainsApp) -> None:
        super().__init__(parent)
        self.parent = parent
        self.title(ui_title("התחברות"))
        self.geometry("560x640")
        self.transient(parent)
        self.grab_set()
        self.configure(fg_color=PALETTE["bg"])
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.login_email = tk.StringVar()
        self.login_password = tk.StringVar()
        self.login_remember = tk.BooleanVar(value=True)
        self.register_name = tk.StringVar()
        self.register_email = tk.StringVar()
        self.register_password = tk.StringVar()
        self.register_confirm = tk.StringVar()
        self.register_remember = tk.BooleanVar(value=True)
        self.status_label: ctk.CTkLabel | None = None
        self.google_button: ctk.CTkButton | None = None
        self.logo_image: tk.PhotoImage | None = None

        self._build_ui()

    def _build_ui(self) -> None:
        brand_frame = ctk.CTkFrame(
            self,
            fg_color=PALETTE["panel_alt"],
            corner_radius=12,
            border_width=1,
            border_color=PALETTE["primary_border"],
        )
        brand_frame.pack(fill="x", padx=24, pady=(20, 14))

        self.logo_image = self._load_logo_image()
        if self.logo_image is not None:
            logo_label = tk.Label(self, image=self.logo_image, bg=PALETTE["panel_alt"], bd=0, highlightthickness=0)
            logo_label.pack(in_=brand_frame, pady=(18, 8))
        ctk.CTkLabel(
            brand_frame,
            text=ui_text("ברוכים הבאים"),
            font=ui_font(24, "bold"),
            text_color=PALETTE["text"],
            anchor="e",
        ).pack(fill="x", padx=24, pady=(2, 4))
        ctk.CTkLabel(
            brand_frame,
            text=ui_text("כניסה מאובטחת לניתוח דוחות, תובנות וייצוא אקסל מדויק."),
            font=ui_font(13),
            text_color=PALETTE["muted"],
            anchor="e",
            justify="right",
            wraplength=470,
        ).pack(fill="x", padx=24, pady=(0, 18))

        tabs = ctk.CTkTabview(
            self,
            fg_color=PALETTE["panel"],
            segmented_button_fg_color=PALETTE["mist"],
            segmented_button_selected_color=PALETTE["primary"],
            segmented_button_selected_hover_color=PALETTE["primary_hover"],
            segmented_button_unselected_color=PALETTE["secondary"],
            segmented_button_unselected_hover_color=PALETTE["secondary_hover"],
            text_color=PALETTE["button_text"],
        )
        tabs.pack(fill="both", expand=True, padx=24, pady=(0, 12))
        login_tab = tabs.add(ui_text("התחברות"))
        register_tab = tabs.add(ui_text("הרשמה"))
        self._build_login_tab(login_tab)
        self._build_register_tab(register_tab)

        footer = ctk.CTkFrame(
            self,
            fg_color=PALETTE["panel"],
            corner_radius=8,
            border_width=1,
            border_color=PALETTE["line"],
        )
        footer.pack(fill="x", padx=24, pady=(0, 20))
        self.status_label = ctk.CTkLabel(
            footer,
            text=ui_text("אפשר להתחבר עם אימייל וסיסמה, או להמשיך עם Google."),
            font=ui_font(12),
            text_color=PALETTE["muted"],
            anchor="e",
            justify="right",
            wraplength=420,
        )
        self.status_label.pack(fill="x", padx=14, pady=(10, 8))
        self.google_button = self.parent._button(
            footer,
            "כניסה עם Google",
            self._sign_in_with_google,
            fg_color=PALETTE["secondary"],
            width=180,
        )
        self.google_button.pack(anchor="e", padx=14, pady=(0, 12))
        if not self.parent.auth_service.has_google_configuration():
            self.google_button.configure(state="disabled")
            self.status_label.configure(text=ui_text("חיבור Google יהיה זמין אחרי הוספת google_client_secret.json."))

    def _build_login_tab(self, tab) -> None:
        self._labeled_entry(tab, "אימייל", self.login_email)
        self._labeled_entry(tab, "סיסמה", self.login_password, show="*")
        ctk.CTkCheckBox(
            tab,
            text=ui_text("זכור אותי במחשב הזה"),
            variable=self.login_remember,
            font=ui_font(12),
            text_color=PALETTE["text"],
            fg_color=PALETTE["primary"],
            hover_color=PALETTE["primary_hover"],
            border_color=PALETTE["primary_border"],
            checkmark_color=PALETTE["button_text"],
        ).pack(anchor="e", padx=18, pady=(2, 12))
        self.parent._button(tab, "התחברות", self._login_local, width=140).pack(anchor="e", padx=18, pady=(0, 18))

    def _build_register_tab(self, tab) -> None:
        self._labeled_entry(tab, "שם מלא", self.register_name)
        self._labeled_entry(tab, "אימייל", self.register_email)
        self._labeled_entry(tab, "סיסמה", self.register_password, show="*")
        self._labeled_entry(tab, "אימות סיסמה", self.register_confirm, show="*")
        ctk.CTkCheckBox(
            tab,
            text=ui_text("זכור אותי במחשב הזה"),
            variable=self.register_remember,
            font=ui_font(12),
            text_color=PALETTE["text"],
            fg_color=PALETTE["primary"],
            hover_color=PALETTE["primary_hover"],
            border_color=PALETTE["primary_border"],
            checkmark_color=PALETTE["button_text"],
        ).pack(anchor="e", padx=18, pady=(2, 12))
        self.parent._button(tab, "יצירת משתמש", self._register_local, width=140).pack(anchor="e", padx=18, pady=(0, 18))

    def _labeled_entry(self, parent, label: str, variable: tk.StringVar, show: str | None = None) -> None:
        ctk.CTkLabel(
            parent,
            text=ui_text(label),
            font=ui_font(13, "bold"),
            text_color=PALETTE["text"],
            anchor="e",
        ).pack(fill="x", padx=18, pady=(14, 4))
        entry = ctk.CTkEntry(
            parent,
            textvariable=variable,
            justify="right",
            font=ui_font(13),
            height=38,
            fg_color=PALETTE["panel_alt"],
            border_color=PALETTE["line"],
            text_color=PALETTE["text"],
            show=show or "",
        )
        entry.pack(fill="x", padx=18, pady=(0, 4))

    def _set_status(self, message: str, color: str | None = None) -> None:
        if self.status_label is not None:
            self.status_label.configure(text=ui_text(message), text_color=color or PALETTE["muted"])

    def _load_logo_image(self) -> tk.PhotoImage | None:
        logo_path = app_root() / "assets" / "images" / "capital_gains_logo_transparent.png"
        if not logo_path.exists():
            return None
        try:
            image = tk.PhotoImage(file=str(logo_path))
        except tk.TclError:
            return None
        return image.subsample(5, 5)

    def _login_local(self) -> None:
        try:
            session = self.parent.workflow.sign_in_local(
                self.login_email.get(),
                self.login_password.get(),
                remember=self.login_remember.get(),
            )
        except (InvalidCredentialsError, LocalAuthError) as exc:
            self._set_status(str(exc), PALETTE["warning"])
            return
        self.parent._apply_auth_session(session)

    def _register_local(self) -> None:
        if self.register_password.get() != self.register_confirm.get():
            self._set_status("הסיסמאות אינן זהות.", PALETTE["warning"])
            return
        try:
            session = self.parent.workflow.register_local_user(
                self.register_name.get(),
                self.register_email.get(),
                self.register_password.get(),
                remember=self.register_remember.get(),
            )
        except (DuplicateUserError, WeakPasswordError, LocalAuthError) as exc:
            self._set_status(str(exc), PALETTE["warning"])
            return
        self.parent._apply_auth_session(session)

    def _sign_in_with_google(self) -> None:
        if self.google_button is not None:
            self.google_button.configure(state="disabled")
        self._set_status("פותח דפדפן להתחברות מאובטחת עם Google...", PALETTE["primary_hover"])
        threading.Thread(target=self._google_worker, daemon=True).start()

    def _google_worker(self) -> None:
        try:
            session = self.parent.workflow.sign_in_with_google()
        except (AuthConfigurationError, GoogleAuthError) as exc:
            self.after(0, lambda: self._google_error(str(exc)))
            return
        self.after(0, lambda: self.parent._apply_auth_session(session))

    def _google_error(self, message: str) -> None:
        if self.google_button is not None:
            self.google_button.configure(state="normal")
        self._set_status(message, PALETTE["warning"])

    def _on_close(self) -> None:
        if self.parent.auth_session.connected:
            self.destroy()
            return
        if messagebox.askyesno(ui_title("סגירת האפליקציה"), ui_text("בלי התחברות אי אפשר להמשיך. לסגור את האפליקציה?"), parent=self):
            self.destroy()
            self.parent.destroy()


class MappingTemplateDialog(ctk.CTkToplevel):
    FIELD_LABELS = [
        ("trade_date", "תאריך עסקה"),
        ("action", "פעולה"),
        ("quantity", "כמות"),
        ("price", "מחיר / שער"),
        ("net_amount", "תמורה נטו"),
        ("security_id", "מספר נייר"),
        ("symbol", "סימול"),
        ("security_name", "שם נייר"),
        ("currency", "מטבע"),
        ("commission", "עמלה"),
        ("reference", "אסמכתא"),
        ("bank_reported_gain_loss", "רווח/הפסד בנק"),
    ]

    def __init__(self, parent, preview: HeaderPreview) -> None:
        super().__init__(parent)
        self.preview = preview
        self.saved = False
        self.title(ui_title("התאמת עמודות"))
        self.geometry("760x640")
        self.transient(parent)
        self.grab_set()
        self.configure(fg_color=PALETTE["bg"])
        self.vars: dict[str, tk.StringVar] = {}

        ctk.CTkLabel(
            self,
            text=ui_text(f"הגדירי התאמת עמודות עבור {preview.source_file} / {preview.sheet}"),
            font=ui_font(18, "bold"),
            text_color=PALETTE["text"],
            anchor="e",
        ).pack(fill="x", padx=18, pady=(18, 8))

        ctk.CTkLabel(
            self,
            text=ui_text(f"שורת הכותרות שזוהתה: {preview.header_row_index}"),
            font=ui_font(12),
            text_color=PALETTE["muted"],
            anchor="e",
        ).pack(fill="x", padx=18, pady=(0, 10))

        preview_box = ctk.CTkTextbox(self, height=96, fg_color="#0D1013", text_color=PALETTE["text"], font=ui_font(12))
        preview_box.pack(fill="x", padx=18, pady=(0, 10))
        preview_box.insert("1.0", ui_text("כותרות שזוהו:\n" + " | ".join(preview.headers)))
        if preview.sample_rows:
            preview_box.insert("end", ui_text("\n\nדוגמאות:\n"))
            for row in preview.sample_rows:
                preview_box.insert("end", ui_text(" | ".join(row) + "\n"))
        preview_box.configure(state="disabled")

        scroll = ctk.CTkScrollableFrame(self, fg_color=PALETTE["panel"], corner_radius=8)
        scroll.pack(fill="both", expand=True, padx=18, pady=(0, 10))
        scroll.grid_columnconfigure(1, weight=1)
        options = [""] + preview.headers
        for row_index, (field_name, label) in enumerate(self.FIELD_LABELS):
            ctk.CTkLabel(
                scroll,
                text=ui_text(label),
                font=ui_font(13),
                text_color=PALETTE["text"],
                anchor="e",
            ).grid(row=row_index, column=0, padx=10, pady=6, sticky="e")
            variable = tk.StringVar()
            combo = ttk.Combobox(scroll, textvariable=variable, values=options, state="readonly", justify="right")
            combo.grid(row=row_index, column=1, padx=10, pady=6, sticky="ew")
            self.vars[field_name] = variable

        buttons = ctk.CTkFrame(self, fg_color=PALETTE["panel"])
        buttons.pack(fill="x", padx=18, pady=(0, 18))
        ctk.CTkButton(
            buttons,
            text=ui_text("שמור תבנית"),
            font=ui_font(14, "bold"),
            command=self._save,
            fg_color=PALETTE["primary"],
            hover_color=PALETTE["primary_hover"],
            text_color=PALETTE["button_text"],
        ).pack(side="right", padx=8, pady=8)
        ctk.CTkButton(
            buttons,
            text=ui_text("ביטול"),
            font=ui_font(14, "bold"),
            command=self.destroy,
            fg_color=PALETTE["secondary"],
            hover_color=PALETTE["secondary_hover"],
            text_color="white",
        ).pack(side="right", padx=8, pady=8)

        self._prefill_suggestions()

    def _prefill_suggestions(self) -> None:
        lookup = {_normalize_header_text(header): header for header in self.preview.headers}
        for field_name, aliases in {
            "trade_date": ("trade date", "execution date", "תאריך", "תאריך ביצוע", "תאריך עסקה"),
            "action": ("action", "transaction", "פעולה", "סוג פעולה"),
            "quantity": ("quantity", "qty", "כמות", "units"),
            "price": ("price", "trade price", "שער", "מחיר"),
            "net_amount": ("net amount", "תמורה נטו", "תמורה", "amount"),
            "security_id": ("security id", "מספר נייר", "מספר בורסה", "isin"),
            "symbol": ("symbol", "ticker", "סימול", "security"),
            "security_name": ("security name", "description", "שם נייר", 'שם ני"ע'),
            "currency": ("currency", "מטבע"),
            "commission": ("commission", "עמלות", "עמלה"),
            "reference": ("reference", "אסמכתא"),
            "bank_reported_gain_loss": ("gain/loss", "רווח/הפסד"),
        }.items():
            for alias in aliases:
                header = lookup.get(_normalize_header_text(alias))
                if header:
                    self.vars[field_name].set(header)
                    break

    def _save(self) -> None:
        field_map = {field_name: variable.get().strip() for field_name, variable in self.vars.items() if variable.get().strip()}
        if not all(field in field_map for field in ("trade_date", "action", "quantity")):
            messagebox.showwarning(ui_title("חסר מיפוי"), ui_text("חייבים למפות לפחות תאריך, פעולה וכמות."))
            return
        if not any(field in field_map for field in ("price", "net_amount")):
            messagebox.showwarning(ui_title("חסר מיפוי"), ui_text("צריך למפות מחיר/שער או תמורה נטו."))
            return
        if not any(field in field_map for field in ("security_id", "symbol", "security_name")):
            messagebox.showwarning(ui_title("חסר מיפוי"), ui_text("צריך למפות לפחות מזהה נייר אחד."))
            return

        template_name = f"{self.preview.source_file} - {self.preview.sheet}"
        save_generic_report_template(template_name, field_map)
        self.saved = True
        self.destroy()


class IssuesDialog(ctk.CTkToplevel):
    def __init__(self, parent, issues: list[ValidationIssue]) -> None:
        super().__init__(parent)
        self.title(ui_title("שגיאות בדוחות"))
        self.geometry("860x420")
        self.transient(parent)
        self.grab_set()
        self.configure(fg_color=PALETTE["bg"])

        ctk.CTkLabel(
            self,
            text=ui_text("נמצאו שורות שדורשות תיקון ידני בקובץ המקור"),
            font=ui_font(18, "bold"),
            text_color=PALETTE["text"],
        ).pack(anchor="e", padx=18, pady=(18, 8))

        columns = ("severity", "file", "sheet", "row", "field", "message")
        _configure_treeview_style(self)
        tree = ttk.Treeview(
            self,
            columns=columns,
            displaycolumns=list(reversed(columns)),
            show="headings",
            height=12,
            style="Luxury.Treeview",
        )
        titles = ["חומרה", "קובץ", "גיליון", "שורה", "שדה", "הודעה"]
        for col, title in zip(columns, titles, strict=True):
            tree.heading(col, text=ui_text(title), anchor="e")
            tree.column(col, width=120 if col != "message" else 340, anchor="e")
        for issue in issues:
            tree.insert(
                "",
                tk.END,
                values=(
                    issue.severity,
                    ui_text(issue.source_file),
                    ui_text(issue.sheet),
                    issue.row_number,
                    ui_text(issue.field),
                    ui_text(issue.message),
                ),
            )
        tree.pack(fill="both", expand=True, padx=18, pady=8)

        ctk.CTkButton(
            self,
            text=ui_text("סגור"),
            font=ui_font(14, "bold"),
            command=self.destroy,
            fg_color=PALETTE["primary"],
            hover_color=PALETTE["primary_hover"],
            text_color=PALETTE["button_text"],
        ).pack(
            anchor="e", padx=18, pady=(8, 18)
        )


class CorrectionsDialog(ctk.CTkToplevel):
    def __init__(self, parent, transactions: list[Transaction], issues: list[ValidationIssue]) -> None:
        super().__init__(parent)
        self.title(ui_title("תיקון ידני"))
        self.geometry("920x520")
        self.transient(parent)
        self.grab_set()
        self.configure(fg_color=PALETTE["bg"])
        self.transactions = transactions
        self.issues = issues
        self.corrections: dict[tuple[str, str, int, str], str] = {}
        self.confirmed = False
        self.selected_issue: ValidationIssue | None = None

        ctk.CTkLabel(
            self,
            text=ui_text("נמצאו שורות עם נתון חסר. בחר שורה, הזן ערך מתוקן ושמור."),
            font=ui_font(17, "bold"),
            text_color=PALETTE["text"],
        ).pack(anchor="e", padx=18, pady=(18, 8))

        columns = ("status", "file", "sheet", "row", "field", "value", "message")
        _configure_treeview_style(self)
        self.tree = ttk.Treeview(
            self,
            columns=columns,
            displaycolumns=list(reversed(columns)),
            show="headings",
            height=10,
            style="Luxury.Treeview",
        )
        widths = {"status": 80, "file": 180, "sheet": 100, "row": 70, "field": 90, "value": 100, "message": 260}
        titles = {
            "status": "סטטוס",
            "file": "קובץ",
            "sheet": "גיליון",
            "row": "שורה",
            "field": "שדה",
            "value": "ערך",
            "message": "הודעה",
        }
        for col in columns:
            self.tree.heading(col, text=ui_text(titles[col]), anchor="e")
            self.tree.column(col, width=widths[col], anchor="e")
        for index, issue in enumerate(issues):
            self.tree.insert(
                "",
                tk.END,
                iid=str(index),
                values=(
                    ui_text("פתוח"),
                    ui_text(issue.source_file),
                    ui_text(issue.sheet),
                    issue.row_number,
                    ui_text(issue.field),
                    issue.value,
                    ui_text(issue.message),
                ),
            )
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.pack(fill="both", expand=True, padx=18, pady=8)

        form = ctk.CTkFrame(self, fg_color=PALETTE["panel"])
        form.pack(fill="x", padx=18, pady=(4, 8))
        form.grid_columnconfigure(1, weight=1)
        self.selected_label = ctk.CTkLabel(
            form,
            text=ui_text("לא נבחרה שורה"),
            font=ui_font(13),
            text_color=PALETTE["muted"],
            anchor="e",
        )
        self.selected_label.grid(row=0, column=0, padx=10, pady=10, sticky="e")
        self.value_entry = ctk.CTkEntry(
            form,
            placeholder_text=ui_text("ערך חדש"),
            border_color=PALETTE["line"],
            justify="right",
            font=ui_font(13),
        )
        self.value_entry.grid(row=0, column=1, padx=10, pady=10, sticky="ew")
        ctk.CTkButton(
            form,
            text=ui_text("שמור תיקון"),
            font=ui_font(14, "bold"),
            command=self._save_current,
            fg_color=PALETTE["primary"],
            hover_color=PALETTE["primary_hover"],
            text_color=PALETTE["button_text"],
        ).grid(row=0, column=2, padx=10, pady=10)

        buttons = ctk.CTkFrame(self, fg_color=PALETTE["panel"])
        buttons.pack(fill="x", padx=18, pady=(0, 18))
        ctk.CTkButton(
            buttons,
            text=ui_text("המשך עם התיקונים"),
            font=ui_font(14, "bold"),
            command=self._confirm,
            fg_color=PALETTE["primary"],
            hover_color=PALETTE["primary_hover"],
            text_color=PALETTE["button_text"],
        ).pack(side="right", padx=8, pady=8)
        ctk.CTkButton(
            buttons,
            text=ui_text("ביטול"),
            font=ui_font(14, "bold"),
            fg_color=PALETTE["secondary"],
            hover_color=PALETTE["secondary_hover"],
            command=self.destroy,
        ).pack(side="right", padx=8, pady=8)

    def _on_select(self, _event=None) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        issue = self.issues[int(selection[0])]
        self.selected_issue = issue
        self.selected_label.configure(text=ui_text(f"{issue.source_file} | שורה {issue.row_number} | {issue.field}"))
        self.value_entry.delete(0, tk.END)
        self.value_entry.insert(0, "" if issue.value is None else str(issue.value))

    def _save_current(self) -> None:
        if self.selected_issue is None:
            messagebox.showwarning(ui_title("לא נבחרה שורה"), ui_text("בחר שורה לתיקון."))
            return
        value = self.value_entry.get().strip()
        if not value:
            messagebox.showwarning(ui_title("ערך חסר"), ui_text("הזיני ערך חדש."))
            return
        issue = self.selected_issue
        key = (issue.source_file, issue.sheet, issue.row_number, issue.field)
        self.corrections[key] = value
        selection = self.tree.selection()
        if selection:
            values = list(self.tree.item(selection[0], "values"))
            values[0] = ui_text("תוקן")
            values[5] = value
            self.tree.item(selection[0], values=values)

    def _confirm(self) -> None:
        missing = len(self.issues) - len(self.corrections)
        if missing and not messagebox.askyesno(ui_title("לא כל השורות תוקנו"), ui_text(f"נותרו {missing} שורות ללא תיקון. להמשיך?")):
            return
        self.confirmed = True
        self.destroy()


def _apply_corrections(transactions: list[Transaction], corrections: dict[tuple[str, str, int, str], str]) -> None:
    index = {(tx.source_file, tx.sheet, tx.row_number): tx for tx in transactions}
    for (source_file, sheet, row_number, field), value in corrections.items():
        tx = index.get((source_file, sheet, row_number))
        if tx is None:
            continue
        if field == "quantity":
            tx.quantity = _parse_float(value)
        elif field == "price":
            tx.price = _parse_float(value)
        elif field == "security":
            tx.security_id = value
            tx.symbol = value
        else:
            setattr(tx, field, value)


def _parse_float(value: str) -> float:
    return float(value.replace(",", "").strip())


def _configure_treeview_style(widget) -> None:
    style = ttk.Style(widget)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure(
        "Luxury.Treeview",
        background="#0D1013",
        fieldbackground="#0D1013",
        foreground=PALETTE["text"],
        font=(ASSISTANT_FONT_FAMILY, 11),
        bordercolor=PALETTE["line"],
        lightcolor=PALETTE["line"],
        darkcolor=PALETTE["line"],
        rowheight=28,
    )
    style.configure(
        "Luxury.Treeview.Heading",
        background="#1D2228",
        foreground=PALETTE["chart_white"],
        font=(ASSISTANT_FONT_FAMILY, 11, "bold"),
        bordercolor=PALETTE["line"],
        relief="flat",
        anchor="e",
    )
    style.map("Luxury.Treeview", background=[("selected", "#2A3138")], foreground=[("selected", PALETTE["chart_white"])])


def _short_label(value: str) -> str:
    value = value.strip()
    if len(value) <= 9:
        return value
    return value[:8] + "..."


def main() -> None:
    app = CapitalGainsApp()
    app.mainloop()
