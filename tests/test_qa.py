from datetime import datetime
import unittest

from capital_gains_app.fifo import calculate_fifo
from capital_gains_app.models import ActionType, CorporateActionRecord, Transaction, ValidationIssue
from capital_gains_app.qa import answer_report_question, suggested_report_questions


def tx(row, trade_date, action, qty, price, net, symbol="AAA", security_name="Alpha Asset", security_id="AAA"):
    return Transaction(
        source_file="qa.xlsx",
        sheet="Sheet1",
        row_number=row,
        broker="Test",
        trade_date=datetime.fromisoformat(trade_date),
        action_raw=action.value,
        action_type=action,
        security_id=security_id,
        symbol=symbol,
        security_name=security_name,
        quantity=qty,
        price=price,
        currency="USD",
        report_currency="USD",
        net_amount=net,
    )


class ReportQATests(unittest.TestCase):
    def test_answers_question_about_transaction_count(self) -> None:
        result = calculate_fifo(
            [
                tx(1, "2024-01-01", ActionType.BUY, 10, 10, -100),
                tx(2, "2024-02-01", ActionType.SELL, -4, 15, 60),
            ]
        )

        answer = answer_report_question(result, "כמה תנועות יש בקובץ?")

        self.assertIn("2", answer)
        self.assertIn("תנועות", answer)

    def test_answers_when_no_result_is_loaded(self) -> None:
        answer = answer_report_question(None, "מה הרווח?")

        self.assertIn("קודם צריך לנתח", answer)

    def test_answers_for_specific_security(self) -> None:
        result = calculate_fifo(
            [
                tx(1, "2024-01-01", ActionType.BUY, 10, 10, -100, symbol="AAA", security_name="Alpha"),
                tx(2, "2024-02-01", ActionType.SELL, -4, 15, 60, symbol="AAA", security_name="Alpha"),
                tx(3, "2024-01-15", ActionType.BUY, 8, 20, -160, symbol="BBB", security_name="Beta"),
            ]
        )

        answer = answer_report_question(result, "מה הרווח של AAA?")

        self.assertIn("AAA", answer)
        self.assertIn("20.00", answer)

    def test_answers_for_date_range(self) -> None:
        result = calculate_fifo(
            [
                tx(1, "2024-01-01", ActionType.BUY, 10, 10, -100, symbol="AAA"),
                tx(2, "2024-02-01", ActionType.SELL, -4, 15, 60, symbol="AAA"),
                tx(3, "2024-03-01", ActionType.SELL, -2, 16, 32, symbol="AAA"),
            ]
        )

        answer = answer_report_question(result, "כמה תנועות היו בין 2024-02-01 ל-2024-03-01?")

        self.assertIn("2", answer)
        self.assertIn("טווח", answer)

    def test_answers_comparison_between_two_securities(self) -> None:
        result = calculate_fifo(
            [
                tx(1, "2024-01-01", ActionType.BUY, 10, 10, -100, symbol="AAA", security_name="Alpha"),
                tx(2, "2024-02-01", ActionType.SELL, -4, 15, 60, symbol="AAA", security_name="Alpha"),
                tx(3, "2024-01-15", ActionType.BUY, 8, 20, -160, symbol="BBB", security_name="Beta"),
                tx(4, "2024-02-10", ActionType.SELL, -4, 18, 72, symbol="BBB", security_name="Beta"),
            ]
        )

        answer = answer_report_question(result, "השווה בין AAA ל-BBB")

        self.assertIn("AAA", answer)
        self.assertIn("BBB", answer)
        self.assertIn("השוואה", answer)

    def test_answers_anomaly_question(self) -> None:
        result = calculate_fifo(
            [
                tx(1, "2024-01-01", ActionType.BUY, 10, 10, -100, symbol="AAA", security_name="Alpha"),
                tx(2, "2024-02-01", ActionType.SELL, -4, 15, 60, symbol="AAA", security_name="Alpha"),
                tx(3, "2024-01-15", ActionType.BUY, 8, 20, -160, symbol="BBB", security_name="Beta"),
                tx(4, "2024-02-10", ActionType.SELL, -4, 10, 40, symbol="BBB", security_name="Beta"),
            ]
        )

        answer = answer_report_question(result, "מה הנייר הכי בולט בדוח?")

        self.assertIn("הנייר", answer)
        self.assertTrue("AAA" in answer or "BBB" in answer)

    def test_answers_activity_breakdown_question(self) -> None:
        result = calculate_fifo(
            [
                tx(1, "2024-01-01", ActionType.BUY, 10, 10, -100, symbol="AAA"),
                tx(2, "2024-01-10", ActionType.BUY, 3, 11, -33, symbol="AAA"),
                tx(3, "2024-02-01", ActionType.SELL, -4, 15, 60, symbol="AAA"),
            ]
        )

        answer = answer_report_question(result, "תן לי פילוח פעילות לפי סוגי פעולה")

        self.assertIn("פילוח הפעילות", answer)
        self.assertIn("קניות", answer)
        self.assertIn("מכירות", answer)

    def test_answers_hidden_data_question(self) -> None:
        result = calculate_fifo(
            [
                tx(1, "2024-01-01", ActionType.BUY, 10, 10, -100, symbol="AAA"),
                tx(2, "2024-02-01", ActionType.SELL, -4, 15, 60, symbol="AAA"),
            ]
        )
        result.issues = [
            ValidationIssue(
                severity="warning",
                message="Missing note",
                source_file="qa.xlsx",
                sheet="Sheet1",
                row_number=2,
                field="note",
            )
        ]
        result.corporate_actions = [
            CorporateActionRecord(
                action_date=datetime.fromisoformat("2024-01-20"),
                action_type="reverse split",
                old_key="AAA",
                new_key="AAA",
                old_quantity=10,
                new_quantity=5,
                ratio=0.5,
                source_file="qa.xlsx",
                row_numbers="7-8",
            )
        ]

        answer = answer_report_question(result, "מה עוד חשוב לבדוק מעבר למסך הראשי?")

        self.assertIn("מעבר לכרטיסים", answer)
        self.assertIn("התראות", answer)
        self.assertIn("אירועי הון", answer)

    def test_answers_key_insights_question(self) -> None:
        result = calculate_fifo(
            [
                tx(1, "2024-01-01", ActionType.BUY, 10, 10, -100, symbol="AAA"),
                tx(2, "2024-02-01", ActionType.SELL, -4, 15, 60, symbol="AAA"),
            ]
        )

        answer = answer_report_question(result, "תן לי 5 תובנות מרכזיות")

        self.assertIn("5 תובנות מרכזיות", answer)
        self.assertIn("1.", answer)

    def test_suggested_questions_reflect_result_state(self) -> None:
        result = calculate_fifo(
            [
                tx(1, "2024-01-01", ActionType.BUY, 10, 10, -100, symbol="AAA"),
                tx(2, "2024-01-15", ActionType.BUY, 8, 20, -160, symbol="BBB"),
                tx(3, "2024-02-01", ActionType.SELL, -4, 15, 60, symbol="AAA"),
            ]
        )
        result.issues = [
            ValidationIssue(
                severity="warning",
                message="Missing price",
                source_file="qa.xlsx",
                sheet="Sheet1",
                row_number=4,
                field="price",
            )
        ]

        suggestions = suggested_report_questions(result)

        self.assertTrue(any("תובנות" in question for question in suggestions))
        self.assertTrue(any("חריגות" in question or "נתונים חסרים" in question for question in suggestions))
        self.assertTrue(any("השווה בין" in question for question in suggestions))


if __name__ == "__main__":
    unittest.main()
