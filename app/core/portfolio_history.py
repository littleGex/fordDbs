"""
Portfolio value over time (#52): holdings, net money invested (fees
included) and market value per calendar day, rebuilt from
etf_transactions on every call; nothing derived is stored.

A ticker's price on a day is its latest observation on or before that
day: a cached Yahoo close, or the fill price of one of its own trades
(for days or tickers Yahoo has no close for). On the same date the close
wins. Today's live price, when there is one, wins on today.
"""
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.price_history import cached_closes
from app.models.shares_models import EtfTransaction

CENTS = Decimal("0.01")
FILL, CLOSE = 0, 1  # sort rank: a close after a fill on the same day wins

Observation = Tuple[date, int, Decimal]


def _observations(rows: List[EtfTransaction],
                  closes: Dict[str, list]) -> Dict[str, List[Observation]]:
    obs: Dict[str, List[Observation]] = defaultdict(list)
    for row in rows:
        shares, fiat = row.shares_acquired, row.fiat_invested
        if shares and fiat:
            obs[row.ticker_symbol].append(
                (row.transaction_date.date(), FILL, abs(fiat) / abs(shares)))
    for ticker, series in closes.items():
        obs[ticker].extend((day, CLOSE, close) for day, close in series
                           if close > 0)
    for series in obs.values():
        series.sort(key=lambda o: (o[0], o[1]))
    return obs


class _Prices:
    """Walks each ticker's observations forward one day at a time."""

    def __init__(self, obs: Dict[str, List[Observation]]):
        self.obs = obs
        self.pos = defaultdict(int)
        self.current: Dict[str, Decimal] = {}

    def advance(self, day: date) -> None:
        for ticker, series in self.obs.items():
            i = self.pos[ticker]
            while i < len(series) and series[i][0] <= day:
                self.current[ticker] = series[i][2]
                i += 1
            self.pos[ticker] = i

    def price(self, ticker: str, live: Optional[float]) -> Decimal:
        if live and live > 0:
            return Decimal(str(live))
        return self.current.get(ticker, Decimal("0"))


def portfolio_history(db: Session, today: date,
                      live_prices: Dict[str, float]) -> List[dict]:
    """One point per calendar day from the first trade to today:
    {"date", "value", "invested"}; [] without transactions."""
    rows = db.query(EtfTransaction).filter(
        EtfTransaction.transaction_date.isnot(None)).order_by(
        EtfTransaction.transaction_date).all()
    if not rows:
        return []
    by_day = defaultdict(list)
    for row in rows:
        by_day[row.transaction_date.date()].append(row)
    tickers = {row.ticker_symbol for row in rows}
    prices = _Prices(_observations(rows, cached_closes(db, tickers)))

    shares: Dict[str, Decimal] = defaultdict(Decimal)
    invested = Decimal("0")
    points = []
    day = rows[0].transaction_date.date()
    while day <= today:
        for row in by_day.get(day, []):
            shares[row.ticker_symbol] += row.shares_acquired
            invested += row.fiat_invested + (row.fees or 0)
        prices.advance(day)
        value = sum((held * prices.price(
            ticker, live_prices.get(ticker) if day == today else None)
            for ticker, held in shares.items() if held), Decimal("0"))
        points.append({"date": day.isoformat(),
                       "value": float(value.quantize(CENTS)),
                       "invested": float(invested.quantize(CENTS))})
        day += timedelta(days=1)
    return points
