from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any


class ActionType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    TRANSFER_IN = "TRANSFER_IN"
    TRANSFER_OUT = "TRANSFER_OUT"
    SPLIT_IN = "SPLIT_IN"
    SPLIT_OUT = "SPLIT_OUT"
    CAPITAL_REDUCTION = "CAPITAL_REDUCTION"
    EXPIRE = "EXPIRE"
    CASH = "CASH"
    IGNORE = "IGNORE"
    UNKNOWN = "UNKNOWN"


@dataclass(slots=True)
class ValidationIssue:
    severity: str
    message: str
    source_file: str
    sheet: str
    row_number: int
    field: str = ""
    value: Any = None


@dataclass(slots=True)
class Transaction:
    source_file: str
    sheet: str
    row_number: int
    broker: str
    trade_date: datetime
    action_raw: str
    action_type: ActionType
    security_id: str
    symbol: str
    security_name: str
    quantity: float
    price: float
    currency: str
    net_amount: float
    commission: float = 0.0
    fees: float = 0.0
    settlement_date: datetime | None = None
    account_type: str = ""
    report_currency: str = ""
    bank_reported_gain_loss: float | None = None
    tax_rate: float | None = None
    tax_withheld_local: float | None = None
    tax_withheld_foreign: float | None = None
    reference: str = ""
    description: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def inventory_key(self) -> str:
        if self.security_id:
            return self.security_id
        if self.symbol:
            return self.symbol.upper()
        return self.security_name.upper()

    @property
    def display_security(self) -> str:
        parts = [self.symbol, self.security_name, self.security_id]
        return " | ".join(str(p) for p in parts if p)

    @property
    def absolute_quantity(self) -> float:
        return abs(float(self.quantity or 0.0))

    def buy_cost_basis(self) -> float:
        if self.net_amount:
            return abs(float(self.net_amount))
        return abs(float(self.quantity) * float(self.price)) + abs(self.commission) + abs(self.fees)

    def sale_proceeds(self) -> float:
        if self.net_amount:
            return abs(float(self.net_amount))
        gross = abs(float(self.quantity) * float(self.price))
        return gross - abs(self.commission) - abs(self.fees)


@dataclass(slots=True)
class Lot:
    security_key: str
    security_id: str
    symbol: str
    security_name: str
    acquired_date: datetime
    source_file: str
    source_row: int
    quantity: float
    total_cost: float
    currency: str
    inferred: bool = False
    notes: str = ""

    @property
    def unit_cost(self) -> float:
        if not self.quantity:
            return 0.0
        return self.total_cost / self.quantity


@dataclass(slots=True)
class RealizedMatch:
    sale_date: datetime
    security_key: str
    security_id: str
    symbol: str
    security_name: str
    quantity: float
    proceeds: float
    cost_basis: float
    gain_loss: float
    currency: str
    sale_source_file: str
    sale_row: int
    buy_date: datetime | None
    buy_source_file: str
    buy_row: int
    inferred: bool = False
    action_raw: str = ""
    bank_reported_gain_loss: float | None = None


@dataclass(slots=True)
class CorporateActionRecord:
    action_date: datetime
    action_type: str
    old_key: str
    new_key: str
    old_quantity: float
    new_quantity: float
    ratio: float | None
    source_file: str
    row_numbers: str
    notes: str = ""


@dataclass(slots=True)
class ExchangeRateSnapshot:
    requested_date: date
    lookup_date: date
    published_date: date
    currency_pair: str
    rate: float
    source: str
    note: str = ""


@dataclass(slots=True)
class CalculationResult:
    transactions: list[Transaction]
    realized: list[RealizedMatch]
    open_lots: list[Lot]
    corporate_actions: list[CorporateActionRecord]
    issues: list[ValidationIssue]
    exchange_rate: ExchangeRateSnapshot | None = None
