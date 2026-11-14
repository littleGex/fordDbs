# Trade Republic export import (#45, closes #39)

Date: 2026-11-14
Issues: #45 (this design), #39 (its remaining part, `external_id` dedupe, is
included here). Builds on #38 (`docs/superpowers/specs/2026-11-12-isin-instruments-design.md`).

## Goal

Load the Trade Republic app's transaction export (Service → Kontoauszüge →
Transaktionsexport) straight into the app to seed the investment history, and
re-import newer exports later without duplicates. No Trade Republic login or
API.

Success:

- The first import of a real export stores every buy and sell, linked to its
  ISIN, with real dates, amounts and fees.
- Re-importing a newer export adds only the new rows.
- Nothing about the import is silent: ignored rows are counted by reason,
  unknown row types are listed with line numbers, unresolved ISINs and
  warnings are reported.
- A dry run shows all of that without storing anything.

## Decisions

1. **Trade Republic is the source of truth for its savings plans.** No app
   schedules for them; the user re-imports after each month's buys. The import
   never touches `entry_type="scheduled"` rows. The admin page warns before
   creating a schedule for a fund that has imported fills.
2. **An ISIN without a ticker still imports**, with the ISIN itself as
   `ticker_symbol`. It is listed as unresolved; setting its ticker in the
   Instruments section renames the rows (#38's ticker sync). Until then the
   holding values at 0.
3. **Stocks import together with funds** into `etf_transactions`.
4. **Dividends are not imported** (counted as ignored).
5. **Server-side parser and endpoint**, a file picker on the admin page, no
   command-line converter.
6. **Unknown row types do not block the import**: the rest imports and the
   unknown rows are listed. Re-importing later is safe thanks to dedupe.
7. **A liquidation sell is identified by its ISIN**; if a re-import finds a
   different net, it is skipped with a warning, not added a second time.
8. **Dry run included.**

## Export format

Header as exported:

`datetime,date,account_type,category,type,asset_class,name,symbol,shares,price,amount,fee,tax,currency,original_amount,original_currency,fx_rate,description,transaction_id,counterparty_name,counterparty_iban,payment_reference,mcc_code`

`symbol` is the ISIN. `transaction_id` is stable and unique. `date` is the
trade date; `datetime` is the booking time and can be days later.

The export contains the account holder's name, IBAN and holdings. It is never
committed; `.gitignore` gets `*Transaction_export*.csv`.

## Data model (one Alembic migration, after `a7c3e9f1b2d4`)

- `etf_transactions.external_id`: `String`, nullable, unique. Holds the
  Trade Republic `transaction_id`, or `liquidation:<ISIN>` for a netted
  liquidation sell.

## Parser (`app/core/tr_import.py`)

`parse_tr_export(csv_text: str) -> ParseResult`. Pure: no database, no
network.

```python
@dataclass
class ParsedTxn:
    line: int            # CSV line of the row (or the last row of a group)
    external_id: str
    isin: str
    name: str | None
    transaction_type: str  # "buy" or "sell"
    trade_date: date
    shares: Decimal        # signed: + buy, - sell
    fiat: Decimal          # signed: + buy, - sell (proceeds)
    fees: Decimal          # >= 0
    price: Decimal | None  # fill price (EUR) for buys, used as reference

@dataclass
class ParseResult:
    transactions: list[ParsedTxn]
    ignored: dict[str, int]   # reason -> count
    unknown: list[dict]       # {"line", "category", "type"}
```

Rules:

- **Header** must include every column the parser reads (`date`, `category`,
  `type`, `name`, `symbol`, `shares`, `price`, `amount`, `fee`, `currency`,
  `transaction_id`). Missing columns raise `ValueError` naming them.
- **`TRADING` + `BUY`** → buy. `shares` = |shares|, `fiat` = |amount| (the
  amount excludes the fee), `fees` = |fee| (empty = 0), `price` from the
  `price` column, `external_id` = `transaction_id`.
- **`TRADING` + `SELL`** → sell with the app's signs: `shares` = −|shares|,
  `fiat` = −|amount|, `fees` = |fee|.
- **Liquidation**: per ISIN, net = sum of `shares` over `CORPORATE_ACTION`
  rows of type `LIQUIDATION_DIVIDEND` and `LIQUIDATION_DIVIDEND_CANCELLED`,
  and sum of `amount` over `CASH` rows of type `LIQUIDATION_PROCEEDS`.
  Non-zero net shares → one sell: `shares` = net (negative), `fiat` =
  −|net amount|, `fees` = 0, dated with the latest `date` of the group,
  `external_id` = `liquidation:<ISIN>`. Net shares zero → ignored as
  `"liquidation cancelled"`. Withheld tax is not stored.
- **Every other `CASH` row** (top-ups, transfers, Vorabpauschale, dividends,
  interest) → ignored as `"cash"`.
- **Anything else** (other `CORPORATE_ACTION` types, other `TRADING` types,
  other categories) → `unknown`.
- **Errors** (`ValueError` naming the CSV line): a buy or sell whose
  `currency` is not `EUR`; empty `symbol` or `transaction_id` on a buy or
  sell; an invalid ISIN (#38's `normalize_isin`); an unparseable number or
  date; the same non-empty `transaction_id` on two rows of any category
  (a broken or concatenated file).

Amounts are parsed as `Decimal`.

## Import (`app/core/tr_import.py`)

`import_tr_export(db, csv_text, *, dry_run=False, resolver=resolve_isin,
clock=time.monotonic) -> ImportResult`, one database transaction:

1. Parse. A `ValueError` propagates (the endpoint returns 400).
2. Dedupe: rows whose `external_id` is already stored are skipped and
   counted. For a `liquidation:` id whose stored shares or fiat differ from
   the new net, add a warning.
3. Resolve the ISINs of the new rows through #38's `get_or_resolve`, with the
   name from the export and the latest buy's `(trade_date, price)` as the
   reference (none if the ISIN has no buy in the file). Existing instruments
   are not looked up again. Lookups stop once `RESOLVE_BUDGET_SECONDS = 60`
   have passed (measured with `clock`); ISINs left are created unresolved
   with the note `"not looked up yet, press Re-resolve"`.
4. Insert each new row: `ticker_symbol` = the instrument's `yahoo_ticker`, or
   the ISIN if unresolved; `isin`; `external_id`; `entry_type="import"`;
   `transaction_type`; `fees`; `transaction_date` = trade date at midnight.
5. Commit once, or roll back everything (including instruments created in
   step 3) for a dry run. #38's service functions only flush, never commit,
   so the import owns the single commit or rollback.

```python
@dataclass
class ImportResult:
    imported: int              # would be imported, for a dry run
    skipped_duplicates: int
    ignored: dict[str, int]
    unknown: list[dict]
    unresolved: list[str]      # ISINs of new rows without a ticker
    warnings: list[str]
    dry_run: bool
```

## API

`POST /v1/investments/etf/import/trade-republic` (parents only, investments
router), body `{"csv_data": str, "dry_run": bool = false}`.

- 200 with the `ImportResult` fields as JSON.
- 400 with the parser's message for a parse error, or "nothing was imported"
  for a database error.
- 413 if `csv_data` is over 5 MB.

`GET /v1/investments/instruments`: each instrument also gets `imported`, the
number of its transactions with `entry_type="import"`.

## Admin page (`investments-frontend/src/views/AdminView.vue`)

New card "Import Trade Republic export":

- File picker (`.csv`), read in the browser; files over 5 MB are refused
  before sending.
- "Check file" (dry run) and "Import" buttons.
- Results shown on the page: imported / would import, duplicates skipped,
  ignored by reason, unknown rows with line numbers, warnings, unresolved ISINs
  with a pointer to the Instruments section.
- After a real import, the Instruments and Schedules lists refresh.

Schedule form: if the ISIN given, or an instrument whose ticker equals the
ticker given, has `imported > 0`, confirm first: "Trade Republic fills for
this fund are imported; an app schedule would count them twice. Create
anyway?"

## Testing

Fixture `tests/fixtures/tr_export_sample.csv`: the structure of the redacted
#45 sample with public ISINs, invented transaction ids and invented amounts,
plus a synthetic `SELL` and a synthetic unknown type.

- Parser: buy with fee; savings-plan buy (amount excludes fee); trade `date`
  used, not `datetime`; liquidation netting including the cancellation → one
  sell; fully cancelled liquidation ignored; cash, Vorabpauschale and dividend
  rows counted as ignored; synthetic `SELL`; synthetic unknown type reported
  with its line; errors for missing header column, non-EUR trade,
  unparseable number, duplicate `transaction_id`, invalid ISIN.
- Import (database, fake resolver): rows linked by ISIN with the instrument's
  ticker; unresolved ISIN imports with the ISIN as ticker and is renamed when
  its ticker is set; latest buy's price and date passed as reference;
  existing instrument not looked up again; re-import skips everything; changed
  liquidation net warns; dry run stores nothing (not even instruments); time
  budget leaves remaining ISINs unresolved (fake clock); database error rolls
  everything back.
- API: response shape; 400 on parse error; 413 on size; dry run; 401 without
  login; `imported` count on instruments.
- Migration: upgrade, downgrade, upgrade on a scratch database.

## Rollout

Migration release, same order as v2.15.0: back up the database, build, run
`alembic upgrade head` in a one-off container, restart `api` and
`investments-ui`. Then on the live site: "Check file" with the real export,
read the result, "Import", and set tickers for unresolved ISINs. The PR
closes #45 and #39.

## Out of scope

Dividends and withheld tax; a separate stocks view; replacing scheduled
estimates with real fills; a command-line converter.
