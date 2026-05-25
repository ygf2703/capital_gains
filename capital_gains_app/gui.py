from __future__ import annotations

import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk

from .exporter import export_result
from .fifo import calculate_fifo
from .models import Transaction, ValidationIssue
from .parsers import parse_workbooks

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except Exception:  # pragma: no cover - optional dependency
    DND_FILES = None
    TkinterDnD = None


if TkinterDnD is not None:
    class BaseWindow(ctk.CTk, TkinterDnD.DnDWrapper):  # type: ignore[misc]
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)
            self.TkdndVersion = TkinterDnD._require(self)
else:
    BaseWindow = ctk.CTk


class CapitalGainsApp(BaseWindow):
    def __init__(self) -> None:
        super().__init__()
        self.title("Capital Gains FIFO")
        self.geometry("980x680")
        self.minsize(860, 580)
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")

        self.files: list[Path] = []
        self.transactions: list[Transaction] = []
        self.issues: list[ValidationIssue] = []

        self._build_ui()

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        header = ctk.CTkFrame(self, corner_radius=0)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text="Capital Gains FIFO", font=ctk.CTkFont(size=24, weight="bold")).grid(
            row=0, column=0, padx=24, pady=(18, 2), sticky="w"
        )
        ctk.CTkLabel(header, text="חישוב FIFO מקומי מדוחות Excel של אגיס ולאומי").grid(
            row=1, column=0, padx=24, pady=(0, 18), sticky="w"
        )

        controls = ctk.CTkFrame(self)
        controls.grid(row=1, column=0, padx=18, pady=14, sticky="ew")
        controls.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(controls, text="הוסף קבצים", command=self.add_files).grid(row=0, column=0, padx=10, pady=10)
        ctk.CTkButton(controls, text="נקה רשימה", fg_color="#6B7280", command=self.clear_files).grid(
            row=0, column=1, padx=10, pady=10, sticky="w"
        )
        ctk.CTkButton(controls, text="חשב וייצא Excel", command=self.calculate_and_export).grid(
            row=0, column=2, padx=10, pady=10
        )

        self.drop_area = ctk.CTkFrame(self, border_width=2, border_color="#2F80ED", corner_radius=8)
        self.drop_area.grid(row=2, column=0, padx=18, pady=(0, 14), sticky="nsew")
        self.drop_area.grid_rowconfigure(1, weight=1)
        self.drop_area.grid_columnconfigure(0, weight=1)

        label_text = "גרור לכאן קבצי Excel או לחץ על הוסף קבצים"
        if DND_FILES is None:
            label_text = "לחץ על הוסף קבצים לבחירת דוחות Excel"
        ctk.CTkLabel(self.drop_area, text=label_text, font=ctk.CTkFont(size=18, weight="bold")).grid(
            row=0, column=0, padx=18, pady=16
        )

        self.file_list = tk.Listbox(self.drop_area, height=8, activestyle="none")
        self.file_list.grid(row=1, column=0, padx=18, pady=(0, 14), sticky="nsew")

        if DND_FILES is not None:
            self.drop_area.drop_target_register(DND_FILES)
            self.drop_area.dnd_bind("<<Drop>>", self._on_drop)

        bottom = ctk.CTkFrame(self)
        bottom.grid(row=3, column=0, padx=18, pady=(0, 18), sticky="ew")
        bottom.grid_columnconfigure(0, weight=1)
        self.status = ctk.CTkLabel(bottom, text="מוכן")
        self.status.grid(row=0, column=0, padx=10, pady=10, sticky="w")

    def add_files(self) -> None:
        selected = filedialog.askopenfilenames(
            title="בחר דוחות Excel",
            filetypes=[("Excel files", "*.xlsx *.xlsm *.xls"), ("All files", "*.*")],
        )
        self._add_paths(selected)

    def clear_files(self) -> None:
        self.files.clear()
        self.file_list.delete(0, tk.END)
        self.status.configure(text="הרשימה נוקתה")

    def _on_drop(self, event) -> None:
        paths = self.tk.splitlist(event.data)
        self._add_paths(paths)

    def _add_paths(self, paths) -> None:
        for raw in paths:
            path = Path(raw)
            if path.suffix.lower() in {".xlsx", ".xlsm", ".xls"} and path not in self.files:
                self.files.append(path)
                self.file_list.insert(tk.END, str(path))
        self.status.configure(text=f"{len(self.files)} קבצים ברשימה")

    def calculate_and_export(self) -> None:
        if not self.files:
            messagebox.showwarning("אין קבצים", "בחר לפחות קובץ Excel אחד.")
            return
        output = filedialog.asksaveasfilename(
            title="שמור דוח FIFO",
            defaultextension=".xlsx",
            initialfile=f"fifo_report_{datetime.now():%Y%m%d_%H%M}.xlsx",
            filetypes=[("Excel workbook", "*.xlsx")],
        )
        if not output:
            return
        try:
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

        self.status.configure(text="מחשב FIFO ומייצא דוח...")
        threading.Thread(target=self._calculate_worker, args=(transactions, issues, output), daemon=True).start()

    def _calculate_worker(self, transactions: list[Transaction], issues: list[ValidationIssue], output: str) -> None:
        try:
            result = calculate_fifo(transactions, issues)
            path = export_result(result, output)
            self.after(0, lambda: self._done(path, len(result.realized), len(result.issues)))
        except Exception as exc:  # pragma: no cover - GUI boundary
            error = str(exc)
            self.after(0, lambda: messagebox.showerror("שגיאה", error))
            self.after(0, lambda: self.status.configure(text="שגיאה בחישוב"))

    def _show_issues(self, issues: list[ValidationIssue]) -> None:
        dialog = IssuesDialog(self, issues)
        self.wait_window(dialog)
        self.status.configure(text="נמצאו שגיאות בדוח. תקן את קובץ המקור והריץ שוב.")

    def _done(self, path: Path, realized_count: int, issue_count: int) -> None:
        self.status.configure(text=f"הדוח נשמר: {path}")
        messagebox.showinfo("הסתיים", f"הדוח נוצר בהצלחה.\nשורות FIFO: {realized_count}\nהתראות: {issue_count}\n\n{path}")


class IssuesDialog(ctk.CTkToplevel):
    def __init__(self, parent, issues: list[ValidationIssue]) -> None:
        super().__init__(parent)
        self.title("שגיאות בדוחות")
        self.geometry("860x420")
        self.transient(parent)
        self.grab_set()

        ctk.CTkLabel(
            self,
            text="נמצאו שורות שדורשות תיקון ידני בקובץ המקור",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).pack(anchor="w", padx=18, pady=(18, 8))

        columns = ("severity", "file", "sheet", "row", "field", "message")
        tree = ttk.Treeview(self, columns=columns, show="headings", height=12)
        for col, title in zip(columns, ["severity", "file", "sheet", "row", "field", "message"], strict=True):
            tree.heading(col, text=title)
            tree.column(col, width=120 if col != "message" else 340)
        for issue in issues:
            tree.insert(
                "",
                tk.END,
                values=(issue.severity, issue.source_file, issue.sheet, issue.row_number, issue.field, issue.message),
            )
        tree.pack(fill="both", expand=True, padx=18, pady=8)

        ctk.CTkButton(self, text="סגור", command=self.destroy).pack(anchor="e", padx=18, pady=(8, 18))


class CorrectionsDialog(ctk.CTkToplevel):
    def __init__(self, parent, transactions: list[Transaction], issues: list[ValidationIssue]) -> None:
        super().__init__(parent)
        self.title("תיקון ידני")
        self.geometry("920x520")
        self.transient(parent)
        self.grab_set()
        self.transactions = transactions
        self.issues = issues
        self.corrections: dict[tuple[str, str, int, str], str] = {}
        self.confirmed = False
        self.selected_issue: ValidationIssue | None = None

        ctk.CTkLabel(
            self,
            text="נמצאו שורות עם נתון חסר. בחר שורה, הזן ערך מתוקן, ושמור.",
            font=ctk.CTkFont(size=17, weight="bold"),
        ).pack(anchor="w", padx=18, pady=(18, 8))

        columns = ("status", "file", "sheet", "row", "field", "value", "message")
        self.tree = ttk.Treeview(self, columns=columns, show="headings", height=10)
        widths = {"status": 80, "file": 180, "sheet": 100, "row": 70, "field": 90, "value": 100, "message": 260}
        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=widths[col])
        for index, issue in enumerate(issues):
            self.tree.insert(
                "",
                tk.END,
                iid=str(index),
                values=("פתוח", issue.source_file, issue.sheet, issue.row_number, issue.field, issue.value, issue.message),
            )
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.pack(fill="both", expand=True, padx=18, pady=8)

        form = ctk.CTkFrame(self)
        form.pack(fill="x", padx=18, pady=(4, 8))
        form.grid_columnconfigure(1, weight=1)
        self.selected_label = ctk.CTkLabel(form, text="לא נבחרה שורה")
        self.selected_label.grid(row=0, column=0, padx=10, pady=10, sticky="w")
        self.value_entry = ctk.CTkEntry(form, placeholder_text="ערך חדש")
        self.value_entry.grid(row=0, column=1, padx=10, pady=10, sticky="ew")
        ctk.CTkButton(form, text="שמור תיקון", command=self._save_current).grid(row=0, column=2, padx=10, pady=10)

        buttons = ctk.CTkFrame(self)
        buttons.pack(fill="x", padx=18, pady=(0, 18))
        ctk.CTkButton(buttons, text="המשך עם התיקונים", command=self._confirm).pack(side="right", padx=8, pady=8)
        ctk.CTkButton(buttons, text="ביטול", fg_color="#6B7280", command=self.destroy).pack(side="right", padx=8, pady=8)

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
            messagebox.showwarning("לא נבחרה שורה", "בחר שורה לתיקון.")
            return
        value = self.value_entry.get().strip()
        if not value:
            messagebox.showwarning("ערך חסר", "הזן ערך חדש.")
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


def main() -> None:
    app = CapitalGainsApp()
    app.mainloop()
