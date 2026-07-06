from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .exchange_rates import fetch_usd_ils_rate_one_month_back, parse_user_date
from .exporter import export_result
from .fifo import calculate_fifo
from .models import CalculationResult, Transaction, ValidationIssue
from .parsers import parse_workbooks


@dataclass(slots=True)
class ParsedReports:
    transactions: list[Transaction]
    issues: list[ValidationIssue]


def parse_reports(paths: list[str | Path]) -> ParsedReports:
    transactions, issues = parse_workbooks(paths)
    return ParsedReports(transactions=transactions, issues=issues)


def calculate_analysis(
    transactions: list[Transaction],
    issues: list[ValidationIssue],
    *,
    infer_missing_cost_basis: bool = True,
) -> CalculationResult:
    return calculate_fifo(transactions, issues, infer_missing_cost_basis=infer_missing_cost_basis)


def apply_exchange_rate(result: CalculationResult, exchange_date: str) -> None:
    if not exchange_date:
        return
    result.exchange_rate = fetch_usd_ils_rate_one_month_back(parse_user_date(exchange_date))


def build_output_path(output: str = "") -> Path:
    if output:
        return Path(output)
    return Path("outputs") / f"fifo_report_{datetime.now():%Y%m%d_%H%M%S}.xlsx"


def export_analysis(result: CalculationResult, output: str = "") -> Path:
    return export_result(result, build_output_path(output))
