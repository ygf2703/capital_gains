from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .models import CalculationResult, CorporateActionRecord, Lot, RealizedMatch, Transaction, ValidationIssue


HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
HEADER_FONT = Font(color="FFFFFF", bold=True)
MONEY_FORMAT = '#,##0.00;[Red]-#,##0.00;"-"'
QTY_FORMAT = '#,##0.######;[Red]-#,##0.######;"-"'
DATE_FORMAT = "yyyy-mm-dd"


def export_result(result: CalculationResult, output_path: str | Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    wb = Workbook()
    summary = wb.active
    summary.title = "Summary"

    _write_summary(summary, result)
    _write_realized(wb.create_sheet("Realized FIFO"), result.realized)
    _write_open_lots(wb.create_sheet("Open Positions"), result.open_lots)
    _write_transactions(wb.create_sheet("Transactions"), result.transactions)
    _write_corporate_actions(wb.create_sheet("Corporate Actions"), result.corporate_actions)
    _write_issues(wb.create_sheet("Validation Issues"), result.issues)

    for ws in wb.worksheets:
        _format_sheet(ws)

    wb.save(output_path)
    return output_path


def _write_summary(ws, result: CalculationResult) -> None:
    ws.append(["Metric", "Value"])
    totals: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for row in result.realized:
        totals[row.currency]["Proceeds"] += row.proceeds
        totals[row.currency]["Cost Basis"] += row.cost_basis
        totals[row.currency]["Gain/Loss"] += row.gain_loss
        if row.bank_reported_gain_loss is not None:
            totals[row.currency]["Bank Reported Gain/Loss"] += row.bank_reported_gain_loss

    ws.append(["Transactions", len(result.transactions)])
    ws.append(["Realized FIFO rows", len(result.realized)])
    ws.append(["Open lots", len(result.open_lots)])
    ws.append(["Corporate actions", len(result.corporate_actions)])
    ws.append(["Validation issues", len(result.issues)])
    ws.append([])
    ws.append(["Currency", "Proceeds", "Cost Basis", "Gain/Loss", "Bank Reported Gain/Loss", "Difference"])
    for currency, values in sorted(totals.items()):
        bank_gain = values.get("Bank Reported Gain/Loss", 0.0)
        gain = values.get("Gain/Loss", 0.0)
        ws.append(
            [
                currency,
                values.get("Proceeds", 0.0),
                values.get("Cost Basis", 0.0),
                gain,
                bank_gain if bank_gain else None,
                gain - bank_gain if bank_gain else None,
            ]
        )


def _write_realized(ws, rows: Iterable[RealizedMatch]) -> None:
    ws.append(
        [
            "sale_date",
            "security_key",
            "security_id",
            "symbol",
            "security_name",
            "quantity",
            "proceeds",
            "cost_basis",
            "gain_loss",
            "currency",
            "buy_date",
            "buy_source_file",
            "buy_row",
            "sale_source_file",
            "sale_row",
            "inferred",
            "action_raw",
            "bank_reported_gain_loss",
            "difference_vs_bank",
        ]
    )
    for row in rows:
        bank = row.bank_reported_gain_loss
        ws.append(
            [
                row.sale_date,
                row.security_key,
                row.security_id,
                row.symbol,
                row.security_name,
                row.quantity,
                row.proceeds,
                row.cost_basis,
                row.gain_loss,
                row.currency,
                row.buy_date,
                row.buy_source_file,
                row.buy_row,
                row.sale_source_file,
                row.sale_row,
                row.inferred,
                row.action_raw,
                bank,
                row.gain_loss - bank if bank is not None else None,
            ]
        )


def _write_open_lots(ws, rows: Iterable[Lot]) -> None:
    ws.append(
        [
            "security_key",
            "security_id",
            "symbol",
            "security_name",
            "acquired_date",
            "quantity",
            "unit_cost",
            "total_cost",
            "currency",
            "source_file",
            "source_row",
            "inferred",
            "notes",
        ]
    )
    for row in rows:
        ws.append(
            [
                row.security_key,
                row.security_id,
                row.symbol,
                row.security_name,
                row.acquired_date,
                row.quantity,
                row.unit_cost,
                row.total_cost,
                row.currency,
                row.source_file,
                row.source_row,
                row.inferred,
                row.notes,
            ]
        )


def _write_transactions(ws, rows: Iterable[Transaction]) -> None:
    ws.append(
        [
            "trade_date",
            "broker",
            "source_file",
            "sheet",
            "row_number",
            "action_raw",
            "action_type",
            "security_key",
            "security_id",
            "symbol",
            "security_name",
            "quantity",
            "price",
            "currency",
            "report_currency",
            "net_amount",
            "commission",
            "fees",
            "bank_reported_gain_loss",
            "reference",
        ]
    )
    for row in rows:
        ws.append(
            [
                row.trade_date,
                row.broker,
                row.source_file,
                row.sheet,
                row.row_number,
                row.action_raw,
                row.action_type.value,
                row.inventory_key,
                row.security_id,
                row.symbol,
                row.security_name,
                row.quantity,
                row.price,
                row.currency,
                row.report_currency,
                row.net_amount,
                row.commission,
                row.fees,
                row.bank_reported_gain_loss,
                row.reference,
            ]
        )


def _write_corporate_actions(ws, rows: Iterable[CorporateActionRecord]) -> None:
    ws.append(
        [
            "action_date",
            "action_type",
            "old_key",
            "new_key",
            "old_quantity",
            "new_quantity",
            "ratio",
            "source_file",
            "row_numbers",
            "notes",
        ]
    )
    for row in rows:
        ws.append(
            [
                row.action_date,
                row.action_type,
                row.old_key,
                row.new_key,
                row.old_quantity,
                row.new_quantity,
                row.ratio,
                row.source_file,
                row.row_numbers,
                row.notes,
            ]
        )


def _write_issues(ws, rows: Iterable[ValidationIssue]) -> None:
    ws.append(["severity", "message", "source_file", "sheet", "row_number", "field", "value"])
    for row in rows:
        ws.append([row.severity, row.message, row.source_file, row.sheet, row.row_number, row.field, row.value])


def _format_sheet(ws) -> None:
    ws.freeze_panes = "A2"
    ws.sheet_view.rightToLeft = False
    for cell in ws[1]:
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center")

    for row in ws.iter_rows():
        for cell in row:
            if isinstance(cell.value, datetime):
                cell.number_format = DATE_FORMAT
            elif isinstance(cell.value, float):
                header = str(ws.cell(row=1, column=cell.column).value or "").lower()
                if "quantity" in header or "ratio" in header or "price" in header or "unit" in header:
                    cell.number_format = QTY_FORMAT
                else:
                    cell.number_format = MONEY_FORMAT

    for column_cells in ws.columns:
        max_length = 0
        column = column_cells[0].column
        for cell in column_cells:
            value = cell.value
            if value is None:
                continue
            max_length = max(max_length, len(str(value)))
        ws.column_dimensions[get_column_letter(column)].width = min(max(max_length + 2, 10), 42)
    ws.auto_filter.ref = ws.dimensions
