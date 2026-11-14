# app/api/v1/portfolio_history.py
"""
Portfolio value over time (#52). Mounted under /v1/investments, parents
only (see app/main.py).
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.investments import fetch_live_prices
from app.core.portfolio_history import portfolio_history
from app.core.price_history import berlin_today, ensure_price_history
from app.database.database import get_db
from app.models.shares_models import EtfTransaction

history_router = APIRouter()


@history_router.get("/etf/history")
def get_portfolio_history(db: Session = Depends(get_db)):
    """ETF and stock value and net money invested per day. Fetches any
    missing daily closes first; tickers Yahoo couldn't bring up to date
    are listed in `stale`."""
    stale = ensure_price_history(db)
    db.commit()
    tickers = {t for (t,) in db.query(EtfTransaction.ticker_symbol)
               .distinct()}
    today = berlin_today()
    live = fetch_live_prices(tickers) if tickers else {}
    return {
        "points": portfolio_history(db, today, live),
        "stale": [{"ticker": t,
                   "through": stale[t].isoformat() if stale[t] else None}
                  for t in sorted(stale)],
        "as_of": today.isoformat(),
    }
