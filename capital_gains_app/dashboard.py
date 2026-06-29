from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass

from .models import CalculationResult


@dataclass(slots=True)
class DashboardSummary:
    total_transactions: int
    unique_securities: int
    realized_rows: int
    open_lots: int
    corporate_actions: int
    issue_count: int
    inferred_rows: int
    gain_by_currency: list[tuple[str, float]]
    proceeds_by_currency: list[tuple[str, float]]
    action_counts: list[tuple[str, int]]
    top_securities: list[tuple[str, str, float]]
    key_insights: list[str]


def build_dashboard_summary(result: CalculationResult) -> DashboardSummary:
    gain_by_currency: dict[str, float] = defaultdict(float)
    proceeds_by_currency: dict[str, float] = defaultdict(float)
    gain_by_security: dict[tuple[str, str], float] = defaultdict(float)
    action_counter: Counter[str] = Counter()
    security_keys: set[str] = set()
    inferred_rows = 0

    for row in result.realized:
        currency = row.currency or "UNKNOWN"
        label = row.symbol or row.security_name or row.security_key
        security_keys.add(row.security_key)
        gain_by_currency[currency] += row.gain_loss
        proceeds_by_currency[currency] += row.proceeds
        gain_by_security[(label, currency)] += row.gain_loss
        if row.inferred:
            inferred_rows += 1

    for row in result.transactions:
        action_counter[row.action_type.value] += 1
        security_keys.add(row.inventory_key)

    top_securities = sorted(
        ((label, currency, value) for (label, currency), value in gain_by_security.items()),
        key=lambda item: abs(item[2]),
        reverse=True,
    )[:8]
    key_insights = _build_key_insights(
        total_transactions=len(result.transactions),
        unique_securities=len(security_keys),
        open_lots=len(result.open_lots),
        corporate_actions=len(result.corporate_actions),
        issue_count=len(result.issues),
        inferred_rows=inferred_rows,
        gain_by_currency=sorted(gain_by_currency.items()),
        proceeds_by_currency=sorted(proceeds_by_currency.items()),
        top_securities=top_securities,
    )

    return DashboardSummary(
        total_transactions=len(result.transactions),
        unique_securities=len(security_keys),
        realized_rows=len(result.realized),
        open_lots=len(result.open_lots),
        corporate_actions=len(result.corporate_actions),
        issue_count=len(result.issues),
        inferred_rows=inferred_rows,
        gain_by_currency=sorted(gain_by_currency.items()),
        proceeds_by_currency=sorted(proceeds_by_currency.items()),
        action_counts=action_counter.most_common(8),
        top_securities=top_securities,
        key_insights=key_insights,
    )


def _build_key_insights(
    total_transactions: int,
    unique_securities: int,
    open_lots: int,
    corporate_actions: int,
    issue_count: int,
    inferred_rows: int,
    gain_by_currency: list[tuple[str, float]],
    proceeds_by_currency: list[tuple[str, float]],
    top_securities: list[tuple[str, str, float]],
) -> list[str]:
    insights: list[str] = []

    if gain_by_currency:
        total_text = ", ".join(f"{currency}: {_money(value)}" for currency, value in gain_by_currency)
        insights.append(f"סך הרווח/הפסד המחושב לפי פיפו: {total_text}.")
    else:
        insights.append("לא נמצאו מכירות שמייצרות שורות פיפו בדוח הנוכחי.")

    if top_securities:
        best = max(top_securities, key=lambda item: item[2])
        worst = min(top_securities, key=lambda item: item[2])
        if worst[2] < 0:
            insights.append(
                f"הנייר הבולט ברווח הוא {best[0]} ({_money(best[2])} {best[1]}), והבולט בהפסד הוא {worst[0]} ({_money(worst[2])} {worst[1]})."
            )
        else:
            insights.append(f"הנייר הבולט ברווח הוא {best[0]} עם {_money(best[2])} {best[1]}; לא זוהה נייר עם הפסד ממומש.")
    else:
        insights.append("אין עדיין נייר בולט ברווח או הפסד, כי אין מכירות ממומשות.")

    if proceeds_by_currency:
        largest_proceeds = max(proceeds_by_currency, key=lambda item: abs(item[1]))
        insights.append(f"עיקר התמורה ממכירות נרשמה במטבע {largest_proceeds[0]}: {_money(largest_proceeds[1])}.")
    else:
        insights.append("לא נמצאה תמורה ממכירות בדוח.")

    if issue_count or inferred_rows:
        insights.append(
            f"יש {issue_count:,} התראות, מתוכן {inferred_rows:,} שורות עם עלות פתיחה מוסקת; מומלץ לבדוק אותן לפני שימוש מס."
        )
    elif corporate_actions:
        insights.append(f"זוהו {corporate_actions:,} אירועי הון שטופלו בחישוב.")
    else:
        insights.append("לא זוהו התראות או חריגים משמעותיים בחישוב.")

    if unique_securities == 1:
        insights.append(f"הדוח מתמקד בנייר ערך אחד בלבד, עם {total_transactions:,} תנועות ו-{open_lots:,} פוזיציות פתוחות.")
    else:
        insights.append(f"הדוח כולל {unique_securities:,} ניירות ערך, {total_transactions:,} תנועות ו-{open_lots:,} פוזיציות פתוחות.")

    return insights[:5]


def _money(value: float) -> str:
    return f"{value:,.2f}"
