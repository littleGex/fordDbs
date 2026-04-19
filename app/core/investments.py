import logging
import yfinance as yf
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Dict, Set
from app.models.shares_models import EmployeeShare, EtfTransaction
from datetime import datetime
from requests.exceptions import RequestException


logger = logging.getLogger(__name__)


def get_portfolio_summary(db: Session):
    # 1. Fetch raw database records
    now = datetime.now()
    shares_data = get_grouped_shares(db, target_date=now)
    etf_data = get_grouped_etfs(db)

    # 2. Extract unique tickers
    tickers = {row.ticker_symbol for row in shares_data}.union(
              {row.ticker_symbol for row in etf_data})

    # 3. Fetch external live pricing
    live_prices = fetch_live_prices(tickers)

    # 4. Process business math and format output
    return {
        "shares": format_shares(shares_data, live_prices),
        "etfs": format_etfs(etf_data, live_prices),
        "timestamp": now.isoformat()
    }


def fetch_live_prices(tickers: Set[str]) -> Dict[str, float]:
    """
    Fetches the most recent price for a set of tickers with
    specific error handling.
    """
    if not tickers:
        return {}

    ticker_list = list(tickers)
    prices = {ticker: 0.0 for ticker in tickers}

    try:
        data = yf.download(
            tickers=ticker_list,
            period="5d",
            interval="1d",
            progress=False,
            group_by='ticker',
            timeout=10
        )

        if data.empty:
            logger.warning(
                f"No data returned for tickers: {ticker_list}")
            return prices

        for ticker in ticker_list:
            try:
                # Handle DataFrame structure based on ticker count
                df = data[ticker] if len(ticker_list) > 1 else data

                # Check if 'Close' column exists and has data
                if 'Close' in df and not df['Close'].dropna().empty:
                    last_price = df['Close'].dropna().iloc[-1]
                    prices[ticker] = round(float(last_price), 2)
                else:
                    logger.info(
                        f"Ticker {ticker} found but no price data available.")

            except KeyError:
                logger.error(
                    f"Ticker {ticker} not found in Yahoo Finance response.")
            except (IndexError, ValueError) as e:
                logger.error(f"Error parsing data for {ticker}: {e}")

    except RequestException as e:
        # Specifically catch network/connection issues
        logger.error(f"Network error while fetching market data: {e}")
    except Exception as e:
        # Catch other unexpected errors but log them clearly
        logger.error(
            f"Unexpected error in fetch_live_prices: {e}",
            exc_info=True)

    return prices


def format_shares(shares_data, live_prices: dict) -> list:
    formatted = []
    for row in shares_data:
        avail = float(row.available or 0)
        pending = float(row.pending or 0)
        price = live_prices.get(row.ticker_symbol, 0.0)

        formatted.append({
            "ticker": row.ticker_symbol,
            "available_shares": avail,
            "pending_shares": pending,
            "live_price": price,
            "available_value": round(avail * price, 2)
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
