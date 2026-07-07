from __future__ import annotations

import re
from calendar import monthrange
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime

from .dashboard import DashboardSummary, build_dashboard_summary
from .models import CalculationResult, CorporateActionRecord, Lot, RealizedMatch, Transaction, ValidationIssue


@dataclass(frozen=True, slots=True)
class QAContext:
    security_name: str = ""
    start_date: date | None = None
    end_date: date | None = None


@dataclass(frozen=True, slots=True)
class QAEvidence:
    title: str
    detail: str
    location: str = ""


@dataclass(frozen=True, slots=True)
class QAResponse:
    answer: str
    evidence: list[QAEvidence]


def suggested_report_questions(result: CalculationResult | None) -> list[str]:
    generic = [
        "תן לי 5 תובנות מרכזיות",
        "מה הרווח הכולל?",
        "אילו פוזיציות נשארו פתוחות?",
        "מה עוד חשוב לבדוק מעבר למסך הראשי?",
    ]
    if result is None:
        return generic

    summary = build_dashboard_summary(result)
    suggestions: list[str] = []

    def add(question: str) -> None:
        if question and question not in suggestions:
            suggestions.append(question)

    add("תן לי 5 תובנות מרכזיות")
    if summary.gain_by_currency:
        add("מה הרווח הכולל?")
    if result.open_lots:
        add("אילו פוזיציות נשארו פתוחות?")
    if result.issues or any(row.inferred for row in result.realized):
        add("אילו חריגות או נתונים חסרים קיימים?")
    if result.corporate_actions:
        add("היו אירועי הון בקובץ?")

    comparison = _build_comparison_prompt(result)
    if comparison:
        add(comparison)

    labels = _all_security_labels(result)
    if len(labels) == 1:
        add(f"מה מצב הנייר {labels[0]}?")

    add("תן לי פילוח פעילות לפי סוגי פעולה")
    if result.exchange_rate:
        add("איזה שער דולר שימש בחישוב?")
    add("מה עוד חשוב לבדוק מעבר למסך הראשי?")

    return suggestions[:6] or generic


def answer_report_question(result: CalculationResult | None, question: str) -> str:
    return answer_report_question_with_evidence(result, question).answer


def answer_report_question_with_evidence(result: CalculationResult | None, question: str) -> QAResponse:
    if result is None:
        return QAResponse("קודם צריך לנתח לפחות קובץ אחד, ואז אוכל לענות מתוך הנתונים שלו.", [])

    summary = build_dashboard_summary(result)
    normalized = question.strip().lower()
    if not normalized:
        return _default_answer(summary, result)

    comparison = _extract_comparison_candidates(result, normalized)
    if comparison:
        return _answer_comparison(result, comparison[0], comparison[1])

    context = _extract_context(result, normalized)
    if _contains_any(normalized, ("תובנ", "insight", "takeaway", "מרכזי", "מה חשוב")):
        return _answer_key_insights(summary)
    if _contains_any(normalized, ("לא הוצג", "לא מוצג", "חסר", "missing", "מעבר למסך", "מה עוד", "עוד כדאי", "עוד חשוב")):
        return _answer_hidden_data(result, summary, context)
    if _contains_any(normalized, ("אירוע הון", "אירועי הון", "איחוד", "פיצול", "reverse split", "split", "corporate")):
        return _answer_corporate_actions(result, context)
    if _looks_like_anomaly_question(normalized):
        return _answer_anomaly(result, context)
    if _contains_any(normalized, ("התרא", "שגיא", "issue", "warning", "בעיה", "חריג")):
        return _answer_issues(result, context)
    if _contains_any(normalized, ("פתוח", "open", "פוזיצ")):
        return _answer_open_positions(result, context)
    if _contains_any(normalized, ("רווח", "הפסד", "gain", "profit", "loss")):
        return _answer_gain(result, summary, context)
    if _contains_any(normalized, ("פילוח", "פירוט", "breakdown", "activity", "פעיל", "הרכב")):
        return _answer_activity(result, context)
    if _contains_any(normalized, ("תנוע", "transaction", "עסק", "מכירות", "קניות")):
        return _answer_transaction_count(result, context)
    if _contains_any(normalized, ("דולר", "usd", "שער", "exchange")):
        return _answer_exchange_rate(result)
    if _contains_any(normalized, ("פיפו", "fifo", "מימוש")):
        return _answer_fifo_rows(result, context)
    if _contains_any(normalized, ("נייר", "security", "מניה", "ticker")):
        return _answer_security_overview(result, summary, context)
    if _contains_any(normalized, ("summary", "סיכום")):
        return _default_answer(summary, result)

    default_response = _default_answer(summary, result)
    return _response(
        default_response.answer
        + " אפשר לשאול גם על נייר מסוים, טווח תאריכים, השוואה בין שני ניירות, פוזיציות פתוחות, חריגות, פילוח פעילות או נתונים שלא הוצגו במסך הראשי.",
        default_response.evidence,
    )


def _answer_key_insights(summary: DashboardSummary) -> QAResponse:
    lines = [f"{index}. {insight}" for index, insight in enumerate(summary.key_insights, start=1)]
    return _response("5 תובנות מרכזיות:\n" + "\n".join(lines))


def _answer_gain(result: CalculationResult, summary: DashboardSummary, context: QAContext) -> QAResponse:
    realized = _filtered_realized(result, context)
    if context.security_name or context.start_date or context.end_date:
        if not realized:
            return _response(f"לא מצאתי רווח/הפסד ממומש עבור {_context_label(context)}.")
        totals = _gain_by_currency(realized)
        totals_text = _format_currency_totals(totals.items())
        return _response(
            f"הרווח/ההפסד הממומש עבור {_context_label(context)} הוא {totals_text}.",
            _evidence_from_realized(realized),
        )

    totals = _format_currency_totals(summary.gain_by_currency) or "אין רווח ממומש"
    return _response(f"סך הרווח/ההפסד הממומש לפי פיפו הוא {totals}.", _evidence_from_realized(result.realized))


def _answer_transaction_count(result: CalculationResult, context: QAContext) -> QAResponse:
    transactions = _filtered_transactions(result, context)
    if not transactions:
        return _response(f"לא מצאתי תנועות עבור {_context_label(context)}.")

    buys = sum(1 for tx in transactions if tx.action_type.value == "BUY")
    sells = sum(1 for tx in transactions if tx.action_type.value == "SELL")
    return _response(
        f"עבור {_context_label(context)} נמצאו {len(transactions):,} תנועות: "
        f"{buys:,} קניות ו-{sells:,} מכירות.",
        _evidence_from_transactions(transactions),
    )


def _answer_activity(result: CalculationResult, context: QAContext) -> QAResponse:
    transactions = _filtered_transactions(result, context)
    if not transactions:
        return _response(f"לא מצאתי תנועות עבור {_context_label(context)}.")

    action_counts: Counter[str] = Counter(tx.action_type.value for tx in transactions)
    security_counts: Counter[str] = Counter(_transaction_label(tx) for tx in transactions)
    breakdown = ", ".join(
        f"{count:,} {_action_label(action)}"
        for action, count in sorted(action_counts.items(), key=lambda item: (-item[1], item[0]))
        if count
    )
    first_date = min(tx.trade_date for tx in transactions).date()
    last_date = max(tx.trade_date for tx in transactions).date()
    busiest = security_counts.most_common(1)[0] if security_counts else None

    lines = [
        f"פילוח הפעילות עבור {_context_label(context)}: {breakdown}.",
        f"טווח הפעילות שנמצא: {first_date:%Y-%m-%d} עד {last_date:%Y-%m-%d}.",
    ]
    if busiest and not context.security_name:
        lines.append(f"הנייר הפעיל ביותר בטווח הזה הוא {busiest[0]} עם {busiest[1]:,} תנועות.")
    return _response(" ".join(lines), _evidence_from_transactions(transactions))


def _answer_security_overview(result: CalculationResult, summary: DashboardSummary, context: QAContext) -> QAResponse:
    if context.security_name:
        transactions = _filtered_transactions(result, context)
        realized = _filtered_realized(result, context)
        open_lots = _filtered_open_lots(result, context)
        if not transactions and not realized and not open_lots:
            return _response(f"לא מצאתי נתונים עבור הנייר {context.security_name}.")
        gain_totals = _gain_by_currency(realized)
        gain_text = _format_currency_totals(gain_totals.items()) or "אין רווח ממומש"
        open_qty = sum(lot.quantity for lot in open_lots)
        return _response(
            f"עבור {context.security_name} נמצאו {len(transactions):,} תנועות, "
            f"{len(realized):,} שורות FIFO ורווח/הפסד ממומש {gain_text}. "
            f"כמות פתוחה נוכחית: {open_qty:,.4f}.",
            _merge_evidence(
                _evidence_from_transactions(transactions, limit=2),
                _evidence_from_realized(realized, limit=2),
                _evidence_from_open_lots(open_lots, limit=1),
            ),
        )

    top = summary.top_securities[0][0] if summary.top_securities else "אין עדיין נייר ממומש בולט"
    return _response(
        f"זוהו {summary.unique_securities:,} ניירות ערך. הנייר הבולט כרגע הוא {top}.",
        _evidence_from_transactions(result.transactions, limit=3),
    )


def _answer_open_positions(result: CalculationResult, context: QAContext) -> QAResponse:
    open_lots = _filtered_open_lots(result, context)
    if not open_lots:
        return _response(f"אין פוזיציות פתוחות עבור {_context_label(context)}.")
    grouped: dict[str, float] = defaultdict(float)
    for lot in open_lots:
        grouped[_lot_label(lot)] += lot.quantity
    largest = sorted(grouped.items(), key=lambda item: abs(item[1]), reverse=True)[:3]
    details = ", ".join(f"{label}: {qty:,.4f}" for label, qty in largest)
    return _response(
        f"יש {len(open_lots):,} פוזיציות פתוחות עבור {_context_label(context)}. הגדולות שבהן: {details}.",
        _evidence_from_open_lots(open_lots),
    )


def _answer_issues(result: CalculationResult, context: QAContext) -> QAResponse:
    issues = _filtered_issues(result, context)
    if not issues:
        return _response(f"לא זוהו התראות או חריגות עבור {_context_label(context)}.")
    sample = "; ".join(issue.message for issue in issues[:3])
    return _response(
        f"זוהו {len(issues):,} התראות עבור {_context_label(context)}. דוגמאות: {sample}.",
        _evidence_from_issues(issues),
    )


def _answer_exchange_rate(result: CalculationResult) -> QAResponse:
    if not result.exchange_rate:
        return _response("עדיין לא נטען שער דולר לחישוב הזה.")
    rate = result.exchange_rate
    return _response(
        f"שער הדולר שנשמר עם החישוב הוא {rate.rate:.4f}, פורסם ב-{rate.published_date:%Y-%m-%d} "
        f"עבור תאריך מבוקש {rate.requested_date:%Y-%m-%d}.",
        [
            QAEvidence(
                title="שער דולר",
                detail=f"שער {rate.rate:.4f} עבור {rate.currency_pair}, מבוקש {rate.requested_date:%Y-%m-%d}, פורסם {rate.published_date:%Y-%m-%d}.",
                location=rate.source,
            )
        ],
    )


def _answer_fifo_rows(result: CalculationResult, context: QAContext) -> QAResponse:
    realized = _filtered_realized(result, context)
    if not realized:
        return _response(f"לא מצאתי שורות FIFO עבור {_context_label(context)}.")
    return _response(
        f"נוצרו {len(realized):,} שורות FIFO עבור {_context_label(context)}.",
        _evidence_from_realized(realized),
    )


def _answer_comparison(result: CalculationResult, left_name: str, right_name: str) -> QAResponse:
    left_context = QAContext(security_name=left_name)
    right_context = QAContext(security_name=right_name)
    left_realized = _filtered_realized(result, left_context)
    right_realized = _filtered_realized(result, right_context)
    left_transactions = _filtered_transactions(result, left_context)
    right_transactions = _filtered_transactions(result, right_context)

    if not left_transactions and not right_transactions:
        return _response(f"לא מצאתי נתונים להשוואה בין {left_name} לבין {right_name}.")

    left_gain = sum(row.gain_loss for row in left_realized)
    right_gain = sum(row.gain_loss for row in right_realized)
    left_open = sum(lot.quantity for lot in _filtered_open_lots(result, left_context))
    right_open = sum(lot.quantity for lot in _filtered_open_lots(result, right_context))

    winner = left_name if left_gain >= right_gain else right_name
    return _response(
        f"השוואה בין {left_name} ל-{right_name}: "
        f"{left_name} עם {len(left_transactions):,} תנועות, רווח/הפסד {left_gain:,.2f}, כמות פתוחה {left_open:,.4f}; "
        f"{right_name} עם {len(right_transactions):,} תנועות, רווח/הפסד {right_gain:,.2f}, כמות פתוחה {right_open:,.4f}. "
        f"כרגע {winner} בולט יותר ברווח הממומש.",
        _merge_evidence(
            _evidence_from_realized(left_realized, limit=2),
            _evidence_from_realized(right_realized, limit=2),
        ),
    )


def _answer_anomaly(result: CalculationResult, context: QAContext) -> QAResponse:
    realized = _filtered_realized(result, context)
    transactions = _filtered_transactions(result, context)
    open_lots = _filtered_open_lots(result, context)
    if not realized and not transactions and not open_lots:
        return _response(f"לא מצאתי נתונים חריגים עבור {_context_label(context)}.")

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

    if insights:
        return _response(
            " ".join(insights),
            _merge_evidence(
                _evidence_from_realized(realized, limit=2),
                _evidence_from_transactions(transactions, limit=1),
                _evidence_from_open_lots(open_lots, limit=1),
            ),
        )
    return _response(f"לא זיהיתי חריגה בולטת עבור {_context_label(context)}.")


def _answer_hidden_data(result: CalculationResult, summary: DashboardSummary, context: QAContext) -> QAResponse:
    issues = _filtered_issues(result, context)
    inferred_rows = [row for row in _filtered_realized(result, context) if row.inferred]
    open_lots = _filtered_open_lots(result, context)
    corporate_actions = _filtered_corporate_actions(result, context)

    lines: list[str] = []
    if issues:
        lines.append(f"יש {len(issues):,} התראות שכדאי לעבור עליהן ידנית.")
    if inferred_rows:
        lines.append(f"זוהו {len(inferred_rows):,} שורות FIFO עם עלות פתיחה מוסקת, ולכן כדאי לאמת את בסיס העלות.")
    if corporate_actions:
        lines.append(f"טופלו {len(corporate_actions):,} אירועי הון שלא מוצגים במלוא הפירוט בכרטיסי הסיכום.")
    if open_lots:
        lines.append(f"יש עוד {len(open_lots):,} פוזיציות פתוחות שאפשר לפרק לפי נייר וכמות.")
    if len(summary.gain_by_currency) > 1 and not context.security_name:
        lines.append(f"הרווחים מחולקים על פני {len(summary.gain_by_currency):,} מטבעות שונים.")
    if result.exchange_rate and not context.security_name:
        lines.append(
            f"החישוב השתמש גם בשער דולר {result.exchange_rate.rate:.4f} שפורסם ב-{result.exchange_rate.published_date:%Y-%m-%d}."
        )

    if not lines:
        return _response(f"מעבר למסך הראשי לא זיהיתי כרגע שכבת מידע נוספת שחייבת תשומת לב עבור {_context_label(context)}.")
    return _response(
        "מעבר לכרטיסים ולגרפים במסך, יש עוד מידע שכדאי לשים לב אליו: " + " ".join(lines),
        _merge_evidence(
            _evidence_from_issues(issues, limit=2),
            _evidence_from_realized(inferred_rows, limit=2),
            _evidence_from_corporate_actions(corporate_actions, limit=2),
            _evidence_from_open_lots(open_lots, limit=1),
        ),
    )


def _answer_corporate_actions(result: CalculationResult, context: QAContext) -> QAResponse:
    actions = _filtered_corporate_actions(result, context)
    if not actions:
        return _response(f"לא זוהו אירועי הון עבור {_context_label(context)}.")

    samples = []
    for action in actions[:3]:
        ratio_text = f"יחס {action.ratio:.4f}" if action.ratio else f"כמות {action.old_quantity:,.4f} -> {action.new_quantity:,.4f}"
        samples.append(f"{action.action_date:%Y-%m-%d}: {_corporate_action_label(action.action_type)} ({ratio_text})")
    details = "; ".join(samples)
    return _response(
        f"זוהו {len(actions):,} אירועי הון עבור {_context_label(context)}. דוגמאות: {details}.",
        _evidence_from_corporate_actions(actions),
    )


def _default_answer(summary: DashboardSummary, result: CalculationResult) -> QAResponse:
    lines = [
        f"נותחו {summary.total_transactions:,} תנועות על פני {summary.unique_securities:,} ניירות ערך.",
        f"נוצרו {summary.realized_rows:,} שורות FIFO ויש {len(result.open_lots):,} פוזיציות פתוחות.",
    ]
    if summary.gain_by_currency:
        totals = _format_currency_totals(summary.gain_by_currency)
        lines.append(f"רווח/הפסד ממומש: {totals}.")
    if result.issues:
        lines.append(f"יש גם {len(result.issues):,} התראות שכדאי לעבור עליהן.")
    return _response(
        " ".join(lines),
        _merge_evidence(
            _evidence_from_transactions(result.transactions, limit=2),
            _evidence_from_realized(result.realized, limit=2),
            _evidence_from_issues(result.issues, limit=1),
        ),
    )


def _extract_context(result: CalculationResult, question: str) -> QAContext:
    start_date, end_date = _extract_date_range(question)
    security_name = _extract_single_security(result, question)
    return QAContext(security_name=security_name, start_date=start_date, end_date=end_date)


def _extract_comparison_candidates(result: CalculationResult, question: str) -> tuple[str, str] | None:
    if not _contains_any(question, ("השווה", "compare", "לעומת", "מול", "versus", "vs")):
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


def _filtered_issues(result: CalculationResult, context: QAContext) -> list[ValidationIssue]:
    rows = result.issues
    if context.security_name:
        wanted = context.security_name.lower()
        rows = [
            issue
            for issue in rows
            if wanted in str(issue.value or "").lower() or wanted in issue.message.lower()
        ]
    return rows


def _filtered_corporate_actions(result: CalculationResult, context: QAContext) -> list[CorporateActionRecord]:
    rows = result.corporate_actions
    if context.security_name:
        wanted = context.security_name.lower()
        rows = [
            row
            for row in rows
            if wanted in row.old_key.lower()
            or wanted in row.new_key.lower()
            or wanted in row.notes.lower()
        ]
    if context.start_date:
        rows = [row for row in rows if row.action_date.date() >= context.start_date]
    if context.end_date:
        rows = [row for row in rows if row.action_date.date() <= context.end_date]
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


def _build_comparison_prompt(result: CalculationResult) -> str:
    counts: Counter[str] = Counter(_transaction_label(tx) for tx in result.transactions)
    labels = [label for label, _count in counts.most_common(2)]
    if len(labels) == 2:
        return f"השווה בין {labels[0]} ל-{labels[1]}"
    return ""


def _looks_like_anomaly_question(question: str) -> bool:
    return _contains_any(question, ("הכי", "בולט", "חריג", "גדול", "largest", "biggest", "top"))


def _contains_any(text: str, tokens: tuple[str, ...]) -> bool:
    return any(token in text for token in tokens)


def _response(answer: str, evidence: list[QAEvidence] | None = None) -> QAResponse:
    return QAResponse(answer=answer, evidence=_limit_evidence(evidence or []))


def _merge_evidence(*groups: list[QAEvidence]) -> list[QAEvidence]:
    merged: list[QAEvidence] = []
    seen: set[tuple[str, str, str]] = set()
    for group in groups:
        for item in group:
            key = (item.title, item.detail, item.location)
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
    return merged


def _limit_evidence(evidence: list[QAEvidence], limit: int = 4) -> list[QAEvidence]:
    return evidence[:limit]


def _format_currency_totals(rows) -> str:
    return ", ".join(f"{currency}: {value:,.2f}" for currency, value in rows)


def _evidence_from_transactions(rows: list[Transaction], limit: int = 4) -> list[QAEvidence]:
    ordered = sorted(rows, key=lambda row: (row.trade_date, row.row_number))
    evidence: list[QAEvidence] = []
    for row in ordered[:limit]:
        evidence.append(
            QAEvidence(
                title=f"{_action_label(row.action_type.value)} | {_transaction_label(row)}",
                detail=f"{row.trade_date:%Y-%m-%d}, כמות {row.absolute_quantity:,.4f}, מחיר {row.price:,.4f} {row.currency or ''}".strip(),
                location=_transaction_location(row),
            )
        )
    return evidence


def _evidence_from_realized(rows: list[RealizedMatch], limit: int = 4) -> list[QAEvidence]:
    ordered = sorted(rows, key=lambda row: (row.sale_date, row.sale_row))
    evidence: list[QAEvidence] = []
    for row in ordered[:limit]:
        buy_ref = f", קנייה משורה {row.buy_row}" if row.buy_row else ""
        evidence.append(
            QAEvidence(
                title=f"FIFO | {_realized_label(row)}",
                detail=f"מכירה {row.sale_date:%Y-%m-%d}, כמות {row.quantity:,.4f}, רווח/הפסד {row.gain_loss:,.2f} {row.currency}{buy_ref}.",
                location=_realized_location(row),
            )
        )
    return evidence


def _evidence_from_open_lots(rows: list[Lot], limit: int = 4) -> list[QAEvidence]:
    ordered = sorted(rows, key=lambda row: abs(row.quantity), reverse=True)
    evidence: list[QAEvidence] = []
    for row in ordered[:limit]:
        evidence.append(
            QAEvidence(
                title=f"פוזיציה פתוחה | {_lot_label(row)}",
                detail=f"כמות {row.quantity:,.4f}, עלות כוללת {row.total_cost:,.2f} {row.currency}, נרכשה ב-{row.acquired_date:%Y-%m-%d}.",
                location=_lot_location(row),
            )
        )
    return evidence


def _evidence_from_issues(rows: list[ValidationIssue], limit: int = 4) -> list[QAEvidence]:
    evidence: list[QAEvidence] = []
    for row in rows[:limit]:
        evidence.append(
            QAEvidence(
                title=f"התראה | {row.severity}",
                detail=row.message,
                location=_issue_location(row),
            )
        )
    return evidence


def _evidence_from_corporate_actions(rows: list[CorporateActionRecord], limit: int = 4) -> list[QAEvidence]:
    evidence: list[QAEvidence] = []
    for row in rows[:limit]:
        ratio_text = f"יחס {row.ratio:.4f}" if row.ratio else f"כמות {row.old_quantity:,.4f} -> {row.new_quantity:,.4f}"
        evidence.append(
            QAEvidence(
                title=f"אירוע הון | {_corporate_action_label(row.action_type)}",
                detail=f"{row.action_date:%Y-%m-%d}, {ratio_text}.",
                location=f"{row.source_file} | שורות {row.row_numbers}",
            )
        )
    return evidence


def _action_label(action: str) -> str:
    mapping = {
        "BUY": "קניות",
        "SELL": "מכירות",
        "TRANSFER_IN": "העברות פנימה",
        "TRANSFER_OUT": "העברות החוצה",
        "SPLIT_IN": "פיצולים פנימה",
        "SPLIT_OUT": "פיצולים החוצה",
        "CAPITAL_REDUCTION": "הפחתות הון",
        "EXPIRE": "פקיעות",
        "CASH": "תנועות מזומן",
        "IGNORE": "שורות מסוננות",
        "UNKNOWN": "שורות לא מזוהות",
    }
    return mapping.get(action, action)


def _corporate_action_label(action_type: str) -> str:
    normalized = action_type.replace("_", " ").strip().lower()
    mapping = {
        "split": "פיצול",
        "reverse split": "איחוד הון",
        "capital reduction": "הפחתת הון",
    }
    return mapping.get(normalized, action_type)


def _transaction_label(tx: Transaction) -> str:
    return tx.symbol or tx.security_name or tx.security_id or tx.inventory_key


def _transaction_location(tx: Transaction) -> str:
    return f"{tx.source_file} | {tx.sheet} | שורה {tx.row_number}"


def _realized_label(row: RealizedMatch) -> str:
    return row.symbol or row.security_name or row.security_id or row.security_key


def _realized_location(row: RealizedMatch) -> str:
    buy_ref = f" | קנייה שורה {row.buy_row}" if row.buy_row else ""
    return f"{row.sale_source_file} | מכירה שורה {row.sale_row}{buy_ref}"


def _lot_label(lot: Lot) -> str:
    return lot.symbol or lot.security_name or lot.security_id or lot.security_key


def _lot_location(lot: Lot) -> str:
    return f"{lot.source_file} | שורה {lot.source_row}"


def _issue_location(issue: ValidationIssue) -> str:
    return f"{issue.source_file} | {issue.sheet} | שורה {issue.row_number}"


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
