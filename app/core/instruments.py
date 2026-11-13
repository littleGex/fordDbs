# app/core/instruments.py
"""
ISIN instruments (#38): resolve an ISIN to a Yahoo ticker priced in EUR.

Candidates come from OpenFIGI (German composite ticker + ".DE") and
Yahoo search. Only candidates Yahoo prices in EUR can be picked, a
".DE" listing first. With a reference fill price, the pick's close on
that date must be within PRICE_TOLERANCE, otherwise nothing is picked
and the ISIN is left for a manual choice.

The three network lookups are plain functions passed in by keyword so
tests can use fakes; left out, the module-level functions are looked up
at call time (so they can also be patched).
"""
import json
import logging
import math
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Callable, List, Optional, Tuple

import yfinance as yf
from sqlalchemy.orm import Session

from app.models.shares_models import (EtfPurchaseSchedule, EtfTransaction,
                                      Instrument)

logger = logging.getLogger(__name__)

PRICE_TOLERANCE = Decimal("0.05")
LOOKUP_FAILED = "lookup failed, retry later"
HTTP_TIMEOUT = 10
OPENFIGI_URL = "https://api.openfigi.com/v3/mapping"
# OpenFIGI exchange code for the German composite; its tickers are the
# Xetra ones, which Yahoo lists with a ".DE" suffix.
FIGI_GERMANY = "GR"

Reference = Tuple[date, Decimal]


@dataclass
class Candidate:
    ticker: str
    currency: Optional[str]
    close: Optional[Decimal]
    accepted: bool
    reason: str


@dataclass
class Resolution:
    isin: str
    ticker: Optional[str]
    currency: Optional[str]
    name: Optional[str]
    candidates: List[Candidate] = field(default_factory=list)
    note: str = ""


# --- ISIN validation -------------------------------------------------

def _isin_check_digit(body: str) -> int:
    """Luhn check digit over the first 11 characters, letters A=10..Z=35."""
    digits = "".join(str(int(c, 36)) for c in body)
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return (10 - total % 10) % 10


def normalize_isin(value: str) -> str:
    """Strip and upper-case an ISIN; ValueError if it is not valid."""
    isin = (value or "").strip().upper()
    if (len(isin) != 12 or not isin[:2].isalpha()
            or not isin[2:11].isalnum() or not isin[11].isdigit()
            or not isin.isascii()):
        raise ValueError(f"not a valid ISIN: {value!r}")
    if _isin_check_digit(isin[:11]) != int(isin[11]):
        raise ValueError(f"ISIN check digit does not match: {value!r}")
    return isin


# --- Network lookups ---------------------------------------------------

def figi_tickers(isin: str) -> List[str]:
    """Xetra tickers (as Yahoo ".DE" symbols) OpenFIGI has for isin."""
    body = json.dumps([{"idType": "ID_ISIN", "idValue": isin}]).encode()
    request = urllib.request.Request(
        OPENFIGI_URL, data=body,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as resp:
        (result,) = json.load(resp)
    tickers = [d["ticker"] + ".DE" for d in result.get("data", [])
               if d.get("exchCode") == FIGI_GERMANY and d.get("ticker")]
    return list(dict.fromkeys(tickers))


def yahoo_search(isin: str) -> List[Tuple[str, Optional[str]]]:
    """(symbol, short name) for each listing Yahoo search finds."""
    quotes = yf.Search(isin, max_results=10, news_count=0,
                       timeout=HTTP_TIMEOUT).quotes
    return [(q["symbol"], q.get("shortname")) for q in quotes
            if q.get("symbol")]


def yahoo_quote(ticker: str,
                on: Optional[date]) -> Tuple[Optional[str],
                                             Optional[Decimal]]:
    """(currency, close) for ticker: the last close on or before `on`,
    or the latest close when on is None. close is None when Yahoo has
    no usable price; LookupError when Yahoo does not know the ticker."""
    t = yf.Ticker(ticker)
    try:
        currency = t.fast_info["currency"]
    except KeyError:
        raise LookupError(f"Yahoo has no data for {ticker}")
    if on is None:
        history = t.history(period="5d", timeout=HTTP_TIMEOUT)
    else:
        history = t.history(start=on - timedelta(days=5),
                            end=on + timedelta(days=1),
                            timeout=HTTP_TIMEOUT)
    closes = [c for c in history.get("Close", [])
              if c is not None and math.isfinite(c)]
    if not closes:
        return currency, None
    return currency, Decimal(str(round(float(closes[-1]), 4)))


# --- Resolver ---------------------------------------------------------

def _describe(candidates: List[Candidate]) -> str:
    return ", ".join(f"{c.ticker} ({c.reason})" for c in candidates)


def _collect_tickers(isin, figi_tickers, yahoo_search):
    """Candidate tickers (OpenFIGI first, then Yahoo search), the first
    Yahoo short name, and the errors from sources that failed."""
    tickers, name, errors = [], None, []
    try:
        tickers.extend(figi_tickers(isin))
    except Exception as e:
        errors.append(f"OpenFIGI: {e}")
        logger.warning(f"OpenFIGI lookup failed for {isin}: {e}")
    try:
        for symbol, shortname in yahoo_search(isin):
            tickers.append(symbol)
            name = name or shortname or None
    except Exception as e:
        errors.append(f"Yahoo search: {e}")
        logger.warning(f"Yahoo search failed for {isin}: {e}")
    unique = list(dict.fromkeys(t.strip().upper() for t in tickers))
    return unique, name, errors


def _check_candidate(ticker, on, yahoo_quote) -> Tuple[Candidate, bool]:
    """Quote one ticker; returns the candidate and whether the quote
    itself failed (as opposed to Yahoo having no data)."""
    try:
        currency, close = yahoo_quote(ticker, on)
    except LookupError:
        return Candidate(ticker, None, None, False, "no Yahoo data"), False
    except Exception as e:
        return Candidate(ticker, None, None, False,
                         f"quote failed: {e}"), True
    if currency != "EUR":
        reason = f"priced in {currency or 'unknown currency'}"
        return Candidate(ticker, currency, close, False, reason), False
    if close is None:
        return Candidate(ticker, currency, None, False,
                         "no Yahoo data"), False
    return Candidate(ticker, currency, close, True, "EUR listing"), False


def resolve_isin(isin: str, reference: Optional[Reference] = None, *,
                 figi_tickers: Optional[Callable] = None,
                 yahoo_search: Optional[Callable] = None,
                 yahoo_quote: Optional[Callable] = None) -> Resolution:
    """Pick a EUR-priced Yahoo ticker for isin. Never raises for
    network problems; raises ValueError for an invalid ISIN."""
    isin = normalize_isin(isin)
    tickers, name, errors = _collect_tickers(
        isin, figi_tickers or globals()["figi_tickers"],
        yahoo_search or globals()["yahoo_search"])

    on = reference[0] if reference else None
    checked = [_check_candidate(t, on,
                                yahoo_quote or globals()["yahoo_quote"])
               for t in tickers]
    candidates = [c for c, _ in checked]
    quote_errors = sum(1 for _, failed in checked if failed)

    result = Resolution(isin=isin, ticker=None, currency=None, name=name,
                        candidates=candidates)
    accepted = [c for c in candidates if c.accepted]

    if not accepted:
        lookups_failed = (errors and not candidates) or (
            candidates and quote_errors == len(candidates))
        if lookups_failed:
            result.note = f"{LOOKUP_FAILED} ({'; '.join(errors) or 'quotes'})"
        elif candidates:
            result.note = f"No EUR listing found. Candidates: " \
                          f"{_describe(candidates)}"
        else:
            result.note = "No listings found for this ISIN."
        return result

    pick = next((c for c in accepted if c.ticker.endswith(".DE")),
                accepted[0])

    if reference:
        ref_date, ref_price = reference
        off = abs(pick.close - ref_price) / ref_price
        if off > PRICE_TOLERANCE:
            result.note = (
                f"{pick.ticker} closed at {pick.close} on {ref_date}, "
                f"{off:.1%} off the fill price {ref_price}; set the ticker "
                f"by hand if it is right. Candidates: "
                f"{_describe(candidates)}")
            return result
        result.note = (f"Picked {pick.ticker}: close {pick.close} on "
                       f"{ref_date} is within {PRICE_TOLERANCE:.0%} of the "
                       f"fill price {ref_price}.")
    else:
        result.note = (f"Picked {pick.ticker} (EUR); not checked against "
                       f"a fill price.")

    result.ticker = pick.ticker
    result.currency = pick.currency
    return result


# --- Service layer (database). Callers commit. -------------------------

LINKED_MODELS = (EtfTransaction, EtfPurchaseSchedule)


def set_instrument_ticker(db: Session, instrument: Instrument, ticker: str,
                          currency: str, *, manual: bool) -> None:
    """The one place an instrument's ticker changes: also rewrites
    ticker_symbol on every transaction and schedule linked to it."""
    ticker = ticker.strip().upper()
    instrument.yahoo_ticker = ticker
    instrument.currency = currency
    instrument.manual_override = manual
    instrument.resolved_at = datetime.now()
    for model in LINKED_MODELS:
        db.query(model).filter(model.isin == instrument.isin).update(
            {model.ticker_symbol: ticker}, synchronize_session="fetch")


def apply_resolution(db: Session, instrument: Instrument,
                     resolution: Resolution) -> None:
    """Store a resolver result; an unresolved result keeps any ticker
    the instrument already had."""
    if not instrument.name and resolution.name:
        instrument.name = resolution.name
    instrument.resolution_note = resolution.note
    if resolution.ticker:
        set_instrument_ticker(db, instrument, resolution.ticker,
                              resolution.currency, manual=False)


def get_or_resolve(db: Session, isin: str, name: Optional[str] = None,
                   reference: Optional[Reference] = None, *,
                   resolver: Callable = resolve_isin) -> Instrument:
    """The stored instrument for isin, resolved or not, without a
    lookup; otherwise create it and run the resolver once."""
    isin = normalize_isin(isin)
    instrument = db.get(Instrument, isin)
    if instrument is not None:
        return instrument
    instrument = Instrument(isin=isin, name=(name or "").strip() or None,
                            manual_override=False)
    db.add(instrument)
    db.flush()
    apply_resolution(db, instrument, resolver(isin, reference))
    return instrument


def re_resolve(db: Session, instrument: Instrument, *,
               resolver: Callable = resolve_isin) -> Instrument:
    """Run the lookup again; never for a manual override."""
    if instrument.manual_override:
        raise PermissionError(
            f"{instrument.isin} was set by hand; set the ticker instead")
    apply_resolution(db, instrument,
                     resolver(instrument.isin,
                              reference_for(db, instrument.isin)))
    return instrument


def link_ticker(db: Session, instrument: Instrument,
                ticker_symbol: str) -> dict:
    """Attach existing rows with ticker_symbol (and no ISIN yet) to the
    instrument, renaming them to its ticker if it is resolved. Rows
    already linked to another ISIN are left alone and counted."""
    ticker_symbol = ticker_symbol.strip().upper()
    counts = {"transactions": 0, "schedules": 0, "conflicts": 0}
    found = already_linked = False
    for model, key in ((EtfTransaction, "transactions"),
                       (EtfPurchaseSchedule, "schedules")):
        rows = db.query(model).filter(
            model.ticker_symbol == ticker_symbol).all()
        found = found or bool(rows)
        already_linked = already_linked or db.query(model).filter(
            model.isin == instrument.isin).first() is not None
        for row in rows:
            if row.isin is None:
                row.isin = instrument.isin
                if instrument.yahoo_ticker:
                    row.ticker_symbol = instrument.yahoo_ticker
                counts[key] += 1
            elif row.isin != instrument.isin:
                counts["conflicts"] += 1
    # A repeated link finds nothing under the old name (the rows were
    # renamed), which is fine; a ticker nothing ever had is an error.
    if not found and not already_linked:
        raise LookupError(f"no transactions or schedules with ticker "
                          f"{ticker_symbol}")
    return counts


def reference_for(db: Session, isin: str) -> Optional[Reference]:
    """(date, EUR price per share) of the latest real fill linked to
    isin, to check a ticker against. Scheduled rows are skipped (they
    are estimates at the old ticker's price), as are zero-cost rows and
    rows without a date."""
    txn = db.query(EtfTransaction).filter(
        EtfTransaction.isin == isin,
        EtfTransaction.shares_acquired != 0,
        EtfTransaction.fiat_invested != 0,
        EtfTransaction.transaction_date.isnot(None),
        EtfTransaction.entry_type.is_distinct_from("scheduled"),
    ).order_by(EtfTransaction.transaction_date.desc()).first()
    if txn is None:
        return None
    price = (abs(Decimal(txn.fiat_invested))
             / abs(Decimal(txn.shares_acquired))).quantize(
                 Decimal("0.0001"))
    return txn.transaction_date.date(), price
