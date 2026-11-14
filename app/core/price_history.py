"""
Daily close cache for the portfolio history chart (#52).

ensure_price_history() fetches unadjusted daily closes from Yahoo for the
days each ticker is missing, in one batched download, and records how
far each ticker has been fetched so days without a close (weekends,
holidays) aren't asked for again. A ticker only counts as fetched up to
the last close Yahoo actually returned (plus a trailing weekend), so an
empty answer is retried and reported as out of date. Only finished days
are cached.
"""
import logging
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Callable, Dict, Iterable, List, Optional, Tuple

import pandas as pd
import pytz
import yfinance as yf
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.instruments import normalize_isin
from app.models.shares_models import (EtfTransaction, PriceFetchState,
                                      PriceHistory)

logger = logging.getLogger(__name__)

BERLIN = pytz.timezone("Europe/Berlin")
DOWNLOAD_TIMEOUT = 10


def berlin_today() -> date:
    return datetime.now(BERLIN).date()


def _is_isin(ticker: str) -> bool:
    """Rows without a Yahoo ticker use their ISIN; there's nothing to
    fetch for those."""
    try:
        return normalize_isin(ticker) == ticker
    except ValueError:
        return False


@dataclass
class _Need:
    """What one ticker needs: priced from its first trade through `end`
    (yesterday, or the day it was sold out), minus what is cached."""
    first: date
    end: date
    since: Optional[date] = None  # fetched_from
    done: Optional[date] = None  # fetched_through

    def ranges(self) -> List[Tuple[date, date]]:
        if self.first > self.end:
            return []
        if self.done is None:
            return [(self.first, self.end)]
        out = []
        if self.first < self.since:  # earlier trades added since
            out.append((self.first,
                        min(self.since - timedelta(days=1), self.end)))
        if self.done < self.end:
            out.append((self.done + timedelta(days=1), self.end))
        return out


def _needs(db: Session, tickers: Optional[Iterable[str]],
           through: date) -> Dict[str, _Need]:
    """Per ticker with trades: first trade through yesterday, or only
    through its last trade if it is no longer held (sold or liquidated
    funds aren't fetched, or reported as out of date, forever)."""
    query = db.query(EtfTransaction.ticker_symbol,
                     func.min(EtfTransaction.transaction_date),
                     func.max(EtfTransaction.transaction_date),
                     func.sum(EtfTransaction.shares_acquired)
                     ).group_by(EtfTransaction.ticker_symbol)
    if tickers is not None:
        query = query.filter(EtfTransaction.ticker_symbol.in_(list(tickers)))
    needs = {}
    for ticker, first, last, held in query:
        if first is None or _is_isin(ticker):
            continue
        end = through if held else min(through, last.date())
        needs[ticker] = _Need(first=first.date(), end=end)
    for row in db.query(PriceFetchState).filter(
            PriceFetchState.ticker.in_(list(needs))):
        needs[row.ticker].since = row.fetched_from
        needs[row.ticker].done = row.fetched_through
    return needs


def _close_series(frame: pd.DataFrame, ticker: str,
                  single: bool) -> Optional[pd.Series]:
    if frame is None or frame.empty:
        return None
    if isinstance(frame.columns, pd.MultiIndex):
        if "Close" not in frame.columns.get_level_values(0):
            return None
        closes = frame["Close"]
        return closes[ticker] if ticker in closes.columns else None
    return frame["Close"] if single and "Close" in frame.columns else None


def _rows_for(series: Optional[pd.Series], ticker: str, start: date,
              through: date) -> List[dict]:
    rows = []
    if series is None:
        return rows
    for stamp, value in series.items():
        day = pd.Timestamp(stamp).date()
        if value is None or not math.isfinite(value) or value <= 0:
            continue
        if start <= day <= through:
            rows.append({"ticker": ticker, "day": day,
                         "close": Decimal(str(round(float(value), 6)))})
    return rows


def _has_weekday(first: date, last: date) -> bool:
    day = first
    while day <= last:
        if day.weekday() < 5:
            return True
        day += timedelta(days=1)
    return False


def _fetched_through(start: date, through: date,
                     last_close: Optional[date]) -> Optional[date]:
    """How far a download really got for one ticker. yfinance often
    returns empty data instead of raising, so only days up to the last
    close returned count as fetched, plus trailing weekend days (which
    never have one). None: nothing new was fetched."""
    if last_close is None:
        return through if not _has_weekday(start, through) else None
    if not _has_weekday(last_close + timedelta(days=1), through):
        return through
    return last_close


def _progress(need: _Need, found: List[dict]) -> Optional[Tuple[date, date]]:
    """The ticker's new (fetched_from, fetched_through) after a
    download, or None if nothing counts as fetched yet."""
    days = [r["day"] for r in found]

    def last_in(lo, hi):
        return max((d for d in days if lo <= d <= hi), default=None)

    if need.done is None:
        reached = _fetched_through(need.first, need.end,
                                   last_in(need.first, need.end))
        return (need.first, reached) if reached else None
    since, done = need.since, need.done
    if need.first < need.since:
        lo, hi = need.first, need.since - timedelta(days=1)
        if last_in(lo, hi) or not _has_weekday(lo, hi):
            since = need.first
    if need.done < need.end:
        lo = need.done + timedelta(days=1)
        done = _fetched_through(lo, need.end,
                                last_in(lo, need.end)) or need.done
    return since, done


def _store(db: Session, rows: List[dict],
           progress: Dict[str, Tuple[date, date]]) -> None:
    if rows:
        db.execute(insert(PriceHistory).values(rows)
                   .on_conflict_do_nothing())
    states = [{"ticker": t, "fetched_from": since, "fetched_through": done}
              for t, (since, done) in progress.items()]
    if states:
        stmt = insert(PriceFetchState).values(states)
        db.execute(stmt.on_conflict_do_update(
            index_elements=[PriceFetchState.ticker],
            set_={"fetched_from": stmt.excluded.fetched_from,
                  "fetched_through": stmt.excluded.fetched_through}))
    db.flush()


def _is_stale(need: _Need, state: Optional[Tuple[date, date]]) -> bool:
    return (state is None or state[0] > need.first
            or state[1] < need.end)


def ensure_price_history(db: Session, tickers: Optional[Iterable[str]] = None,
                         *, through: Optional[date] = None,
                         download: Optional[Callable] = None
                         ) -> Dict[str, Optional[date]]:
    """Fetch the missing daily closes (through yesterday by default):
    earlier trades added since the last fetch, and new days, but only
    while a ticker is held.

    Returns the tickers whose needed days still aren't all fetched
    (Yahoo failed or returned nothing), mapped to their fetched_through.
    Does not commit."""
    through = through or berlin_today() - timedelta(days=1)
    download = download or yf.download
    needs = {t: n for t, n in _needs(db, tickers, through).items()
             if n.ranges()}
    if not needs:
        return {}
    wanted = sorted(needs)
    spans = [r for t in wanted for r in needs[t].ranges()]
    try:
        frame = download(wanted, start=min(lo for lo, _ in spans),
                         end=max(hi for _, hi in spans) + timedelta(days=1),
                         interval="1d", auto_adjust=False, progress=False,
                         timeout=DOWNLOAD_TIMEOUT)
    except Exception:
        logger.exception("Price history download failed for %s", wanted)
        return {t: needs[t].done for t in wanted}
    single = len(wanted) == 1
    rows, progress = [], {}
    for ticker in wanted:
        series = _close_series(frame, ticker, single)
        found = [row for lo, hi in needs[ticker].ranges()
                 for row in _rows_for(series, ticker, lo, hi)]
        rows += found
        state = _progress(needs[ticker], found)
        if state:
            progress[ticker] = state
    _store(db, rows, progress)
    return {t: (progress[t][1] if t in progress else needs[t].done)
            for t in wanted if _is_stale(needs[t], progress.get(t))}


def cached_closes(db: Session, tickers: Iterable[str]
                  ) -> Dict[str, List[Tuple[date, Decimal]]]:
    """Cached closes per ticker, oldest first."""
    result: Dict[str, List[Tuple[date, Decimal]]] = {}
    for row in db.query(PriceHistory).filter(
            PriceHistory.ticker.in_(list(tickers))).order_by(
            PriceHistory.ticker, PriceHistory.day):
        result.setdefault(row.ticker, []).append((row.day, row.close))
    return result
