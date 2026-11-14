"""
Trade Republic transaction export import (#45).

parse_tr_export() turns the CSV from the Trade Republic app (Profile ->
Transaction export) into buys and sells; it is pure (no database, no
network). Holdings only: cash movements are counted and ignored.
"""
import csv
import io
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional

from app.core.instruments import normalize_isin

LIQUIDATION_PREFIX = "liquidation:"
IGNORED_CASH = "cash"
IGNORED_LIQUIDATION_CANCELLED = "liquidation cancelled"

REQUIRED_COLUMNS = ("date", "category", "type", "name", "symbol", "shares",
                    "price", "amount", "fee", "currency", "transaction_id")

LIQUIDATION_SHARE_TYPES = ("LIQUIDATION_DIVIDEND",
                           "LIQUIDATION_DIVIDEND_CANCELLED")
LIQUIDATION_PROCEEDS = "LIQUIDATION_PROCEEDS"


@dataclass
class ParsedTxn:
    line: int  # CSV line of the row (or the last row of a group)
    external_id: str
    isin: str
    name: Optional[str]
    transaction_type: str  # "buy" or "sell"
    trade_date: date
    shares: Decimal  # signed: + buy, - sell
    fiat: Decimal  # signed: + buy, - sell (proceeds)
    fees: Decimal  # >= 0
    price: Optional[Decimal]  # EUR fill price of a buy (reference)


@dataclass
class ParseResult:
    transactions: List[ParsedTxn] = field(default_factory=list)
    ignored: Dict[str, int] = field(default_factory=dict)
    unknown: List[dict] = field(default_factory=list)


@dataclass
class _Liquidation:
    isin: str
    name: Optional[str] = None
    shares: Decimal = Decimal("0")
    amount: Decimal = Decimal("0")
    last_date: Optional[date] = None
    last_line: int = 0


def _decimal(value: str, column: str) -> Decimal:
    value = (value or "").strip()
    if not value:
        return Decimal("0")
    try:
        return Decimal(value)
    except InvalidOperation:
        raise ValueError(f"{column} is not a number: {value!r}")


def _date(value: str) -> date:
    try:
        return date.fromisoformat((value or "").strip())
    except ValueError:
        raise ValueError(f"date is not YYYY-MM-DD: {value!r}")


def _trade(row: dict, line: int) -> ParsedTxn:
    if row["currency"].strip() != "EUR":
        raise ValueError(f"currency is {row['currency']!r}, only EUR "
                         "trades can be imported")
    external_id = row["transaction_id"].strip()
    if not external_id:
        raise ValueError("transaction_id is empty")
    if not row["symbol"].strip():
        raise ValueError("symbol (ISIN) is empty")
    sell = row["type"] == "SELL"
    sign = Decimal("-1") if sell else Decimal("1")
    price = _decimal(row["price"], "price")
    return ParsedTxn(
        line=line, external_id=external_id,
        isin=normalize_isin(row["symbol"]),
        name=row["name"].strip() or None,
        transaction_type="sell" if sell else "buy",
        trade_date=_date(row["date"]),
        shares=sign * abs(_decimal(row["shares"], "shares")),
        fiat=sign * abs(_decimal(row["amount"], "amount")),
        fees=abs(_decimal(row["fee"], "fee")),
        price=price or None)


def _add_to_liquidation(groups: Dict[str, _Liquidation], row: dict,
                        line: int) -> None:
    isin = normalize_isin(row["symbol"])
    group = groups.setdefault(isin, _Liquidation(isin=isin))
    group.name = group.name or row["name"].strip() or None
    if row["category"] == "CASH":
        group.amount += _decimal(row["amount"], "amount")
    else:
        group.shares += _decimal(row["shares"], "shares")
    trade_date = _date(row["date"])
    if group.last_date is None or trade_date > group.last_date:
        group.last_date = trade_date
    group.last_line = max(group.last_line, line)


def _liquidation_sell(group: _Liquidation) -> ParsedTxn:
    return ParsedTxn(
        line=group.last_line,
        external_id=f"{LIQUIDATION_PREFIX}{group.isin}",
        isin=group.isin, name=group.name, transaction_type="sell",
        trade_date=group.last_date, shares=-abs(group.shares),
        fiat=-abs(group.amount), fees=Decimal("0"), price=None)


def _kind(row: dict) -> str:
    key = (row["category"], row["type"])
    if key in (("TRADING", "BUY"), ("TRADING", "SELL")):
        return "trade"
    if (key[0] == "CORPORATE_ACTION" and key[1] in LIQUIDATION_SHARE_TYPES
            or key == ("CASH", LIQUIDATION_PROCEEDS)):
        return "liquidation"
    if key[0] == "CASH":
        return "cash"
    return "unknown"


def _reader(csv_text: str) -> csv.DictReader:
    text = (csv_text or "").lstrip("﻿")
    reader = csv.DictReader(io.StringIO(text))
    names = [name.strip().lower() for name in (reader.fieldnames or [])]
    missing = [c for c in REQUIRED_COLUMNS if c not in names]
    if missing:
        raise ValueError(f"Missing column(s): {', '.join(missing)}. "
                         "Is this a Trade Republic transaction export?")
    reader.fieldnames = names
    return reader


def parse_tr_export(csv_text: str) -> ParseResult:
    """Buys, sells and netted liquidations from a Trade Republic export.

    Raises ValueError naming the line for anything that can't be
    imported safely; unknown row types are reported, not raised."""
    reader = _reader(csv_text)
    result = ParseResult()
    seen: Dict[str, int] = {}
    groups: Dict[str, _Liquidation] = {}
    for row in reader:
        line = reader.line_num
        row = {k: (v or "").strip() for k, v in row.items() if k}
        tid = row["transaction_id"]
        if tid in seen:
            raise ValueError(f"line {line}: transaction_id {tid} also on "
                             f"line {seen[tid]}; is the file broken?")
        if tid:
            seen[tid] = line
        kind = _kind(row)
        try:
            if kind == "trade":
                result.transactions.append(_trade(row, line))
            elif kind == "liquidation":
                _add_to_liquidation(groups, row, line)
        except ValueError as e:
            raise ValueError(f"line {line}: {e}")
        if kind == "cash":
            result.ignored[IGNORED_CASH] = (
                result.ignored.get(IGNORED_CASH, 0) + 1)
        elif kind == "unknown":
            result.unknown.append({"line": line,
                                   "category": row["category"],
                                   "type": row["type"]})
    for group in groups.values():
        if group.shares != 0:
            result.transactions.append(_liquidation_sell(group))
        else:
            result.ignored[IGNORED_LIQUIDATION_CANCELLED] = (
                result.ignored.get(IGNORED_LIQUIDATION_CANCELLED, 0) + 1)
    return result
