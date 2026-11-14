"""
Daily close cache for the portfolio history chart (#52).

ensure_price_history() fetches unadjusted daily closes from Yahoo for the
days each ticker is missing, in one batched download, and records how
far each ticker has been fetched so days without a close (weekends,
holidays) aren't asked for again. Only finished days are cached.
"""
import logging
import math
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


def _first_trade_dates(db: Session,
                       tickers: Optional[Iterable[str]]) -> Dict[str, date]:
    query = db.query(EtfTransaction.ticker_symbol,
                     func.min(EtfTransaction.transaction_date)
                     ).group_by(EtfTransaction.ticker_symbol)
    if tickers is not None:
        query = query.filter(EtfTransaction.ticker_symbol.in_(list(tickers)))
    return {ticker: first.date() for ticker, first in query
            if first is not None and not _is_isin(ticker)}


def _missing_starts(db: Session, firsts: Dict[str, date],
                    through: date) -> Tuple[Dict[str, date], dict]:
    """(ticker -> first day to fetch, ticker -> fetched_through)."""
    states = {s.ticker: s.fetched_through for s in
              db.query(PriceFetchState).filter(
                  PriceFetchState.ticker.in_(list(firsts)))}
    starts = {}
    for ticker, first in firsts.items():
        done = states.get(ticker)
        start = done + timedelta(days=1) if done else first
        if start <= through:
            starts[ticker] = start
    return starts, states


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


def _store(db: Session, rows: List[dict], tickers: Iterable[str],
           through: date) -> None:
    if rows:
        db.execute(insert(PriceHistory).values(rows)
                   .on_conflict_do_nothing())
    states = [{"ticker": t, "fetched_through": through} for t in tickers]
    if states:
        stmt = insert(PriceFetchState).values(states)
        db.execute(stmt.on_conflict_do_update(
            index_elements=[PriceFetchState.ticker],
            set_={"fetched_through": stmt.excluded.fetched_through}))
    db.flush()


def ensure_price_history(db: Session, tickers: Optional[Iterable[str]] = None,
                         *, through: Optional[date] = None,
                         download: Optional[Callable] = None
                         ) -> Dict[str, Optional[date]]:
    """Fetch the missing daily closes (through yesterday by default).

    Returns the tickers still not fetched through `through` (Yahoo
    failed), mapped to how far they were fetched. Does not commit."""
    through = through or berlin_today() - timedelta(days=1)
    download = download or yf.download
    starts, states = _missing_starts(db, _first_trade_dates(db, tickers),
                                     through)
    if not starts:
        return {}
    wanted = sorted(starts)
    try:
        frame = download(wanted, start=min(starts.values()),
                         end=through + timedelta(days=1), interval="1d",
                         auto_adjust=False, progress=False,
                         timeout=DOWNLOAD_TIMEOUT)
    except Exception:
        logger.exception("Price history download failed for %s", wanted)
        return {t: states.get(t) for t in wanted}
    single = len(wanted) == 1
    rows = [row for t in wanted
            for row in _rows_for(_close_series(frame, t, single), t,
                                 starts[t], through)]
    _store(db, rows, wanted, through)
    return {}


def cached_closes(db: Session, tickers: Iterable[str]
                  ) -> Dict[str, List[Tuple[date, Decimal]]]:
    """Cached closes per ticker, oldest first."""
    result: Dict[str, List[Tuple[date, Decimal]]] = {}
    for row in db.query(PriceHistory).filter(
            PriceHistory.ticker.in_(list(tickers))).order_by(
            PriceHistory.ticker, PriceHistory.day):
        result.setdefault(row.ticker, []).append((row.day, row.close))
    return result
