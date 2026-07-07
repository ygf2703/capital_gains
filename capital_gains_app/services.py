from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .exchange_rates import fetch_usd_ils_rate_one_month_back, parse_user_date
from .exporter import export_result
from .fifo import calculate_fifo
from .models import CalculationResult, Transaction, ValidationIssue
from .parsers import HeaderPreview, inspect_workbook_headers, parse_workbooks
from .qa import (
    QAResponse,
    answer_report_question,
    answer_report_question_with_evidence,
    suggested_follow_up_questions as build_follow_up_questions,
    suggested_report_questions,
)
from .report_templates import build_report_template, save_report_template


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


def preview_report_headers(paths: list[str | Path]) -> list[HeaderPreview]:
    previews: list[HeaderPreview] = []
    for path_like in paths:
        previews.extend(inspect_workbook_headers(Path(path_like)))
    return previews


def save_generic_report_template(name: str, field_map: dict[str, str]) -> None:
    save_report_template(build_report_template(name=name, field_map=field_map, broker="generic"))


def answer_question(result: CalculationResult | None, question: str) -> str:
    return answer_report_question(result, question)


def answer_question_with_evidence(result: CalculationResult | None, question: str) -> QAResponse:
    return answer_report_question_with_evidence(result, question)


def suggest_questions(result: CalculationResult | None) -> list[str]:
    return suggested_report_questions(result)


def suggest_follow_up_questions(result: CalculationResult | None, question: str, response: QAResponse | None = None) -> list[str]:
    return build_follow_up_questions(result, question, response)
