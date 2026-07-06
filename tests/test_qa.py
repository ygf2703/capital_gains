from datetime import datetime
import unittest

from capital_gains_app.fifo import calculate_fifo
from capital_gains_app.models import ActionType, Transaction
from capital_gains_app.qa import answer_report_question


def tx(row, trade_date, action, qty, price, net):
    return Transaction(
        source_file="qa.xlsx",
        sheet="Sheet1",
        row_number=row,
        broker="Test",
        trade_date=datetime.fromisoformat(trade_date),
        action_raw=action.value,
        action_type=action,
        security_id="AAA",
        symbol="AAA",
        security_name="Alpha Asset",
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


if __name__ == "__main__":
    unittest.main()
