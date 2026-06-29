from __future__ import annotations

import csv
from datetime import date, datetime, timedelta
from io import StringIO
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .models import ExchangeRateSnapshot


BOI_EXCHANGE_RATE_ENDPOINT = "https://edge.boi.gov.il/FusionEdgeServer/sdmx/v2/data/dataflow/BOI.STATISTICS/EXR/1.0/"
BOI_EXCHANGE_RATE_SOURCE = "Bank of Israel - RER_USD_ILS official representative rate"


def parse_user_date(value: str) -> date:
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError("יש להזין תאריך בפורמט YYYY-MM-DD או DD/MM/YYYY")


def one_month_back(value: date) -> date:
    year = value.year
    month = value.month - 1
    if month == 0:
        month = 12
        year -= 1
    day = min(value.day, _days_in_month(year, month))
    return date(year, month, day)


def fetch_usd_ils_rate_one_month_back(requested_date: date, timeout: int = 20) -> ExchangeRateSnapshot:
    lookup_date = one_month_back(requested_date)
    rows = fetch_usd_ils_rates(lookup_date - timedelta(days=10), lookup_date, timeout=timeout)
    valid_rows = [row for row in rows if row[0] <= lookup_date]
    if not valid_rows:
        raise LookupError(f"לא נמצא שער יציג לדולר סביב {lookup_date:%Y-%m-%d}")
    published_date, rate = max(valid_rows, key=lambda row: row[0])
    note = ""
    if published_date != lookup_date:
        note = f"לא פורסם שער בתאריך היעד; נלקח השער האחרון שפורסם לפניו ({published_date:%Y-%m-%d})."
    return ExchangeRateSnapshot(
        requested_date=requested_date,
        lookup_date=lookup_date,
        published_date=published_date,
        currency_pair="USD/ILS",
        rate=rate,
        source=BOI_EXCHANGE_RATE_SOURCE,
        note=note,
    )


def fetch_usd_ils_rates(start_date: date, end_date: date, timeout: int = 20) -> list[tuple[date, float]]:
    query = urlencode(
        {
            "c[BASE_CURRENCY]": "USD",
            "c[COUNTER_CURRENCY]": "ILS",
            "c[DATA_TYPE]": "OF00",
            "format": "csv",
            "startPeriod": start_date.isoformat(),
            "endPeriod": end_date.isoformat(),
        }
    )
    request = Request(
        f"{BOI_EXCHANGE_RATE_ENDPOINT}?{query}",
        headers={"User-Agent": "CapitalGainsFIFO/0.2"},
    )
    with urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8-sig")
    return parse_boi_exchange_rate_csv(raw)


def parse_boi_exchange_rate_csv(raw_csv: str) -> list[tuple[date, float]]:
    rows: list[tuple[date, float]] = []
    reader = csv.DictReader(StringIO(raw_csv))
    for row in reader:
        period = row.get("TIME_PERIOD")
        value = row.get("OBS_VALUE")
        if not period or not value:
            continue
        rows.append((datetime.strptime(period, "%Y-%m-%d").date(), float(value)))
    return rows


def _days_in_month(year: int, month: int) -> int:
    next_month = month + 1
    next_year = year
    if next_month == 13:
        next_month = 1
        next_year += 1
    return (date(next_year, next_month, 1) - timedelta(days=1)).day
