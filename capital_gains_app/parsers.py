from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from openpyxl import load_workbook

from .models import ActionType, Transaction, ValidationIssue


HEADER_ALIASES = {
    "agis": {"Trade Date", "Transaction", "Quantity", "Net Amount ($)"},
    "leumi": {"אסמכתא", "תאריך ביצוע", "פעולה", "כמות ביצוע", "תמורה נטו לפני מס"},
}


def parse_workbooks(paths: list[str | Path]) -> tuple[list[Transaction], list[ValidationIssue]]:
    transactions: list[Transaction] = []
    issues: list[ValidationIssue] = []
    for path_like in paths:
        path = Path(path_like)
        parsed, file_issues = parse_workbook(path)
        transactions.extend(parsed)
        issues.extend(file_issues)
    return transactions, issues


def parse_workbook(path: Path) -> tuple[list[Transaction], list[ValidationIssue]]:
    workbook = load_workbook(path, read_only=True, data_only=True)
    all_transactions: list[Transaction] = []
    issues: list[ValidationIssue] = []

    for sheet in workbook.worksheets:
        rows = list(sheet.iter_rows(values_only=True))
        header_row_index, broker = _detect_header(rows)
        if header_row_index is None or broker is None:
            issues.append(
                ValidationIssue(
                    severity="error",
                    message="Could not detect a supported report header",
                    source_file=path.name,
                    sheet=sheet.title,
                    row_number=1,
                )
            )
            continue

        headers = [_clean_header(v) for v in rows[header_row_index - 1]]
        data_rows = rows[header_row_index:]
        df = pd.DataFrame(data_rows, columns=headers)
        df = df.dropna(how="all")

        if broker == "agis":
            parsed, sheet_issues = _parse_agis(df, path.name, sheet.title, header_row_index)
        else:
            parsed, sheet_issues = _parse_leumi(df, path.name, sheet.title, header_row_index)
        all_transactions.extend(parsed)
        issues.extend(sheet_issues)

    return all_transactions, issues


def _detect_header(rows: list[tuple[Any, ...]]) -> tuple[int | None, str | None]:
    for index, row in enumerate(rows, start=1):
        values = {_clean_header(v) for v in row if v is not None}
        for broker, required in HEADER_ALIASES.items():
            if required.issubset(values):
                return index, broker
    return None, None


def _parse_agis(
    df: pd.DataFrame, source_file: str, sheet: str, header_row_index: int
) -> tuple[list[Transaction], list[ValidationIssue]]:
    transactions: list[Transaction] = []
    issues: list[ValidationIssue] = []
    for position, row in df.iterrows():
        row_number = header_row_index + 1 + int(position)
        action_raw = _text(row.get("Transaction"))
        trade_date = _parse_date(row.get("Trade Date"))
        quantity = _num(row.get("Quantity"))
        price_raw = row.get("Price ($)")
        price = _num(price_raw)
        net_amount = _num(row.get("Net Amount ($)"))
        security_type = _text(row.get("Security Type"))

        if not action_raw or not trade_date:
            continue
        if action_raw in {"Memo", "Charge", "Margin Int", "Journal"} and not quantity:
            continue
        if security_type and security_type.lower() != "equity":
            continue

        action_type = _map_agis_action(action_raw, quantity)
        transaction = Transaction(
            source_file=source_file,
            sheet=sheet,
            row_number=row_number,
            broker="Agis",
            trade_date=trade_date,
            settlement_date=_parse_date(row.get("Settlement Date")),
            action_raw=action_raw,
            action_type=action_type,
            security_id=_text(row.get("Cusip")),
            symbol=_text(row.get("Security")),
            security_name=_text(row.get("Description")),
            quantity=quantity,
            price=price,
            currency=_normalize_currency(row.get("Base Currency")),
            report_currency=_normalize_currency(row.get("Base Currency")),
            commission=_num(row.get("Commissions ($)")),
            fees=_num(row.get("Fees ($)")),
            net_amount=net_amount,
            account_type=_text(row.get("Account Type")),
            description=_text(row.get("Description")),
            raw=_row_to_dict(row),
        )
        _validate_transaction(transaction, issues)
        if transaction.action_type in {ActionType.BUY, ActionType.SELL} and _is_missing(price_raw):
            issues.append(_issue(transaction, "error", "Missing price", "price", price_raw))
        if transaction.action_type != ActionType.IGNORE:
            transactions.append(transaction)
    return transactions, issues


def _parse_leumi(
    df: pd.DataFrame, source_file: str, sheet: str, header_row_index: int
) -> tuple[list[Transaction], list[ValidationIssue]]:
    transactions: list[Transaction] = []
    issues: list[ValidationIssue] = []
    for position, row in df.iterrows():
        row_number = header_row_index + 1 + int(position)
        action_raw = _text(row.get("פעולה"))
        trade_date = _parse_date(row.get("תאריך ביצוע"), day_first=True)
        security_id = _text(row.get("מס' בורסה"))
        security_name = _text(row.get('שם ני"ע'))
        quantity = _num(row.get("כמות ביצוע"))
        price_raw = row.get("שער ביצוע")
        price = _num(price_raw)
        net_amount = _num(row.get("תמורה נטו לפני מס"))

        if not action_raw or not trade_date:
            continue
        if str(row.get("אסמכתא", "")).startswith("סה"):
            continue

        action_type = _map_leumi_action(action_raw, quantity, net_amount)
        transaction = Transaction(
            source_file=source_file,
            sheet=sheet,
            row_number=row_number,
            broker="Leumi",
            trade_date=trade_date,
            action_raw=action_raw,
            action_type=action_type,
            security_id=security_id,
            symbol=security_id,
            security_name=security_name,
            quantity=quantity,
            price=price,
            currency=_normalize_currency(row.get("מטבע")),
            report_currency="ILS",
            commission=_num(row.get("עמלות ודמי ניהול")),
            fees=0.0,
            net_amount=net_amount,
            bank_reported_gain_loss=_optional_num(row.get("רווח/הפסד")),
            tax_rate=_optional_num(row.get("שעור המס")),
            tax_withheld_local=_optional_num(row.get("מס שנוכה/הוחזר בארץ")),
            tax_withheld_foreign=_optional_num(row.get('מס חו"ל בשקלים')),
            reference=_text(row.get("אסמכתא")),
            description=security_name,
            raw=_row_to_dict(row),
        )
        _validate_transaction(transaction, issues)
        if transaction.action_type in {ActionType.BUY, ActionType.SELL} and _is_missing(price_raw):
            issues.append(_issue(transaction, "error", "Missing price", "price", price_raw))
        if transaction.action_type != ActionType.IGNORE:
            transactions.append(transaction)
    return transactions, issues


def _map_agis_action(action: str, quantity: float) -> ActionType:
    normalized = action.strip().lower()
    if normalized == "purchase":
        return ActionType.BUY
    if normalized == "sale":
        return ActionType.SELL
    if normalized == "receive":
        return ActionType.TRANSFER_IN
    if normalized == "deliver":
        return ActionType.TRANSFER_OUT
    if "reverse" in normalized or "splt" in normalized or "split" in normalized:
        return ActionType.SPLIT_IN if quantity > 0 else ActionType.SPLIT_OUT
    if normalized == "stock movement":
        if quantity > 0:
            return ActionType.SPLIT_IN
        if quantity < 0:
            return ActionType.SPLIT_OUT
        return ActionType.CASH
    return ActionType.IGNORE


def _map_leumi_action(action: str, quantity: float, net_amount: float) -> ActionType:
    normalized = action.strip()
    if "קניה" in normalized or normalized == "הזמנה":
        return ActionType.BUY
    if "מכירה" in normalized or normalized in {"פדיון", "דמי ניכיון"}:
        return ActionType.SELL
    if "מקבל בהעברה" in normalized:
        return ActionType.TRANSFER_IN
    if normalized == "הקטנת הון":
        return ActionType.CAPITAL_REDUCTION
    if normalized == "פקיעה - נייר":
        return ActionType.EXPIRE
    if quantity == 0 and net_amount:
        return ActionType.CASH
    return ActionType.IGNORE


def _validate_transaction(transaction: Transaction, issues: list[ValidationIssue]) -> None:
    if transaction.action_type in {ActionType.BUY, ActionType.SELL, ActionType.TRANSFER_IN}:
        if not transaction.quantity:
            issues.append(_issue(transaction, "error", "Missing or zero quantity", "quantity", transaction.quantity))
        if not transaction.security_id and not transaction.symbol and not transaction.security_name:
            issues.append(_issue(transaction, "error", "Missing security identifier", "security", ""))
    if transaction.action_type == ActionType.UNKNOWN:
        issues.append(_issue(transaction, "warning", f"Unknown action: {transaction.action_raw}", "action", transaction.action_raw))


def _issue(transaction: Transaction, severity: str, message: str, field: str, value: Any) -> ValidationIssue:
    return ValidationIssue(
        severity=severity,
        message=message,
        source_file=transaction.source_file,
        sheet=transaction.sheet,
        row_number=transaction.row_number,
        field=field,
        value=value,
    )


def _row_to_dict(row: pd.Series) -> dict[str, Any]:
    return {str(key): _serialize(value) for key, value in row.to_dict().items() if pd.notna(value)}


def _clean_header(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    if text.endswith(".0") and text[:-2].isdigit():
        return text[:-2]
    return text


def _num(value: Any) -> float:
    if value is None or pd.isna(value) or value == "":
        return 0.0
    if isinstance(value, str):
        value = value.replace(",", "").replace(" ", "")
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _optional_num(value: Any) -> float | None:
    if value is None or pd.isna(value) or value == "":
        return None
    return _num(value)


def _is_missing(value: Any) -> bool:
    return value is None or value == "" or pd.isna(value)


def _parse_date(value: Any, day_first: bool = False) -> datetime | None:
    if value is None or pd.isna(value) or value == "":
        return None
    if isinstance(value, datetime):
        return value
    parsed = pd.to_datetime(value, dayfirst=day_first, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.to_pydatetime()


def _normalize_currency(value: Any) -> str:
    text = _text(value)
    mapping = {
        "דולר": "USD",
        "ד.קנדי": "CAD",
        'ש"ח': "ILS",
        "שח": "ILS",
        "USD": "USD",
        "ILS": "ILS",
    }
    return mapping.get(text, text or "UNKNOWN")


def _serialize(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if pd.isna(value):
        return None
    return value
