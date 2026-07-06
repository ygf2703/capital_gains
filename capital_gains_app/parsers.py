from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from openpyxl import load_workbook

from .models import ActionType, Transaction, ValidationIssue


@dataclass(frozen=True, slots=True)
class BrokerLayout:
    broker: str
    required_fields: tuple[str, ...]
    field_aliases: dict[str, tuple[str, ...]]


@dataclass(frozen=True, slots=True)
class HeaderDetection:
    header_row_index: int
    broker: str
    column_map: dict[str, str]
    confidence: float


BROKER_LAYOUTS = (
    BrokerLayout(
        broker="agis",
        required_fields=("trade_date", "action", "quantity", "net_amount"),
        field_aliases={
            "trade_date": ("Trade Date", "Execution Date", "Trade date", "Date"),
            "action": ("Transaction", "Action", "Activity"),
            "quantity": ("Quantity", "Qty", "Executed Quantity"),
            "price": ("Price ($)", "Price", "Trade Price"),
            "net_amount": ("Net Amount ($)", "Net Amount", "Net Proceeds"),
            "security_type": ("Security Type", "Type"),
            "settlement_date": ("Settlement Date", "Value Date"),
            "security_id": ("Cusip", "CUSIP", "Security ID", "ISIN"),
            "symbol": ("Security", "Symbol", "Ticker"),
            "security_name": ("Description", "Security Name", "Name"),
            "base_currency": ("Base Currency", "Currency", "Trade Currency"),
            "commission": ("Commissions ($)", "Commission", "Commissions"),
            "fees": ("Fees ($)", "Fees", "Other Fees"),
            "account_type": ("Account Type", "Account"),
        },
    ),
    BrokerLayout(
        broker="leumi",
        required_fields=("reference", "trade_date", "action", "quantity", "net_amount"),
        field_aliases={
            "reference": ("אסמכתא", "מספר אסמכתא", "אסמכתה"),
            "trade_date": ("תאריך ביצוע", "תאריך עסקה", "תאריך"),
            "action": ("פעולה", "סוג פעולה"),
            "security_id": ("מס' בורסה", "מספר בורסה", "מס' נייר", "מספר נייר"),
            "security_name": ('שם ני"ע', "שם נייר ערך", "שם נייר"),
            "quantity": ("כמות ביצוע", "כמות", "כמות נייר"),
            "price": ("שער ביצוע", "שער", "מחיר ביצוע"),
            "net_amount": ("תמורה נטו לפני מס", "תמורה נטו", "תמורה"),
            "currency": ("מטבע", "מטבע עסקה"),
            "commission": ("עמלות ודמי ניהול", "עמלות", "דמי ניהול"),
            "bank_reported_gain_loss": ("רווח/הפסד", "רווח הפסד", "רווח או הפסד"),
            "tax_rate": ("שעור המס", "שיעור המס"),
            "tax_withheld_local": ("מס שנוכה/הוחזר בארץ", "מס בארץ"),
            "tax_withheld_foreign": ('מס חו"ל בשקלים', "מס חול בשקלים"),
        },
    ),
)


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
    try:
        for sheet in workbook.worksheets:
            rows = list(sheet.iter_rows(values_only=True))
            detection = _detect_header(rows)
            if detection is None:
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

            headers = [_clean_header(v) for v in rows[detection.header_row_index - 1]]
            data_rows = rows[detection.header_row_index :]
            df = pd.DataFrame(data_rows, columns=headers)
            df = df.dropna(how="all")

            if detection.broker == "agis":
                parsed, sheet_issues = _parse_agis(df, path.name, sheet.title, detection)
            else:
                parsed, sheet_issues = _parse_leumi(df, path.name, sheet.title, detection)
            all_transactions.extend(parsed)
            issues.extend(sheet_issues)
    finally:
        workbook.close()

    return all_transactions, issues


def _detect_header(rows: list[tuple[Any, ...]]) -> HeaderDetection | None:
    for index, row in enumerate(rows, start=1):
        actual_headers = [_clean_header(v) for v in row if _clean_header(v)]
        normalized_map = {_normalize_header_text(header): header for header in actual_headers}
        for layout in BROKER_LAYOUTS:
            column_map = _match_layout(normalized_map, layout)
            if column_map is None:
                continue
            confidence = len(column_map) / len(layout.field_aliases)
            return HeaderDetection(index, layout.broker, column_map, confidence)
    return None


def _match_layout(normalized_map: dict[str, str], layout: BrokerLayout) -> dict[str, str] | None:
    column_map: dict[str, str] = {}
    for field_name, aliases in layout.field_aliases.items():
        matched_header = _find_matching_header(normalized_map, aliases)
        if matched_header:
            column_map[field_name] = matched_header
    if all(field_name in column_map for field_name in layout.required_fields):
        return column_map
    return None


def _find_matching_header(normalized_map: dict[str, str], aliases: tuple[str, ...]) -> str:
    for alias in aliases:
        actual = normalized_map.get(_normalize_header_text(alias))
        if actual:
            return actual
    return ""


def _parse_agis(df: pd.DataFrame, source_file: str, sheet: str, detection: HeaderDetection) -> tuple[list[Transaction], list[ValidationIssue]]:
    transactions: list[Transaction] = []
    issues: list[ValidationIssue] = []
    for position, row in df.iterrows():
        row_number = detection.header_row_index + 1 + int(position)
        action_raw = _text(_value(row, detection.column_map, "action"))
        trade_date = _parse_date(_value(row, detection.column_map, "trade_date"))
        quantity = _num(_value(row, detection.column_map, "quantity"))
        price_raw = _value(row, detection.column_map, "price")
        price = _num(price_raw)
        net_amount = _num(_value(row, detection.column_map, "net_amount"))
        security_type = _text(_value(row, detection.column_map, "security_type"))

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
            settlement_date=_parse_date(_value(row, detection.column_map, "settlement_date")),
            action_raw=action_raw,
            action_type=action_type,
            security_id=_text(_value(row, detection.column_map, "security_id")),
            symbol=_text(_value(row, detection.column_map, "symbol")),
            security_name=_text(_value(row, detection.column_map, "security_name")),
            quantity=quantity,
            price=price,
            currency=_normalize_currency(_value(row, detection.column_map, "base_currency")),
            report_currency=_normalize_currency(_value(row, detection.column_map, "base_currency")),
            commission=_num(_value(row, detection.column_map, "commission")),
            fees=_num(_value(row, detection.column_map, "fees")),
            net_amount=net_amount,
            account_type=_text(_value(row, detection.column_map, "account_type")),
            description=_text(_value(row, detection.column_map, "security_name")),
            raw=_row_to_dict(row),
        )
        _validate_transaction(transaction, issues)
        if transaction.action_type in {ActionType.BUY, ActionType.SELL} and _is_missing(price_raw):
            issues.append(_issue(transaction, "error", "Missing price", "price", price_raw))
        if transaction.action_type != ActionType.IGNORE:
            transactions.append(transaction)
    return transactions, issues


def _parse_leumi(df: pd.DataFrame, source_file: str, sheet: str, detection: HeaderDetection) -> tuple[list[Transaction], list[ValidationIssue]]:
    transactions: list[Transaction] = []
    issues: list[ValidationIssue] = []
    for position, row in df.iterrows():
        row_number = detection.header_row_index + 1 + int(position)
        action_raw = _text(_value(row, detection.column_map, "action"))
        trade_date = _parse_date(_value(row, detection.column_map, "trade_date"), day_first=True)
        security_id = _text(_value(row, detection.column_map, "security_id"))
        security_name = _text(_value(row, detection.column_map, "security_name"))
        quantity = _num(_value(row, detection.column_map, "quantity"))
        price_raw = _value(row, detection.column_map, "price")
        price = _num(price_raw)
        net_amount = _num(_value(row, detection.column_map, "net_amount"))

        if not action_raw or not trade_date:
            continue
        if str(_value(row, detection.column_map, "reference", "")).startswith("סה"):
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
            currency=_normalize_currency(_value(row, detection.column_map, "currency")),
            report_currency="ILS",
            commission=_num(_value(row, detection.column_map, "commission")),
            fees=0.0,
            net_amount=net_amount,
            bank_reported_gain_loss=_optional_num(_value(row, detection.column_map, "bank_reported_gain_loss")),
            tax_rate=_optional_num(_value(row, detection.column_map, "tax_rate")),
            tax_withheld_local=_optional_num(_value(row, detection.column_map, "tax_withheld_local")),
            tax_withheld_foreign=_optional_num(_value(row, detection.column_map, "tax_withheld_foreign")),
            reference=_text(_value(row, detection.column_map, "reference")),
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


def _normalize_header_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower()
    for marker in ('"', "'", "׳", "״"):
        text = text.replace(marker, "")
    return " ".join(text.split())


def _value(row: pd.Series, column_map: dict[str, str], field_name: str, default: Any = None) -> Any:
    header = column_map.get(field_name)
    if not header:
        return default
    return row.get(header, default)


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
