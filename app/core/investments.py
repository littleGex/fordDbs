import logging
import yfinance as yf
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Dict, Set
from app.models.shares_models import EmployeeShare, EtfTransaction
from datetime import datetime
from requests.exceptions import RequestException


logger = logging.getLogger(__name__)


def fetch_live_prices(tickers: Set[str]) -> Dict[str, float]:
    """
    Fetches the most recent price for a set of tickers with
    specific error handling.
    """
    if not tickers:
        return {}

    print(f"DEBUG: Fetching prices for database tickers: {tickers}")

    ticker_list = list(tickers)
    prices = {ticker: 0.0 for ticker in tickers}

    try:
        # Download without group_by to keep the structure flat
        data = yf.download(
            tickers=ticker_list,
            period="5d",
            interval="1d",
            progress=False,
            timeout=10
        )

        if data.empty:
            logger.warning(f"No data returned for tickers: {ticker_list}")
            return prices

        for ticker in ticker_list:
            try:
                if ('Close', ticker) in data.columns:
                    series = data[('Close', ticker)]
                elif 'Close' in data.columns:
                    series = data['Close']
                else:
                    continue

                valid_prices = series.dropna()
                if not valid_prices.empty:
                    prices[ticker] = round(float(valid_prices.iloc[-1]), 2)

            except Exception as e:
                logger.error(f"Error parsing {ticker}: {e}")

    except Exception as e:
        logger.error(f"Yahoo Finance fetch failed: {e}")

    return prices


def format_shares(shares_data, live_prices: dict) -> list:
    formatted = []
    for row in shares_data:
        price = live_prices.get(row.ticker_symbol, 0.0)
        available = float(row.available or 0)
        pending = float(row.pending or 0)

        formatted.append({
            "ticker": row.ticker_symbol,
            "available_shares": available,
            "pending_shares": pending,
            "live_price": price,
            "available_value": round(available * price, 2),
            "pending_value": round(pending * price, 2),
            "total_value": round((available + pending) * price, 2)
        })
    return formatted


def format_etfs(etf_data, live_prices: dict) -> list:
    formatted = []
    for row in etf_data:
        shares = float(row.total_shares or 0)
        invested = float(row.total_invested or 0)
        price = live_prices.get(row.ticker_symbol, 0.0)
        current_value = shares * price

        formatted.append({
            "ticker": row.ticker_symbol,
            "total_shares": shares,
            "total_invested": invested,
            "live_price": price,
            "current_value": round(current_value, 2),
            "roi_fiat": round(current_value - invested, 2),
            "roi_percentage": round(
                ((current_value - invested) / invested * 100),
                2) if invested > 0 else 0.0
        })
    return formatted


def get_grouped_shares(db: Session, target_date: datetime):
    return db.query(
        EmployeeShare.ticker_symbol,
        func.sum(EmployeeShare.num_shares).filter(
            EmployeeShare.vest_date <= target_date).label("available"),
        func.sum(EmployeeShare.num_shares).filter(
            EmployeeShare.vest_date > target_date).label("pending")
    ).group_by(EmployeeShare.ticker_symbol).all()


def get_grouped_etfs(db: Session):
    return db.query(
        EtfTransaction.ticker_symbol,
        func.sum(EtfTransaction.shares_acquired).label("total_shares"),
        func.sum(EtfTransaction.fiat_invested).label("total_invested")
    ).group_by(EtfTransaction.ticker_symbol).all()


def get_vesting_schedule(db: Session, live_prices: dict):
    """
    Returns a chronological list of vesting events to build a timeline.
    """
    grants = db.query(EmployeeShare).order_by(EmployeeShare.vest_date).all()

    schedule = []
    cumulative_shares = 0.0

    for grant in grants:
        cumulative_shares += float(grant.num_shares)
        # Get the price for this specific ticker
        price = live_prices.get(grant.ticker_symbol, 0.0)

        schedule.append({
            "date": grant.vest_date.strftime("%Y-%m-%d"),
            "value": round(cumulative_shares * price, 2)
        })
    return schedule


def get_portfolio_summary(db: Session):
    now = datetime.now()
    shares_data = get_grouped_shares(db, target_date=now)
    etf_data = get_grouped_etfs(db)

    tickers = {row.ticker_symbol for row in shares_data}.union(
        {row.ticker_symbol for row in etf_data})

    live_prices = fetch_live_prices(tickers)

    # Pass live_prices to the schedule generator
    vesting_timeline = get_vesting_schedule(db, live_prices)

    return {
        "shares": format_shares(shares_data, live_prices),
        "etfs": format_etfs(etf_data, live_prices),
        "vesting_timeline": vesting_timeline,
        "timestamp": now.isoformat()
    }
