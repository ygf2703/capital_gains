from datetime import datetime
import unittest

from capital_gains_app.fifo import calculate_fifo
from capital_gains_app.models import ActionType, Transaction


def tx(row, date, action, security_id, qty, price, net, gain=None):
    return Transaction(
        source_file="test.xlsx",
        sheet="Sheet1",
        row_number=row,
        broker="Test",
        trade_date=datetime.fromisoformat(date),
        action_raw=action.value,
        action_type=action,
        security_id=security_id,
        symbol=security_id,
        security_name=security_id,
        quantity=qty,
        price=price,
        currency="USD",
        report_currency="USD",
        net_amount=net,
        bank_reported_gain_loss=gain,
    )


class FIFOTests(unittest.TestCase):
    def test_fifo_matches_oldest_lot_first(self):
        result = calculate_fifo(
            [
                tx(1, "2024-01-01", ActionType.BUY, "AAA", 100, 10, -1000),
                tx(2, "2024-01-02", ActionType.BUY, "AAA", 100, 12, -1200),
                tx(3, "2024-01-03", ActionType.SELL, "AAA", -150, 15, 2250),
            ]
        )
        self.assertEqual(len(result.realized), 2)
        self.assertAlmostEqual(sum(row.gain_loss for row in result.realized), 650)
        self.assertAlmostEqual(result.open_lots[0].quantity, 50)
        self.assertAlmostEqual(result.open_lots[0].unit_cost, 12)

    def test_infers_missing_lot_from_bank_gain(self):
        result = calculate_fifo([tx(1, "2024-01-01", ActionType.SELL, "AAA", -10, 15, 150, gain=50)])
        self.assertEqual(len(result.realized), 1)
        self.assertTrue(result.realized[0].inferred)
        self.assertAlmostEqual(result.realized[0].cost_basis, 100)
        self.assertAlmostEqual(result.realized[0].gain_loss, 50)


if __name__ == "__main__":
    unittest.main()
