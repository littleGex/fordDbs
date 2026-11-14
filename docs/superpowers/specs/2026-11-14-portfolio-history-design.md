# Portfolio value over time (#52)

Date: 2026-11-14
Issue: #52. Builds on #38 (instruments) and #45 (Trade Republic import).

## Goal

A line chart on the investments dashboard: market value of ETFs and stocks
against net money invested, per day, from the first trade to today.

Success:

- The chart's last point equals the dashboard's ETFs & stocks value.
- Imports, manual entries and ticker changes show up on the next load.
- A Yahoo outage never breaks the dashboard; it shows which prices are out
  of date.
- After the first fill, the history loads without waiting on Yahoo.

## Decisions

1. **ETFs and stocks only** (`etf_transactions`). Employee shares stay as
   they are; perhaps later from an SG Markets export.
2. **Invested = net money put in, fees included**: every row adds
   `fiat_invested + fees` (a buy adds its cost and fee; a sell or liquidation
   adds its negative proceeds plus its fee). The dashboard card's ETF
   "invested" changes to the same definition.
3. **Fill prices are price points** where Yahoo has no close; Yahoo wins on
   the same day.
4. **Price cache plus on-the-fly calculation**; nothing derived is stored.

## Data model (one Alembic migration, after `c4d8e2a6f0b1`)

Table `price_history`:

| column | type | |
|---|---|---|
| `ticker` | `String`, PK | |
| `day` | `Date`, PK | |
| `close` | `Numeric(14, 6)`, not null | unadjusted close, EUR |
| `fetched_at` | `DateTime`, server default now | |

Only finished days (before today) are stored.

## Price cache (`app/core/price_history.py`)

`ensure_price_history(db, tickers=None, *, through=None, download=None)
-> Dict[str, date]`

- `tickers=None` means every `ticker_symbol` in `etf_transactions` that is
  not a valid ISIN (ISIN-as-ticker rows are never fetched).
- `through` defaults to yesterday (Europe/Berlin).
- Per ticker, the missing range is from the day after its latest cached
  `day` (or from its first trade date if none) to `through`. Tickers with
  nothing missing are skipped.
- One batched download for all tickers that need data, from the earliest
  missing start: `yf.download(tickers, start=..., end=through + 1 day,
  interval="1d", auto_adjust=False, progress=False, timeout=10)`, reading
  the `Close` column per ticker. `download` is injectable (defaults to
  `yf.download` looked up at call time) for tests.
- Rows before each ticker's own missing start, after `through`, NaN, zero
  or negative are dropped.
- Inserted with Postgres `INSERT ... ON CONFLICT DO NOTHING`, then
  committed by the caller.
- Returns `{ticker: last cached day}` for tickers still short of `through`
  after the fetch (the stale list). A download exception is logged, caught,
  and leaves every requested ticker stale.

Scheduler: a job at 06:00 Europe/Berlin runs `ensure_price_history` with its
own session and commits; `misfire_grace_time=86400`.

## Calculation (`app/core/portfolio_history.py`)

`portfolio_history(db, today: date, live_prices: Dict[str, float])
-> List[dict]` returns `[{"date": "YYYY-MM-DD", "value": float, "invested":
float}]`, one per calendar day from the earliest `transaction_date` to
`today`; `[]` without transactions.

- All `etf_transactions` rows (any `entry_type`), grouped by `ticker_symbol`,
  dated by `transaction_date.date()`.
- Shares per ticker: running sum of `shares_acquired`.
- Invested: running sum of `fiat_invested + coalesce(fees, 0)` over all rows.
- Price of a ticker on day `d`: the most recent observation on or before `d`
  among (a) cached closes with `close > 0` and (b) fill prices
  `|fiat_invested| / |shares_acquired|` of its rows with non-zero shares and
  non-zero fiat. On the same date the close wins.
- On `today`, a ticker's live price (> 0) overrides.
- Value on `d` = sum over tickers with non-zero shares of shares × price.
  A ticker with shares but no price yet contributes 0 (cannot happen: its
  first row is a priced trade, unless that row has zero fiat).
- Values and invested rounded to cents.

## API

`GET /v1/investments/etf/history` (parents only, investments router):

1. `stale = ensure_price_history(db)`, commit.
2. `live = fetch_live_prices(tickers)` (as the dashboard does).
3. Response `{"points": [...], "stale": [{"ticker", "through"}], "as_of":
   today}`.

`get_grouped_etfs` (dashboard summary): `total_invested` becomes
`sum(fiat_invested + coalesce(fees, 0))`.

## Dashboard (`investments-frontend/src/views/DashboardView.vue`)

Section "Value over time" below the Total Wealth card, loaded by its own
request after the summary:

- Line "Value" (blue, filled) and line "Invested" (grey, stepped).
- Tooltip: date, value, invested, gain € and %.
- Range buttons 1M, 6M, YTD, 1Y, All (default), filtering client-side.
- About 6 x-axis labels.
- Under the chart, for each stale ticker: "Prices for X are up to date only
  until <date>."
- Hidden when there are no points.

## Testing

- Calculation (database rows + cached prices, no network): shares and
  invested build on trade dates, invested includes fees; a sell lowers
  invested by proceeds minus fee; weekend carries Friday's close; fill price
  where no close; close wins on the same day; liquidated fund priced at its
  fills then 0; zero-share or zero-fiat rows give no price; today uses the
  live price; empty portfolio gives `[]`.
- Cache (fake download): fetches only missing days, one batched call;
  skips ISIN-as-ticker rows and tickers already current; `auto_adjust=False`
  passed; drops NaN, zero and negative closes; repeated insert harmless;
  download failure leaves the cache unchanged and returns the tickers as
  stale.
- API: response shape; stale list; 401 without login; empty portfolio.
- Summary: `total_invested` includes fees.
- Scheduler: the 06:00 job is registered and calls `ensure_price_history`.
- Migration: upgrade, downgrade, upgrade on a scratch database.

## Rollout

Migration release: back up, build `api investments-ui`, run `alembic upgrade
head` in a one-off container, restart both. The first dashboard load fills the
cache; afterwards a read-only check of rows and date range per ticker in
`price_history` on the Pi.

## Out of scope

Employee shares over time; per-fund lines; benchmarks; dividends; weekly
downsampling.
