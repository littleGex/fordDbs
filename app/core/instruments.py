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
import logging
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Callable, List, Optional, Tuple

logger = logging.getLogger(__name__)

PRICE_TOLERANCE = Decimal("0.05")
LOOKUP_FAILED = "lookup failed, retry later"

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


# --- Network lookups (filled in with the real services) ---------------

def figi_tickers(isin: str) -> List[str]:
    raise NotImplementedError


def yahoo_search(isin: str) -> List[Tuple[str, Optional[str]]]:
    raise NotImplementedError


def yahoo_quote(ticker: str,
                on: Optional[date]) -> Tuple[Optional[str],
                                             Optional[Decimal]]:
    raise NotImplementedError


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
