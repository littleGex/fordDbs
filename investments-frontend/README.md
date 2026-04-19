# Investments Frontend

A Vue.js frontend for managing employee shares and ETF investments.

## Features

- **Portfolio Dashboard**: View employee shares and ETF holdings with live prices
- **Admin Panel**: Add shares, record ETF transactions, manage purchase schedules
- **Bulk Data Import**: CSV upload for historical share and ETF data
- **ETF Management**: Buy/sell transactions and automated purchase schedules

## Setup

1. Install dependencies:
   ```bash
   npm install
   ```

2. Run development server:
   ```bash
   npm run dev
   ```

3. Build for production:
   ```bash
   npm run build
   ```

## Environment Variables

Set `VITE_API_BASE` to the backend API URL (default: http://localhost:8005/v1)

## Usage Guide

### Adding Employee Shares

#### Individual Share Entry
1. Navigate to Admin Panel (`/admin`) - requires password `1682`
2. Use the "Add Employee Share" form:
   - **Ticker Symbol**: Stock ticker (e.g., AAPL, GOOGL)
   - **Number of Shares**: Quantity (supports decimals)
   - **Vest Date**: When shares become available for trading (YYYY-MM-DD)
   - **Purchase Price**: Cost basis (optional)

#### Bulk Import Historical Shares (CSV)
Use the "Bulk Import Shares" section with CSV format:
```
ticker,num_shares,vest_date,purchase_price
AAPL,100,2024-01-01,150.00
GOOGL,50,2024-02-01,2800.00
MSFT,75,2027-01-01,300.00
```

**CSV Format Details:**
- `ticker`: Stock symbol (uppercase automatically)
- `num_shares`: Number of shares (decimal supported)
- `vest_date`: Date when shares become available (YYYY-MM-DD)
- `purchase_price`: Optional cost basis

**Example Use Cases:**
- **Current shares**: Set `vest_date` to past date (e.g., 2024-01-01)
- **Future vesting**: Set `vest_date` to future date (e.g., 2027-01-01 for shares vesting in 2027)

### ETF Management

#### Recording ETF Transactions
Use the "Record ETF Transaction" form:
- **Ticker Symbol**: ETF ticker (e.g., VTI, VXUS)
- **Fiat Amount**: Investment amount or sale proceeds
- **Shares Acquired**: Number of shares (positive for buys, negative for sells)
- **Transaction Type**: "Buy" or "Sell"

#### Bulk Import ETF Transactions (CSV)
Use the "Bulk Import ETF Transactions" section with CSV format:
```
ticker,fiat_amount,shares_acquired,transaction_date,fees,transaction_type
VTI,1000.00,10.5,2024-01-01,5.00,buy
VXUS,500.00,-7.2,2024-02-01,2.50,sell
BND,750.00,15.3,2024-03-01,3.75,buy
```

**CSV Format Details:**
- `ticker`: ETF symbol
- `fiat_amount`: Investment amount (positive) or sale proceeds (positive)
- `shares_acquired`: Shares bought (+) or sold (-)
- `transaction_date`: Transaction date (YYYY-MM-DD)
- `fees`: Optional transaction fees
- `transaction_type`: "buy" or "sell"

#### Automated ETF Purchases
Create recurring purchase schedules:
- **Ticker Symbol**: ETF to purchase
- **Fiat Amount**: Monthly investment amount
- **Execution Day**: Day of month (1-28) to execute purchase

Schedules run automatically and can be managed/deleted from the admin panel.

### Portfolio Dashboard

- **Live Pricing**: Real-time stock/ETF prices via Yahoo Finance
- **Available vs Pending**: Shares shown as available (vested) or pending (future vesting)
- **ROI Tracking**: Performance metrics for ETF holdings
- **Net Positions**: ETF holdings account for both buys and sells
