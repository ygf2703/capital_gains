from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import replace
from datetime import datetime
from typing import Iterable

from .models import (
    ActionType,
    CalculationResult,
    CorporateActionRecord,
    Lot,
    RealizedMatch,
    Transaction,
    ValidationIssue,
)

EPSILON = 0.000001


class FIFOEngine:
    def __init__(self, infer_missing_cost_basis: bool = True) -> None:
        self.infer_missing_cost_basis = infer_missing_cost_basis
        self.lots: dict[str, deque[Lot]] = defaultdict(deque)
        self.realized: list[RealizedMatch] = []
        self.issues: list[ValidationIssue] = []
        self.corporate_actions: list[CorporateActionRecord] = []

    def calculate(
        self, transactions: Iterable[Transaction], existing_issues: list[ValidationIssue] | None = None
    ) -> CalculationResult:
        if existing_issues:
            self.issues.extend(existing_issues)
        sorted_transactions = sorted(
            transactions,
            key=lambda tx: (tx.trade_date, _action_order(tx.action_type), tx.source_file, tx.row_number),
        )

        for tx in sorted_transactions:
            if tx.action_type in {ActionType.BUY, ActionType.TRANSFER_IN}:
                self._add_lot(tx)
            elif tx.action_type in {ActionType.SELL, ActionType.EXPIRE}:
                self._sell(tx)
            elif tx.action_type == ActionType.TRANSFER_OUT:
                self._remove_without_gain(tx)
            elif tx.action_type == ActionType.CAPITAL_REDUCTION:
                self._capital_reduction(tx)
            elif tx.action_type in {ActionType.SPLIT_IN, ActionType.SPLIT_OUT}:
                self._handle_split_like(tx, sorted_transactions)

        return CalculationResult(
            transactions=sorted_transactions,
            realized=self.realized,
            open_lots=self._open_lots(),
            corporate_actions=self.corporate_actions,
            issues=self.issues,
        )

    def _add_lot(self, tx: Transaction) -> None:
        quantity = abs(tx.quantity)
        if quantity <= EPSILON:
            return
        cost = tx.buy_cost_basis()
        self.lots[tx.inventory_key].append(
            Lot(
                security_key=tx.inventory_key,
                security_id=tx.security_id,
                symbol=tx.symbol,
                security_name=tx.security_name,
                acquired_date=tx.trade_date,
                source_file=tx.source_file,
                source_row=tx.row_number,
                quantity=quantity,
                total_cost=cost,
                currency=tx.report_currency or tx.currency,
                notes=tx.action_raw,
            )
        )

    def _sell(self, tx: Transaction) -> None:
        key = tx.inventory_key
        sale_quantity = abs(tx.quantity)
        if sale_quantity <= EPSILON:
            return

        proceeds_total = tx.sale_proceeds()
        remaining = sale_quantity

        while remaining > EPSILON:
            if not self.lots[key]:
                if not self._create_inferred_lot_for_shortfall(tx, remaining):
                    self.issues.append(
                        ValidationIssue(
                            severity="warning",
                            message=f"Not enough inventory for sale of {tx.display_security}; unmatched quantity {remaining:.6f}",
                            source_file=tx.source_file,
                            sheet=tx.sheet,
                            row_number=tx.row_number,
                            field="quantity",
                            value=remaining,
                        )
                    )
                    break

            lot = self.lots[key][0]
            matched_quantity = min(remaining, lot.quantity)
            fraction_of_sale = matched_quantity / sale_quantity
            proceeds = proceeds_total * fraction_of_sale
            cost = lot.unit_cost * matched_quantity
            bank_gain = None
            if tx.bank_reported_gain_loss is not None:
                bank_gain = tx.bank_reported_gain_loss * fraction_of_sale

            self.realized.append(
                RealizedMatch(
                    sale_date=tx.trade_date,
                    security_key=key,
                    security_id=tx.security_id or lot.security_id,
                    symbol=tx.symbol or lot.symbol,
                    security_name=tx.security_name or lot.security_name,
                    quantity=matched_quantity,
                    proceeds=proceeds,
                    cost_basis=cost,
                    gain_loss=proceeds - cost,
                    currency=tx.report_currency or lot.currency or tx.currency,
                    sale_source_file=tx.source_file,
                    sale_row=tx.row_number,
                    buy_date=lot.acquired_date,
                    buy_source_file=lot.source_file,
                    buy_row=lot.source_row,
                    inferred=lot.inferred,
                    action_raw=tx.action_raw,
                    bank_reported_gain_loss=bank_gain,
                )
            )

            lot.quantity -= matched_quantity
            lot.total_cost -= cost
            remaining -= matched_quantity
            if lot.quantity <= EPSILON:
                self.lots[key].popleft()

    def _create_inferred_lot_for_shortfall(self, tx: Transaction, quantity: float) -> bool:
        if not self.infer_missing_cost_basis or tx.bank_reported_gain_loss is None:
            return False
        total_sale_quantity = abs(tx.quantity)
        if total_sale_quantity <= EPSILON:
            return False
        proceeds_for_shortfall = tx.sale_proceeds() * (quantity / total_sale_quantity)
        gain_for_shortfall = tx.bank_reported_gain_loss * (quantity / total_sale_quantity)
        inferred_cost = proceeds_for_shortfall - gain_for_shortfall
        self.lots[tx.inventory_key].appendleft(
            Lot(
                security_key=tx.inventory_key,
                security_id=tx.security_id,
                symbol=tx.symbol,
                security_name=tx.security_name,
                acquired_date=tx.trade_date,
                source_file=tx.source_file,
                source_row=tx.row_number,
                quantity=quantity,
                total_cost=inferred_cost,
                currency=tx.report_currency or tx.currency,
                inferred=True,
                notes="Inferred opening cost from bank-reported gain/loss",
            )
        )
        self.issues.append(
            ValidationIssue(
                severity="info",
                message="Created inferred opening lot from bank-reported gain/loss",
                source_file=tx.source_file,
                sheet=tx.sheet,
                row_number=tx.row_number,
                field="cost_basis",
                value=round(inferred_cost, 2),
            )
        )
        return True

    def _remove_without_gain(self, tx: Transaction) -> None:
        key = tx.inventory_key
        remaining = abs(tx.quantity)
        while remaining > EPSILON and self.lots[key]:
            lot = self.lots[key][0]
            matched = min(remaining, lot.quantity)
            cost = lot.unit_cost * matched
            lot.quantity -= matched
            lot.total_cost -= cost
            remaining -= matched
            if lot.quantity <= EPSILON:
                self.lots[key].popleft()
        if remaining > EPSILON:
            self.issues.append(
                ValidationIssue(
                    severity="warning",
                    message=f"Transfer out exceeds available inventory by {remaining:.6f}",
                    source_file=tx.source_file,
                    sheet=tx.sheet,
                    row_number=tx.row_number,
                    field="quantity",
                    value=remaining,
                )
            )

    def _capital_reduction(self, tx: Transaction) -> None:
        key = tx.inventory_key
        reduce_by = abs(tx.quantity)
        total_quantity = sum(lot.quantity for lot in self.lots[key])
        if reduce_by <= EPSILON:
            return
        if total_quantity <= EPSILON:
            self.issues.append(
                ValidationIssue(
                    severity="warning",
                    message="Capital reduction found but no inventory exists for the security",
                    source_file=tx.source_file,
                    sheet=tx.sheet,
                    row_number=tx.row_number,
                    field="quantity",
                    value=tx.quantity,
                )
            )
            return
        if reduce_by >= total_quantity - EPSILON:
            self.issues.append(
                ValidationIssue(
                    severity="warning",
                    message="Capital reduction removes all or almost all inventory; review manually",
                    source_file=tx.source_file,
                    sheet=tx.sheet,
                    row_number=tx.row_number,
                    field="quantity",
                    value=tx.quantity,
                )
            )
            return

        ratio = (total_quantity - reduce_by) / total_quantity
        for lot in self.lots[key]:
            lot.quantity *= ratio
        self.corporate_actions.append(
            CorporateActionRecord(
                action_date=tx.trade_date,
                action_type=tx.action_raw,
                old_key=key,
                new_key=key,
                old_quantity=total_quantity,
                new_quantity=total_quantity - reduce_by,
                ratio=ratio,
                source_file=tx.source_file,
                row_numbers=str(tx.row_number),
                notes="Quantity reduced; total cost basis preserved across remaining shares",
            )
        )

    def _handle_split_like(self, tx: Transaction, all_transactions: list[Transaction]) -> None:
        if tx.action_type != ActionType.SPLIT_OUT:
            return

        candidates = [
            other
            for other in all_transactions
            if other.action_type == ActionType.SPLIT_IN
            and other.trade_date.date() == tx.trade_date.date()
            and other.source_file == tx.source_file
            and other.row_number != tx.row_number
            and abs(other.quantity) > EPSILON
        ]
        if not candidates:
            self._capital_reduction(
                replace(tx, action_type=ActionType.CAPITAL_REDUCTION, action_raw=f"{tx.action_raw} without matching incoming leg")
            )
            return

        incoming = min(candidates, key=lambda other: abs(other.row_number - tx.row_number))
        old_key = tx.inventory_key
        new_key = incoming.inventory_key
        old_quantity = abs(tx.quantity)
        new_quantity = abs(incoming.quantity)
        if old_quantity <= EPSILON:
            return
        ratio = new_quantity / old_quantity

        old_lots = list(self.lots[old_key])
        if not old_lots:
            self.issues.append(
                ValidationIssue(
                    severity="warning",
                    message="Corporate action found but no existing lots were available to convert",
                    source_file=tx.source_file,
                    sheet=tx.sheet,
                    row_number=tx.row_number,
                    field="security",
                    value=old_key,
                )
            )
            return

        self.lots[old_key].clear()
        for lot in old_lots:
            converted = Lot(
                security_key=new_key,
                security_id=incoming.security_id,
                symbol=incoming.symbol,
                security_name=incoming.security_name,
                acquired_date=lot.acquired_date,
                source_file=lot.source_file,
                source_row=lot.source_row,
                quantity=lot.quantity * ratio,
                total_cost=lot.total_cost,
                currency=lot.currency,
                inferred=lot.inferred,
                notes=f"Converted from {old_key} via {tx.action_raw}",
            )
            self.lots[new_key].append(converted)

        self.corporate_actions.append(
            CorporateActionRecord(
                action_date=tx.trade_date,
                action_type=tx.action_raw,
                old_key=old_key,
                new_key=new_key,
                old_quantity=old_quantity,
                new_quantity=new_quantity,
                ratio=ratio,
                source_file=tx.source_file,
                row_numbers=f"{tx.row_number},{incoming.row_number}",
                notes="Converted existing lots; total cost basis preserved",
            )
        )

    def _open_lots(self) -> list[Lot]:
        lots: list[Lot] = []
        for queue in self.lots.values():
            lots.extend(lot for lot in queue if lot.quantity > EPSILON)
        return lots


def calculate_fifo(
    transactions: Iterable[Transaction],
    existing_issues: list[ValidationIssue] | None = None,
    infer_missing_cost_basis: bool = True,
) -> CalculationResult:
    return FIFOEngine(infer_missing_cost_basis=infer_missing_cost_basis).calculate(transactions, existing_issues)


def _action_order(action_type: ActionType) -> int:
    order = {
        ActionType.TRANSFER_IN: 0,
        ActionType.BUY: 1,
        ActionType.SPLIT_OUT: 2,
        ActionType.SPLIT_IN: 3,
        ActionType.CAPITAL_REDUCTION: 4,
        ActionType.SELL: 5,
        ActionType.EXPIRE: 6,
        ActionType.TRANSFER_OUT: 7,
    }
    return order.get(action_type, 99)
