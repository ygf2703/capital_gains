from __future__ import annotations

import re
from calendar import monthrange
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime

from .dashboard import build_dashboard_summary
from .models import CalculationResult, Lot, RealizedMatch, Transaction


@dataclass(frozen=True, slots=True)
class QAContext:
    security_name: str = ""
    start_date: date | None = None
    end_date: date | None = None


def answer_report_question(result: CalculationResult | None, question: str) -> str:
    if result is None:
        return "קודם צריך לנתח לפחות קובץ אחד, ואז אוכל לענות מתוך הנתונים שלו."

    summary = build_dashboard_summary(result)
    normalized = question.strip().lower()
    if not normalized:
        return _default_answer(summary, result)

    comparison = _extract_comparison_candidates(result, normalized)
    if comparison:
        return _answer_comparison(result, comparison[0], comparison[1])

    context = _extract_context(result, normalized)
    if _looks_like_anomaly_question(normalized):
        return _answer_anomaly(result, context)
    if any(token in normalized for token in ("התרא", "שגיא", "issue", "warning", "בעיה", "חריג")):
        return _answer_issues(result, context)
    if any(token in normalized for token in ("פתוח", "open", "פוזיצ")):
        return _answer_open_positions(result, context)
    if any(token in normalized for token in ("רווח", "הפסד", "gain", "profit", "loss")):
        return _answer_gain(result, summary, context)
    if any(token in normalized for token in ("תנוע", "transaction", "עסק", "מכירות", "קניות")):
        return _answer_transaction_count(result, context)
    if any(token in normalized for token in ("דולר", "usd", "שער", "exchange")):
        return _answer_exchange_rate(result)
    if any(token in normalized for token in ("פיפו", "fifo", "מימוש")):
        return _answer_fifo_rows(result, context)
    if any(token in normalized for token in ("נייר", "security", "מניה", "ticker")):
        return _answer_security_overview(result, summary, context)
    if any(token in normalized for token in ("תובנ", "summary", "סיכום")):
        return _default_answer(summary, result)

    return (
        _default_answer(summary, result)
        + " אפשר לשאול גם על נייר מסוים, טווח תאריכים, השוואה בין שני ניירות, פוזיציות פתוחות או חריגות."
    )


def _answer_gain(result: CalculationResult, summary, context: QAContext) -> str:
    realized = _filtered_realized(result, context)
    if context.security_name or context.start_date or context.end_date:
        if not realized:
            return f"לא מצאתי רווח/הפסד ממומש עבור {_context_label(context)}."
        totals = _gain_by_currency(realized)
        totals_text = ", ".join(f"{currency}: {value:,.2f}" for currency, value in totals.items())
        return f"הרווח/ההפסד הממומש עבור {_context_label(context)} הוא {totals_text}."

    totals = ", ".join(f"{currency}: {value:,.2f}" for currency, value in summary.gain_by_currency) or "אין רווח ממומש"
    return f"סך הרווח/ההפסד הממומש לפי פיפו הוא {totals}."


def _answer_transaction_count(result: CalculationResult, context: QAContext) -> str:
    transactions = _filtered_transactions(result, context)
    if not transactions:
        return f"לא מצאתי תנועות עבור {_context_label(context)}."

    buys = sum(1 for tx in transactions if tx.action_type.value == "BUY")
    sells = sum(1 for tx in transactions if tx.action_type.value == "SELL")
    return (
        f"עבור {_context_label(context)} נמצאו {len(transactions):,} תנועות: "
        f"{buys:,} קניות ו-{sells:,} מכירות."
    )


def _answer_security_overview(result: CalculationResult, summary, context: QAContext) -> str:
    if context.security_name:
        transactions = _filtered_transactions(result, context)
        realized = _filtered_realized(result, context)
        open_lots = _filtered_open_lots(result, context)
        if not transactions and not realized and not open_lots:
            return f"לא מצאתי נתונים עבור הנייר {context.security_name}."
        gain_totals = _gain_by_currency(realized)
        gain_text = ", ".join(f"{currency}: {value:,.2f}" for currency, value in gain_totals.items()) or "אין רווח ממומש"
        open_qty = sum(lot.quantity for lot in open_lots)
        return (
            f"עבור {context.security_name} נמצאו {len(transactions):,} תנועות, "
            f"{len(realized):,} שורות FIFO ורווח/הפסד ממומש {gain_text}. "
            f"כמות פתוחה נוכחית: {open_qty:,.4f}."
        )

    top = summary.top_securities[0][0] if summary.top_securities else "אין עדיין נייר ממומש בולט"
    return f"זוהו {summary.unique_securities:,} ניירות ערך. הנייר הבולט כרגע הוא {top}."


def _answer_open_positions(result: CalculationResult, context: QAContext) -> str:
    open_lots = _filtered_open_lots(result, context)
    if not open_lots:
        return f"אין פוזיציות פתוחות עבור {_context_label(context)}."
    grouped: dict[str, float] = defaultdict(float)
    for lot in open_lots:
        grouped[_lot_label(lot)] += lot.quantity
    largest = sorted(grouped.items(), key=lambda item: abs(item[1]), reverse=True)[:3]
    details = ", ".join(f"{label}: {qty:,.4f}" for label, qty in largest)
    return f"יש {len(open_lots):,} פוזיציות פתוחות עבור {_context_label(context)}. הגדולות שבהן: {details}."


def _answer_issues(result: CalculationResult, context: QAContext) -> str:
    issues = result.issues
    if context.security_name:
        issues = [
            issue
            for issue in issues
            if context.security_name.lower() in str(issue.value or "").lower()
            or context.security_name.lower() in issue.message.lower()
        ]
    if not issues:
        return f"לא זוהו התראות או חריגות עבור {_context_label(context)}."
    sample = "; ".join(issue.message for issue in issues[:3])
    return f"זוהו {len(issues):,} התראות עבור {_context_label(context)}. דוגמאות: {sample}."


def _answer_exchange_rate(result: CalculationResult) -> str:
    if not result.exchange_rate:
        return "עדיין לא נטען שער דולר לחישוב הזה."
    rate = result.exchange_rate
    return (
        f"שער הדולר שנשמר עם החישוב הוא {rate.rate:.4f}, פורסם ב-{rate.published_date:%Y-%m-%d} "
        f"עבור תאריך מבוקש {rate.requested_date:%Y-%m-%d}."
    )


def _answer_fifo_rows(result: CalculationResult, context: QAContext) -> str:
    realized = _filtered_realized(result, context)
    if not realized:
        return f"לא מצאתי שורות FIFO עבור {_context_label(context)}."
    return f"נוצרו {len(realized):,} שורות FIFO עבור {_context_label(context)}."


def _answer_comparison(result: CalculationResult, left_name: str, right_name: str) -> str:
    left_context = QAContext(security_name=left_name)
    right_context = QAContext(security_name=right_name)
    left_realized = _filtered_realized(result, left_context)
    right_realized = _filtered_realized(result, right_context)
    left_transactions = _filtered_transactions(result, left_context)
    right_transactions = _filtered_transactions(result, right_context)

    if not left_transactions and not right_transactions:
        return f"לא מצאתי נתונים להשוואה בין {left_name} לבין {right_name}."

    left_gain = sum(row.gain_loss for row in left_realized)
    right_gain = sum(row.gain_loss for row in right_realized)
    left_open = sum(lot.quantity for lot in _filtered_open_lots(result, left_context))
    right_open = sum(lot.quantity for lot in _filtered_open_lots(result, right_context))

    winner = left_name if left_gain >= right_gain else right_name
    return (
        f"השוואה בין {left_name} ל-{right_name}: "
        f"{left_name} עם {len(left_transactions):,} תנועות, רווח/הפסד {left_gain:,.2f}, כמות פתוחה {left_open:,.4f}; "
        f"{right_name} עם {len(right_transactions):,} תנועות, רווח/הפסד {right_gain:,.2f}, כמות פתוחה {right_open:,.4f}. "
        f"כרגע {winner} בולט יותר ברווח הממומש."
    )


def _answer_anomaly(result: CalculationResult, context: QAContext) -> str:
    realized = _filtered_realized(result, context)
    transactions = _filtered_transactions(result, context)
    open_lots = _filtered_open_lots(result, context)
    if not realized and not transactions and not open_lots:
        return f"לא מצאתי נתונים חריגים עבור {_context_label(context)}."

    gain_by_security: dict[str, float] = defaultdict(float)
    txn_counter: Counter[str] = Counter()
    for row in realized:
        gain_by_security[_realized_label(row)] += row.gain_loss
    for tx in transactions:
        txn_counter[_transaction_label(tx)] += 1

    insights: list[str] = []
    if gain_by_security:
        best = max(gain_by_security.items(), key=lambda item: item[1])
        worst = min(gain_by_security.items(), key=lambda item: item[1])
        insights.append(f"הנייר עם הרווח הגבוה ביותר הוא {best[0]} ({best[1]:,.2f}).")
        if worst[1] < 0:
            insights.append(f"הנייר עם ההפסד הגבוה ביותר הוא {worst[0]} ({worst[1]:,.2f}).")
    if txn_counter:
        busiest = txn_counter.most_common(1)[0]
        insights.append(f"הנייר הפעיל ביותר הוא {busiest[0]} עם {busiest[1]:,} תנועות.")
    if open_lots:
        largest = max(open_lots, key=lambda lot: abs(lot.quantity))
        insights.append(f"הפוזיציה הפתוחה הגדולה ביותר היא {_lot_label(largest)} עם {largest.quantity:,.4f}.")

    return " ".join(insights) if insights else f"לא זיהיתי חריגה בולטת עבור {_context_label(context)}."


def _default_answer(summary, result: CalculationResult) -> str:
    lines = [
        f"נותחו {summary.total_transactions:,} תנועות על פני {summary.unique_securities:,} ניירות ערך.",
        f"נוצרו {summary.realized_rows:,} שורות FIFO ויש {len(result.open_lots):,} פוזיציות פתוחות.",
    ]
    if summary.gain_by_currency:
        totals = ", ".join(f"{currency}: {value:,.2f}" for currency, value in summary.gain_by_currency)
        lines.append(f"רווח/הפסד ממומש: {totals}.")
    if result.issues:
        lines.append(f"יש גם {len(result.issues):,} התראות שכדאי לעבור עליהן.")
    return " ".join(lines)


def _extract_context(result: CalculationResult, question: str) -> QAContext:
    start_date, end_date = _extract_date_range(question)
    security_name = _extract_single_security(result, question)
    return QAContext(security_name=security_name, start_date=start_date, end_date=end_date)


def _extract_comparison_candidates(result: CalculationResult, question: str) -> tuple[str, str] | None:
    if not any(token in question for token in ("השווה", "compare", "לעומת", "מול", "versus", "vs")):
        return None
    labels = _all_security_labels(result)
    matches = [label for label in labels if label.lower() in question]
    unique_matches: list[str] = []
    for label in matches:
        if label not in unique_matches:
            unique_matches.append(label)
    if len(unique_matches) >= 2:
        return unique_matches[0], unique_matches[1]
    return None


def _extract_single_security(result: CalculationResult, question: str) -> str:
    labels = sorted(_all_security_labels(result), key=len, reverse=True)
    for label in labels:
        if label.lower() in question:
            return label
    return ""


def _extract_date_range(question: str) -> tuple[date | None, date | None]:
    full_dates = re.findall(r"\d{4}-\d{2}-\d{2}", question)
    if len(full_dates) >= 2:
        return _safe_date(full_dates[0]), _safe_date(full_dates[1])
    if len(full_dates) == 1:
        parsed = _safe_date(full_dates[0])
        return parsed, parsed

    year_month = re.findall(r"\d{4}-\d{2}", question)
    if year_month:
        year, month = [int(part) for part in year_month[0].split("-")]
        start = date(year, month, 1)
        end = date(year, month, monthrange(year, month)[1])
        return start, end
    return None, None


def _safe_date(value: str) -> date | None:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _filtered_transactions(result: CalculationResult, context: QAContext) -> list[Transaction]:
    rows = result.transactions
    if context.security_name:
        wanted = context.security_name.lower()
        rows = [row for row in rows if wanted in _transaction_label(row).lower()]
    if context.start_date:
        rows = [row for row in rows if row.trade_date.date() >= context.start_date]
    if context.end_date:
        rows = [row for row in rows if row.trade_date.date() <= context.end_date]
    return rows


def _filtered_realized(result: CalculationResult, context: QAContext) -> list[RealizedMatch]:
    rows = result.realized
    if context.security_name:
        wanted = context.security_name.lower()
        rows = [row for row in rows if wanted in _realized_label(row).lower()]
    if context.start_date:
        rows = [row for row in rows if row.sale_date.date() >= context.start_date]
    if context.end_date:
        rows = [row for row in rows if row.sale_date.date() <= context.end_date]
    return rows


def _filtered_open_lots(result: CalculationResult, context: QAContext) -> list[Lot]:
    rows = result.open_lots
    if context.security_name:
        wanted = context.security_name.lower()
        rows = [row for row in rows if wanted in _lot_label(row).lower()]
    return rows


def _gain_by_currency(rows: list[RealizedMatch]) -> dict[str, float]:
    totals: dict[str, float] = defaultdict(float)
    for row in rows:
        totals[row.currency or "UNKNOWN"] += row.gain_loss
    return totals


def _all_security_labels(result: CalculationResult) -> list[str]:
    labels: set[str] = set()
    for tx in result.transactions:
        for label in (tx.symbol, tx.security_name, tx.security_id):
            value = str(label).strip()
            if value:
                labels.add(value)
    return sorted(labels, key=lambda item: (len(item), item), reverse=True)


def _looks_like_anomaly_question(question: str) -> bool:
    return any(token in question for token in ("הכי", "בולט", "חריג", "גדול", "largest", "biggest", "top"))


def _transaction_label(tx: Transaction) -> str:
    return tx.symbol or tx.security_name or tx.security_id or tx.inventory_key


def _realized_label(row: RealizedMatch) -> str:
    return row.symbol or row.security_name or row.security_id or row.security_key


def _lot_label(lot: Lot) -> str:
    return lot.symbol or lot.security_name or lot.security_id or lot.security_key


def _context_label(context: QAContext) -> str:
    parts: list[str] = []
    if context.security_name:
        parts.append(context.security_name)
    if context.start_date and context.end_date:
        if context.start_date == context.end_date:
            parts.append(f"תאריך {context.start_date:%Y-%m-%d}")
        else:
            parts.append(f"טווח {context.start_date:%Y-%m-%d} עד {context.end_date:%Y-%m-%d}")
    elif context.start_date:
        parts.append(f"מתאריך {context.start_date:%Y-%m-%d}")
    elif context.end_date:
        parts.append(f"עד תאריך {context.end_date:%Y-%m-%d}")
    return " / ".join(parts) if parts else "הדוח הנוכחי"
