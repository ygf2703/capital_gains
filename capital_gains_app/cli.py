from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from .exchange_rates import fetch_usd_ils_rate_one_month_back, parse_user_date
from .exporter import export_result
from .fifo import calculate_fifo
from .parsers import parse_workbooks


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Calculate FIFO capital gains from broker Excel reports.")
    parser.add_argument("files", nargs="+", help="Excel files to process")
    parser.add_argument("--output", "-o", default="", help="Output XLSX path")
    parser.add_argument(
        "--no-infer-missing-cost",
        action="store_true",
        help="Do not infer missing opening lots from Leumi bank-reported gain/loss",
    )
    parser.add_argument(
        "--exchange-date",
        default="",
        help="Fetch USD/ILS official Bank of Israel rate for one month before this date (YYYY-MM-DD or DD/MM/YYYY)",
    )
    return parser


def run(files: list[str], output: str = "", infer_missing_cost: bool = True, exchange_date: str = "") -> Path:
    transactions, issues = parse_workbooks([Path(file) for file in files])
    result = calculate_fifo(transactions, issues, infer_missing_cost_basis=infer_missing_cost)
    if exchange_date:
        result.exchange_rate = fetch_usd_ils_rate_one_month_back(parse_user_date(exchange_date))
    output_path = Path(output) if output else Path("outputs") / f"fifo_report_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
    return export_result(result, output_path)


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    output = run(
        args.files,
        args.output,
        infer_missing_cost=not args.no_infer_missing_cost,
        exchange_date=args.exchange_date,
    )
    print(f"Report created: {output}")


if __name__ == "__main__":
    main()
