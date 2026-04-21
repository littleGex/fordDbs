import math
import pandas as pd
from unittest.mock import patch
from app.core.investments import fetch_live_prices


def test_fetch_live_prices_integration():
    """Test against the real yfinance API."""
    test_tickers = {"AIR.PA", "AAPL", "VWCE.DE"}
    results = fetch_live_prices(test_tickers)

    # 1. Assert all requested tickers are in the keys
    assert set(results.keys()) == test_tickers

    for ticker, price in results.items():
        # 2. Assert type is float
        assert isinstance(price, (float, int))

        # 3. Assert it's a real number (not NaN or Inf)
        assert math.isfinite(price)

        # 4. Assert the price is logically positive
        # (A price of 0.0 usually means the fetch failed)
        assert price > 0, f"Price for {ticker} should be greater than 0"

    # 5. Spot check a known range (Airbus shouldn't be 1.00 or 10,000.00)
    assert 50 < results["AIR.PA"] < 300


@patch('yfinance.download')
def test_fetch_live_prices_logic(mock_download):
    """Test how our function handles a specific DataFrame response."""
    mock_data = pd.DataFrame({
        ('Close', 'AAPL'): [150.0, 155.0],
        ('Close', 'AIR.PA'): [110.0, 112.0]
    }, index=[pd.Timestamp('2024-01-01'), pd.Timestamp('2024-01-02')])

    mock_data.columns = pd.MultiIndex.from_tuples(mock_data.columns)
    mock_download.return_value = mock_data

    tickers = {"AAPL", "AIR.PA"}
    results = fetch_live_prices(tickers)

    assert results["AAPL"] == 155.0
    assert results["AIR.PA"] == 112.0
