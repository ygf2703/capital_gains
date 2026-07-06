from __future__ import annotations

import argparse
from pathlib import Path

from .services import apply_exchange_rate, calculate_analysis, export_analysis, parse_reports


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
    parsed = parse_reports([Path(file) for file in files])
    result = calculate_analysis(parsed.transactions, parsed.issues, infer_missing_cost_basis=infer_missing_cost)
    apply_exchange_rate(result, exchange_date)
    return export_analysis(result, output)


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
