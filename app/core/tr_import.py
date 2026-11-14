"""
Trade Republic transaction export import (#45).

parse_tr_export() turns the CSV from the Trade Republic app (Profile ->
Transaction export) into buys and sells; it is pure (no database, no
network). Holdings only: cash movements are counted and ignored.

import_tr_export() stores the new ones, linked to their ISIN's
instrument, skipping rows already imported (external_id). Trade Republic
is the source of truth for its savings plans: scheduled rows are never
touched.
"""
import csv
import io
import logging
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Callable, Dict, List, Optional

from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core import instruments
from app.core.instruments import normalize_isin
from app.models.shares_models import (EtfPurchaseSchedule, EtfTransaction,
                                      Instrument)

logger = logging.getLogger(__name__)

LIQUIDATION_PREFIX = "liquidation:"
RESOLVE_BUDGET_SECONDS = 60
NOT_LOOKED_UP = "not looked up yet, press Re-resolve"
SHARES_PLACES = Decimal("0.000001")
CENTS = Decimal("0.01")
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
    # ISINs whose liquidation nets to zero shares (cancelled)
    cancelled_liquidations: List[str] = field(default_factory=list)


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
            result.cancelled_liquidations.append(group.isin)
    return result


# --- Import (database) ------------------------------------------------


@dataclass
class ImportResult:
    imported: int  # would be imported, for a dry run
    skipped_duplicates: int
    ignored: Dict[str, int]
    unknown: List[dict]
    unresolved: List[str]  # ISINs of new rows without a ticker
    warnings: List[str]
    dry_run: bool


class ImportSaveError(Exception):
    """The database rejected the rows; nothing was imported."""


def _not_looked_up(isin, reference=None):
    return instruments.Resolution(isin=isin, ticker=None, currency=None,
                                  name=None, candidates=[],
                                  note=NOT_LOOKED_UP)


def _liquidation_warning(stored: EtfTransaction,
                         txn: ParsedTxn) -> Optional[str]:
    shares = txn.shares.quantize(SHARES_PLACES)
    fiat = txn.fiat.quantize(CENTS)
    if stored.shares_acquired == shares and stored.fiat_invested == fiat:
        return None
    return (f"{txn.isin}: liquidation in this export ({shares} shares, "
            f"{fiat} EUR) differs from the one already imported "
            f"({stored.shares_acquired} shares, {stored.fiat_invested} "
            "EUR); kept the stored one")


def _split_new(db: Session, parsed: List[ParsedTxn]):
    """(new rows, duplicate count, warnings)."""
    ids = [t.external_id for t in parsed]
    stored = {t.external_id: t for t in db.query(EtfTransaction).filter(
        EtfTransaction.external_id.in_(ids))} if ids else {}
    new, warnings = [], []
    for txn in parsed:
        if txn.external_id not in stored:
            new.append(txn)
        elif txn.external_id.startswith(LIQUIDATION_PREFIX):
            warning = _liquidation_warning(stored[txn.external_id], txn)
            if warning:
                warnings.append(warning)
    return new, len(parsed) - len(new), warnings


def _cancelled_warnings(db: Session, isins: List[str]) -> List[str]:
    """A liquidation imported earlier that this export shows as
    cancelled: the stored sell is kept, so say so."""
    ids = [f"{LIQUIDATION_PREFIX}{isin}" for isin in isins]
    stored = db.query(EtfTransaction.isin).filter(
        EtfTransaction.external_id.in_(ids)).all() if ids else []
    return [f"{isin}: this export shows its liquidation as cancelled, but "
            "a liquidation sell was imported earlier and has been kept; "
            "check this holding" for (isin,) in stored]


def _app_entries_warning(db: Session, isin: str,
                         instrument: Instrument) -> Optional[str]:
    """Rows or active schedules entered in the app for a fund whose real
    fills are being imported may count the same buys twice."""
    tickers = [t for t in (instrument.yahoo_ticker, isin) if t]
    rows = db.query(EtfTransaction).filter(
        EtfTransaction.external_id.is_(None),
        or_(EtfTransaction.isin == isin,
            EtfTransaction.ticker_symbol.in_(tickers))).count()
    schedules = db.query(EtfPurchaseSchedule).filter(
        EtfPurchaseSchedule.is_active.is_(True),
        or_(EtfPurchaseSchedule.isin == isin,
            EtfPurchaseSchedule.ticker_symbol.in_(tickers))).count()
    if not rows and not schedules:
        return None
    return (f"{isin} ({tickers[0]}): {rows} transaction(s) and "
            f"{schedules} active schedule(s) entered in the app also "
            "exist for this fund and may count the same buys twice; "
            "deactivate the schedule(s) and check those rows")


def _references(new: List[ParsedTxn]) -> dict:
    """ISIN -> (trade date, price) of its latest buy in the export."""
    refs = {}
    for txn in new:
        if txn.transaction_type != "buy" or txn.price is None:
            continue
        if txn.isin not in refs or txn.trade_date >= refs[txn.isin][0]:
            refs[txn.isin] = (txn.trade_date, txn.price)
    return refs


def _resolve_all(db: Session, new: List[ParsedTxn], resolver: Callable,
                 clock: Callable[[], float]) -> Dict[str, Instrument]:
    """The instrument of every ISIN, created and looked up if new.
    After RESOLVE_BUDGET_SECONDS the rest are created unresolved, so a
    big first import can't outlast the proxy's timeout."""
    names = {}
    for txn in new:
        names.setdefault(txn.isin, txn.name)
    refs = _references(new)
    start = clock()
    found = {}
    for isin, name in names.items():
        within_budget = clock() - start < RESOLVE_BUDGET_SECONDS
        found[isin] = instruments.get_or_resolve(
            db, isin, name, refs.get(isin),
            resolver=resolver if within_budget else _not_looked_up)
    return found


def _row(txn: ParsedTxn, instrument: Instrument) -> EtfTransaction:
    return EtfTransaction(
        ticker_symbol=instrument.yahoo_ticker or txn.isin,
        isin=txn.isin, external_id=txn.external_id, entry_type="import",
        transaction_type=txn.transaction_type,
        transaction_date=datetime.combine(txn.trade_date,
                                          datetime.min.time()),
        shares_acquired=txn.shares, fiat_invested=txn.fiat, fees=txn.fees)


def import_tr_export(db: Session, csv_text: str, *, dry_run: bool = False,
                     resolver: Optional[Callable] = None,
                     clock: Callable[[], float] = time.monotonic
                     ) -> ImportResult:
    """Import a Trade Republic export in one transaction (a savepoint,
    so a dry run rolls back only its own work). Raises ValueError for
    a file that can't be parsed, ImportSaveError if the database
    rejects the rows."""
    parsed = parse_tr_export(csv_text)
    resolver = resolver or instruments.resolve_isin
    savepoint = db.begin_nested()
    try:
        new, duplicates, warnings = _split_new(db, parsed.transactions)
        warnings += _cancelled_warnings(db, parsed.cancelled_liquidations)
        found = _resolve_all(db, new, resolver, clock)
        warnings += [w for w in (_app_entries_warning(db, isin, inst)
                                 for isin, inst in found.items()) if w]
        db.add_all([_row(txn, found[txn.isin]) for txn in new])
        db.flush()
        unresolved = sorted({txn.isin for txn in new
                             if not found[txn.isin].yahoo_ticker})
    except SQLAlchemyError:
        savepoint.rollback()
        logger.exception("Trade Republic import failed while saving")
        raise ImportSaveError(
            "Could not save the import; nothing was imported")
    if dry_run:
        savepoint.rollback()
    else:
        savepoint.commit()
        db.commit()
    return ImportResult(imported=len(new), skipped_duplicates=duplicates,
                        ignored=parsed.ignored, unknown=parsed.unknown,
                        unresolved=unresolved, warnings=warnings,
                        dry_run=dry_run)
