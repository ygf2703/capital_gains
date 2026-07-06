from __future__ import annotations

from .dashboard import build_dashboard_summary
from .models import CalculationResult


def answer_report_question(result: CalculationResult | None, question: str) -> str:
    if result is None:
        return "קודם צריך לנתח לפחות קובץ אחד, ואז אוכל לענות מתוך הנתונים שלו."

    summary = build_dashboard_summary(result)
    normalized = question.strip().lower()
    if not normalized:
        return _default_answer(summary, result)

    if any(token in normalized for token in ("רווח", "הפסד", "gain", "profit", "loss")):
        totals = ", ".join(f"{currency}: {value:,.2f}" for currency, value in summary.gain_by_currency) or "אין רווח ממומש"
        return f"סך הרווח/ההפסד הממומש לפי פיפו הוא {totals}."

    if any(token in normalized for token in ("תנוע", "transaction", "עסק")):
        return f"בקובץ נותחו {summary.total_transactions:,} תנועות."

    if any(token in normalized for token in ("נייר", "security", "מניה", "ticker")):
        top = summary.top_securities[0][0] if summary.top_securities else "אין עדיין נייר ממומש בולט"
        return f"זוהו {summary.unique_securities:,} ניירות ערך. הנייר הבולט כרגע הוא {top}."

    if any(token in normalized for token in ("פתוח", "open", "פוזיצ")):
        if not result.open_lots:
            return "אין פוזיציות פתוחות אחרי החישוב הנוכחי."
        largest = sorted(result.open_lots, key=lambda lot: abs(lot.quantity), reverse=True)[:3]
        details = ", ".join(
            f"{lot.symbol or lot.security_name or lot.security_id}: {lot.quantity:,.4f}" for lot in largest
        )
        return f"יש {len(result.open_lots):,} פוזיציות פתוחות. הגדולות שבהן: {details}."

    if any(token in normalized for token in ("התרא", "שגיא", "issue", "warning", "בעיה")):
        if not result.issues:
            return "לא זוהו התראות או שגיאות בדוח המחושב."
        sample = "; ".join(issue.message for issue in result.issues[:3])
        return f"זוהו {len(result.issues):,} התראות. דוגמאות: {sample}."

    if any(token in normalized for token in ("דולר", "usd", "שער", "exchange")):
        if not result.exchange_rate:
            return "עדיין לא נטען שער דולר לחישוב הזה."
        rate = result.exchange_rate
        return (
            f"שער הדולר שנשמר עם החישוב הוא {rate.rate:.4f}, פורסם ב-{rate.published_date:%Y-%m-%d} "
            f"עבור תאריך מבוקש {rate.requested_date:%Y-%m-%d}."
        )

    if any(token in normalized for token in ("פיפו", "fifo", "מימוש")):
        return f"נוצרו {summary.realized_rows:,} שורות FIFO ממומשות."

    if any(token in normalized for token in ("תובנ", "summary", "סיכום")):
        return _default_answer(summary, result)

    return (
        _default_answer(summary, result)
        + " אפשר לשאול גם על רווח, תנועות, ניירות, פוזיציות פתוחות, התראות או שער הדולר."
    )


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
