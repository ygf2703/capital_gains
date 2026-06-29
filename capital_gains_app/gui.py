from __future__ import annotations

import random
import threading
import tkinter as tk
from datetime import date, datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk

from .dashboard import build_dashboard_summary
from .exchange_rates import fetch_usd_ils_rate_one_month_back, parse_user_date
from .exporter import export_result
from .fifo import calculate_fifo
from .models import CalculationResult, ExchangeRateSnapshot, Transaction, ValidationIssue
from .parsers import parse_workbooks

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except Exception:  # pragma: no cover - optional dependency
    DND_FILES = None
    TkinterDnD = None


PALETTE = {
    "bg": "#050607",
    "granite": "#0B0D10",
    "granite_light": "#2A2E32",
    "graph_pattern": "#30343A",
    "panel": "#111417",
    "panel_alt": "#0B0E11",
    "panel_glass": "#171B1F",
    "mist": "#20252A",
    "line": "#3A4047",
    "text": "#F4F7F8",
    "muted": "#A9B1B7",
    "primary": "#C8D0D6",
    "primary_hover": "#E7ECEF",
    "button_text": "#080A0C",
    "secondary": "#5E676F",
    "secondary_hover": "#7C858D",
    "card_blue": "#0E2533",
    "card_pink": "#2A1824",
    "card_yellow": "#2C2815",
    "card_silver": "#20252A",
    "chart_white": "#FFFFFF",
    "chart_blue": "#8FD8FF",
    "chart_pink": "#FF8FB8",
    "chart_yellow": "#FFE27A",
    "warning": "#FFE27A",
    "negative": "#FF8FB8",
    "positive": "#8FD8FF",
}
RTL_MARK = "\u200f"
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
        self.title("ניתוח רווחי הון FIFO")
        self.geometry("1180x760")
        self.minsize(1020, 680)
        self.configure(fg_color=PALETTE["bg"])
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")
        self.background = GraniteBackground(self)
        self.background.place(x=0, y=0, relwidth=1, relheight=1)
        self.background.lower()

        self.files: list[Path] = []
        self.last_result: CalculationResult | None = None
        self.last_exchange_rate: ExchangeRateSnapshot | None = None
        self.exchange_date_var = tk.StringVar(value=date.today().isoformat())
        self.kpi_labels: dict[str, ctk.CTkLabel] = {}
        self.insight_labels: list[ctk.CTkLabel] = []

        self._build_ui()

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        header = ctk.CTkFrame(self, corner_radius=0, fg_color=PALETTE["panel_alt"])
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header,
            text="היי ליאת, יש קבצים לניתוח?",
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color=PALETTE["text"],
            anchor="e",
        ).grid(row=0, column=0, padx=28, pady=(20, 4), sticky="ew")
        ctk.CTkLabel(
            header,
            text="מחשבון FIFO מקומי לדוחות אגיס ולאומי, עם דשבורד וייצוא Excel",
            font=ctk.CTkFont(size=15),
            text_color=PALETTE["muted"],
            anchor="e",
        ).grid(row=1, column=0, padx=28, pady=(0, 18), sticky="ew")

        toolbar = ctk.CTkFrame(self, corner_radius=8, fg_color=PALETTE["panel_glass"], border_width=1, border_color=PALETTE["line"])
        toolbar.grid(row=1, column=0, padx=18, pady=14, sticky="ew")
        toolbar.grid_columnconfigure(3, weight=1)

        self._button(toolbar, "בחר קבצים", self.add_files).grid(row=0, column=0, padx=(12, 8), pady=12)
        self._button(toolbar, "נקה", self.clear_files, fg_color=PALETTE["secondary"]).grid(row=0, column=1, padx=8, pady=12)
        self._button(toolbar, "חשב וייצא Excel", self.calculate_and_export).grid(row=0, column=2, padx=8, pady=12)

        exchange_box = ctk.CTkFrame(toolbar, corner_radius=8, fg_color=PALETTE["mist"])
        exchange_box.grid(row=0, column=4, padx=12, pady=10, sticky="e")
        ctk.CTkLabel(exchange_box, text="תאריך מבוקש", text_color=PALETTE["muted"], anchor="e").grid(
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
        self.status = ctk.CTkLabel(bottom, text="מוכן", text_color=PALETTE["muted"], anchor="e", justify="right")
        self.status.grid(row=0, column=0, padx=14, pady=10, sticky="ew")

        self.after(200, self._draw_empty_dashboard)

    def _build_file_panel(self, parent: ctk.CTkFrame) -> None:
        panel = ctk.CTkFrame(parent, corner_radius=8, fg_color=PALETTE["panel"], border_width=1, border_color=PALETTE["line"])
        panel.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        panel.grid_rowconfigure(3, weight=1)
        panel.grid_columnconfigure(0, weight=1)

        label_text = "גררי לכאן קבצי Excel או לחצי על בחירת קבצים"
        if DND_FILES is None:
            label_text = "בחרי דוחות Excel לניתוח"
        ctk.CTkLabel(
            panel,
            text=label_text,
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=PALETTE["text"],
            anchor="e",
        ).grid(row=0, column=0, padx=20, pady=(20, 4), sticky="ew")
        ctk.CTkLabel(
            panel,
            text="הדוחות נשארים מקומית במחשב. קבצי מקור לא נדחפים ל-Git.",
            text_color=PALETTE["muted"],
            anchor="e",
        ).grid(row=1, column=0, padx=20, pady=(0, 14), sticky="ew")
        ctk.CTkLabel(
            panel,
            text="אפשר לנתח גם קובץ יחיד של נייר ערך אחד, והייצוא יישאר זמין.",
            text_color=PALETTE["muted"],
            anchor="e",
        ).grid(row=2, column=0, padx=20, pady=(0, 8), sticky="ew")

        drop_frame = ctk.CTkFrame(panel, border_width=1, border_color=PALETTE["line"], corner_radius=8, fg_color="#0D1013")
        drop_frame.grid(row=3, column=0, padx=20, pady=(0, 20), sticky="nsew")
        drop_frame.grid_columnconfigure(0, weight=1)
        drop_frame.grid_rowconfigure(0, weight=1)

        self.file_list = tk.Listbox(
            drop_frame,
            height=10,
            activestyle="none",
            bg="#0D1013",
            fg=PALETTE["text"],
            highlightthickness=0,
            borderwidth=0,
            selectbackground="#2A3138",
            selectforeground=PALETTE["chart_white"],
            font=("Segoe UI", 10),
        )
        self.file_list.grid(row=0, column=0, padx=14, pady=14, sticky="nsew")

        if DND_FILES is not None:
            drop_frame.drop_target_register(DND_FILES)
            drop_frame.dnd_bind("<<Drop>>", self._on_drop)
            panel.drop_target_register(DND_FILES)
            panel.dnd_bind("<<Drop>>", self._on_drop)

        self.exchange_status = ctk.CTkLabel(
            panel,
            text="שער דולר: טרם נטען",
            text_color=PALETTE["muted"],
            anchor="e",
        )
        self.exchange_status.grid(row=4, column=0, padx=20, pady=(0, 18), sticky="ew")

    def _build_dashboard_panel(self, parent: ctk.CTkFrame) -> None:
        dashboard = ctk.CTkScrollableFrame(parent, corner_radius=8, fg_color=PALETTE["panel"], border_width=1, border_color=PALETTE["line"])
        dashboard.grid(row=0, column=1, sticky="nsew")
        dashboard.grid_columnconfigure((0, 1), weight=1)
        dashboard.grid_rowconfigure(5, weight=1)

        ctk.CTkLabel(
            dashboard,
            text="דשבורד",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=PALETTE["text"],
            anchor="e",
        ).grid(row=0, column=0, columnspan=2, padx=18, pady=(18, 8), sticky="ew")

        cards = [
            ("transactions", "תנועות", PALETTE["card_blue"]),
            ("securities", "ניירות", PALETTE["card_silver"]),
            ("realized", "שורות FIFO", PALETTE["card_pink"]),
            ("issues", "התראות", PALETTE["card_yellow"]),
        ]
        for index, (key, title, color) in enumerate(cards):
            card = ctk.CTkFrame(dashboard, corner_radius=8, fg_color=color)
            card.grid(row=1 + index // 2, column=index % 2, padx=10, pady=8, sticky="ew")
            ctk.CTkLabel(card, text=title, text_color=PALETTE["muted"], anchor="e").pack(
                fill="x", padx=12, pady=(10, 0)
            )
            value_label = ctk.CTkLabel(
                card,
                text="-",
                font=ctk.CTkFont(size=23, weight="bold"),
                text_color=PALETTE["text"],
                anchor="e",
            )
            value_label.pack(fill="x", padx=12, pady=(0, 10))
            self.kpi_labels[key] = value_label

        insights_frame = ctk.CTkFrame(dashboard, corner_radius=8, fg_color="#0D1013", border_width=1, border_color=PALETTE["line"])
        insights_frame.grid(row=3, column=0, columnspan=2, padx=16, pady=(10, 6), sticky="ew")
        insights_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            insights_frame,
            text="5 תובנות מרכזיות",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=PALETTE["text"],
            anchor="e",
        ).grid(row=0, column=0, padx=12, pady=(10, 4), sticky="ew")
        for index in range(5):
            label = ctk.CTkLabel(
                insights_frame,
                text=_rtl(f"{index + 1}. התובנות יופיעו אחרי החישוב"),
                text_color=PALETTE["muted"],
                anchor="e",
                justify="right",
                wraplength=390,
            )
            label.grid(row=index + 1, column=0, padx=12, pady=(0, 4), sticky="ew")
            self.insight_labels.append(label)

        self.gain_canvas = tk.Canvas(
            dashboard,
            width=420,
            height=190,
            bg=PALETTE["panel"],
            highlightthickness=0,
        )
        self.gain_canvas.grid(row=4, column=0, columnspan=2, padx=16, pady=(10, 6), sticky="ew")

        self.action_canvas = tk.Canvas(
            dashboard,
            width=420,
            height=190,
            bg=PALETTE["panel"],
            highlightthickness=0,
        )
        self.action_canvas.grid(row=5, column=0, columnspan=2, padx=16, pady=(6, 16), sticky="nsew")

    def _button(self, parent, text: str, command, fg_color: str | None = None, width: int = 120) -> ctk.CTkButton:
        is_secondary = fg_color == PALETTE["secondary"]
        return ctk.CTkButton(
            parent,
            text=text,
            width=width,
            command=command,
            fg_color=fg_color or PALETTE["primary"],
            hover_color=PALETTE["secondary_hover"] if is_secondary else PALETTE["primary_hover"],
            text_color="white" if is_secondary else PALETTE["button_text"],
            corner_radius=8,
            border_width=1,
            border_color="#EDF1F3" if not is_secondary else PALETTE["line"],
        )

    def add_files(self) -> None:
        selected = filedialog.askopenfilenames(
            title="בחרי דוחות Excel",
            filetypes=[("Excel files", "*.xlsx *.xlsm *.xls"), ("All files", "*.*")],
        )
        self._add_paths(selected)

    def clear_files(self) -> None:
        self.files.clear()
        self.file_list.delete(0, tk.END)
        self.status.configure(text="הרשימה נוקתה")
        self._draw_empty_dashboard()

    def fetch_exchange_rate(self) -> None:
        try:
            requested_date = parse_user_date(self.exchange_date_var.get())
        except ValueError as exc:
            messagebox.showwarning("תאריך לא תקין", str(exc))
            return
        self.exchange_status.configure(text="טוען שער יציג מבנק ישראל...")
        self.status.configure(text="טוען שער דולר מבנק ישראל")
        threading.Thread(target=self._exchange_worker, args=(requested_date,), daemon=True).start()

    def _exchange_worker(self, requested_date: date) -> None:
        try:
            rate = fetch_usd_ils_rate_one_month_back(requested_date)
            self.after(0, lambda: self._set_exchange_rate(rate))
        except Exception as exc:  # pragma: no cover - network boundary
            error = str(exc)
            self.after(0, lambda: self._set_exchange_error(error))

    def _set_exchange_rate(self, rate: ExchangeRateSnapshot) -> None:
        self.last_exchange_rate = rate
        note = f"שער דולר ל-{rate.published_date:%Y-%m-%d}: {rate.rate:.4f}"
        if rate.published_date != rate.lookup_date:
            note += f" (תאריך יעד: {rate.lookup_date:%Y-%m-%d})"
        self.exchange_status.configure(text=_rtl(note), text_color=PALETTE["primary_hover"])
        self.status.configure(text="שער הדולר נטען מבנק ישראל")

    def _set_exchange_error(self, error: str) -> None:
        self.exchange_status.configure(text=_rtl(f"לא ניתן לטעון שער דולר: {error}"), text_color=PALETTE["warning"])
        self.status.configure(text="טעינת שער הדולר נכשלה")

    def _on_drop(self, event) -> None:
        paths = self.tk.splitlist(event.data)
        self._add_paths(paths)

    def _add_paths(self, paths) -> None:
        for raw in paths:
            path = Path(raw)
            if path.suffix.lower() in {".xlsx", ".xlsm", ".xls"} and path not in self.files:
                self.files.append(path)
                self.file_list.insert(tk.END, str(path))
        self.status.configure(text=_rtl(f"{len(self.files)} קבצים ברשימה"))

    def calculate_and_export(self) -> None:
        if not self.files:
            messagebox.showwarning("אין קבצים", "בחרי לפחות קובץ Excel אחד.")
            return
        output = filedialog.asksaveasfilename(
            title="שמרי דוח FIFO",
            defaultextension=".xlsx",
            initialfile=f"fifo_report_{datetime.now():%Y%m%d_%H%M}.xlsx",
            filetypes=[("Excel workbook", "*.xlsx")],
        )
        if not output:
            return
        try:
            requested_date = parse_user_date(self.exchange_date_var.get())
            transactions, issues = parse_workbooks(self.files)
        except Exception as exc:
            messagebox.showerror("שגיאה בקריאת הקבצים", str(exc))
            self.status.configure(text="שגיאה בקריאת הקבצים")
            return

        serious = [issue for issue in issues if issue.severity == "error"]
        if serious:
            dialog = CorrectionsDialog(self, transactions, serious)
            self.wait_window(dialog)
            if not dialog.confirmed:
                self.status.configure(text="החישוב בוטל עד לתיקון הנתונים")
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
                messagebox.showwarning("נותרו שגיאות", "לא כל שורות השגיאה תוקנו. החישוב נעצר.")
                self.status.configure(text="נותרו שגיאות לתיקון")
                return

        self.status.configure(text="מחשב FIFO, מושך שער דולר ומייצא דוח...")
        threading.Thread(
            target=self._calculate_worker,
            args=(transactions, issues, output, requested_date),
            daemon=True,
        ).start()

    def _calculate_worker(
        self,
        transactions: list[Transaction],
        issues: list[ValidationIssue],
        output: str,
        requested_date: date,
    ) -> None:
        exchange_error = ""
        exchange_rate = self.last_exchange_rate
        if exchange_rate is None or exchange_rate.requested_date != requested_date:
            try:
                exchange_rate = fetch_usd_ils_rate_one_month_back(requested_date)
            except Exception as exc:  # pragma: no cover - network boundary
                exchange_error = str(exc)
                exchange_rate = None
        try:
            result = calculate_fifo(transactions, issues)
            result.exchange_rate = exchange_rate
            path = export_result(result, output)
            self.after(0, lambda: self._done(path, result, exchange_error))
        except Exception as exc:  # pragma: no cover - GUI boundary
            error = str(exc)
            self.after(0, lambda: messagebox.showerror("שגיאה", error))
            self.after(0, lambda: self.status.configure(text="שגיאה בחישוב"))

    def _done(self, path: Path, result: CalculationResult, exchange_error: str = "") -> None:
        self.last_result = result
        if result.exchange_rate:
            self.last_exchange_rate = result.exchange_rate
            self._set_exchange_rate(result.exchange_rate)
        self._update_dashboard(result)
        self.status.configure(text=f"הדוח נשמר: {path}")
        extra = f"\nשער דולר: {result.exchange_rate.rate:.4f}" if result.exchange_rate else ""
        if exchange_error:
            extra += f"\nלא נטען שער דולר: {exchange_error}"
        messagebox.showinfo(
            "הסתיים",
            f"הדוח נוצר בהצלחה.\nשורות FIFO: {len(result.realized)}\nהתראות: {len(result.issues)}{extra}\n\n{path}",
        )

    def _update_dashboard(self, result: CalculationResult) -> None:
        summary = build_dashboard_summary(result)
        self.kpi_labels["transactions"].configure(text=f"{summary.total_transactions:,}")
        self.kpi_labels["securities"].configure(text=f"{summary.unique_securities:,}")
        self.kpi_labels["realized"].configure(text=f"{summary.realized_rows:,}")
        self.kpi_labels["issues"].configure(text=f"{summary.issue_count:,}")
        for index, label in enumerate(self.insight_labels):
            insight = summary.key_insights[index] if index < len(summary.key_insights) else ""
            label.configure(text=_rtl(f"{index + 1}. {insight}") if insight else "")
        self._draw_gain_chart(summary.top_securities)
        self._draw_action_chart(summary.action_counts)

    def _draw_empty_dashboard(self) -> None:
        for label in self.kpi_labels.values():
            label.configure(text="-")
        for index, label in enumerate(self.insight_labels):
            label.configure(text=_rtl(f"{index + 1}. התובנות יופיעו אחרי החישוב"))
        self._draw_gain_chart([])
        self._draw_action_chart([])

    def _draw_gain_chart(self, rows: list[tuple[str, str, float]]) -> None:
        canvas = self.gain_canvas
        canvas.delete("all")
        width = max(canvas.winfo_width(), 420)
        height = max(canvas.winfo_height(), 190)
        canvas.create_text(width - 8, 18, text="רווח/הפסד לפי נייר", anchor="e", fill=PALETTE["text"], font=("Segoe UI", 12, "bold"))
        if not rows:
            canvas.create_text(width / 2, height / 2, text="אין עדיין נתוני חישוב", fill=PALETTE["muted"], font=("Segoe UI", 11))
            return

        rows = rows[:6]
        values = [value for _, _, value in rows]
        max_abs = max(abs(value) for value in values) or 1
        chart_left = 24
        chart_right = width - 24
        baseline = 112
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
            canvas.create_text(center, y1 + 12 if value >= 0 else y1 + 12, text=currency, fill=PALETTE["chart_white"], font=("Segoe UI", 8))
            canvas.create_text(
                center,
                168,
                text=_short_label(label),
                fill=PALETTE["muted"],
                font=("Segoe UI", 8),
                width=58,
                justify="center",
            )

    def _draw_action_chart(self, rows: list[tuple[str, int]]) -> None:
        canvas = self.action_canvas
        canvas.delete("all")
        width = max(canvas.winfo_width(), 420)
        height = max(canvas.winfo_height(), 190)
        canvas.create_text(width - 8, 18, text="פילוח פעולות", anchor="e", fill=PALETTE["text"], font=("Segoe UI", 12, "bold"))
        if not rows:
            canvas.create_text(width / 2, height / 2, text="הפילוח יופיע אחרי חישוב", fill=PALETTE["muted"], font=("Segoe UI", 11))
            return

        colors = CHART_COLORS
        total = sum(value for _, value in rows) or 1
        center_x = 88
        center_y = 104
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
                text=f"{label}: {value:,} ({percent:.0f}%)",
                anchor="e",
                fill=PALETTE["muted"],
                font=("Segoe UI", 9),
            )


class IssuesDialog(ctk.CTkToplevel):
    def __init__(self, parent, issues: list[ValidationIssue]) -> None:
        super().__init__(parent)
        self.title("שגיאות בדוחות")
        self.geometry("860x420")
        self.transient(parent)
        self.grab_set()
        self.configure(fg_color=PALETTE["bg"])

        ctk.CTkLabel(
            self,
            text="נמצאו שורות שדורשות תיקון ידני בקובץ המקור",
            font=ctk.CTkFont(size=18, weight="bold"),
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
            tree.heading(col, text=title, anchor="e")
            tree.column(col, width=120 if col != "message" else 340, anchor="e")
        for issue in issues:
            tree.insert(
                "",
                tk.END,
                values=(issue.severity, issue.source_file, issue.sheet, issue.row_number, issue.field, issue.message),
            )
        tree.pack(fill="both", expand=True, padx=18, pady=8)

        ctk.CTkButton(self, text="סגור", command=self.destroy, fg_color=PALETTE["primary"], hover_color=PALETTE["primary_hover"]).pack(
            anchor="e", padx=18, pady=(8, 18)
        )


class CorrectionsDialog(ctk.CTkToplevel):
    def __init__(self, parent, transactions: list[Transaction], issues: list[ValidationIssue]) -> None:
        super().__init__(parent)
        self.title("תיקון ידני")
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
            text="נמצאו שורות עם נתון חסר. בחרי שורה, הזיני ערך מתוקן ושמרי.",
            font=ctk.CTkFont(size=17, weight="bold"),
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
            self.tree.heading(col, text=titles[col], anchor="e")
            self.tree.column(col, width=widths[col], anchor="e")
        for index, issue in enumerate(issues):
            self.tree.insert(
                "",
                tk.END,
                iid=str(index),
                values=("פתוח", issue.source_file, issue.sheet, issue.row_number, issue.field, issue.value, issue.message),
            )
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.pack(fill="both", expand=True, padx=18, pady=8)

        form = ctk.CTkFrame(self, fg_color=PALETTE["panel"])
        form.pack(fill="x", padx=18, pady=(4, 8))
        form.grid_columnconfigure(1, weight=1)
        self.selected_label = ctk.CTkLabel(form, text="לא נבחרה שורה", text_color=PALETTE["muted"], anchor="e")
        self.selected_label.grid(row=0, column=0, padx=10, pady=10, sticky="e")
        self.value_entry = ctk.CTkEntry(form, placeholder_text="ערך חדש", border_color=PALETTE["line"], justify="right")
        self.value_entry.grid(row=0, column=1, padx=10, pady=10, sticky="ew")
        ctk.CTkButton(
            form,
            text="שמור תיקון",
            command=self._save_current,
            fg_color=PALETTE["primary"],
            hover_color=PALETTE["primary_hover"],
        ).grid(row=0, column=2, padx=10, pady=10)

        buttons = ctk.CTkFrame(self, fg_color=PALETTE["panel"])
        buttons.pack(fill="x", padx=18, pady=(0, 18))
        ctk.CTkButton(
            buttons,
            text="המשך עם התיקונים",
            command=self._confirm,
            fg_color=PALETTE["primary"],
            hover_color=PALETTE["primary_hover"],
        ).pack(side="right", padx=8, pady=8)
        ctk.CTkButton(buttons, text="ביטול", fg_color="#7D8D92", command=self.destroy).pack(side="right", padx=8, pady=8)

    def _on_select(self, _event=None) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        issue = self.issues[int(selection[0])]
        self.selected_issue = issue
        self.selected_label.configure(text=f"{issue.source_file} | שורה {issue.row_number} | {issue.field}")
        self.value_entry.delete(0, tk.END)
        self.value_entry.insert(0, "" if issue.value is None else str(issue.value))

    def _save_current(self) -> None:
        if self.selected_issue is None:
            messagebox.showwarning("לא נבחרה שורה", "בחרי שורה לתיקון.")
            return
        value = self.value_entry.get().strip()
        if not value:
            messagebox.showwarning("ערך חסר", "הזיני ערך חדש.")
            return
        issue = self.selected_issue
        key = (issue.source_file, issue.sheet, issue.row_number, issue.field)
        self.corrections[key] = value
        selection = self.tree.selection()
        if selection:
            values = list(self.tree.item(selection[0], "values"))
            values[0] = "תוקן"
            values[5] = value
            self.tree.item(selection[0], values=values)

    def _confirm(self) -> None:
        missing = len(self.issues) - len(self.corrections)
        if missing and not messagebox.askyesno("לא כל השורות תוקנו", f"נותרו {missing} שורות ללא תיקון. להמשיך?"):
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
        bordercolor=PALETTE["line"],
        lightcolor=PALETTE["line"],
        darkcolor=PALETTE["line"],
        rowheight=28,
    )
    style.configure(
        "Luxury.Treeview.Heading",
        background="#1D2228",
        foreground=PALETTE["chart_white"],
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


def _rtl(value: str) -> str:
    return f"{RTL_MARK}{value}"


def main() -> None:
    app = CapitalGainsApp()
    app.mainloop()
