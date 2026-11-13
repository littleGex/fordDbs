# ISIN instruments and Yahoo ticker resolution (#38)

Date: 2026-11-12
Issue: #38. Follow-up that depends on it: #45 (Trade Republic export import).

## Goal

Trade Republic identifies funds and stocks by ISIN. Prices come from Yahoo
Finance, which needs a ticker, and for European listings the ticker carries an
exchange suffix (`.DE`, `.PA`, ...). Make the ISIN the key for an instrument,
work out its Yahoo ticker automatically where that can be done safely, and
report the rest for a manual choice instead of guessing.

Success:

- Every ISIN that has a EUR listing on Yahoo resolves to a ticker that Yahoo
  prices in EUR. A USD or GBP listing is never picked.
- An ISIN that cannot be resolved safely is shown as unresolved, with the
  candidates and the reason, and can be set by hand.
- Existing transactions and schedules keep working unchanged, and can be
  linked to an ISIN without retyping them.
- #45's importer can call the resolver with the ISIN and the TR fill price and
  date, and get a checked ticker back.

## Findings from the spike (2026-11-12)

Throwaway scripts, not kept. Run from a Mac with yfinance 1.7.0.

Eight well-known public ETF ISINs with a known Xetra ticker
(e.g. `IE00B4L5Y983` -> `EUNL.DE`, `IE00BK5BQT80` -> `VWCE.DE`):

| Source | Correct Xetra ticker |
|---|---|
| Yahoo search with the ISIN as query | 1 / 8. Usually returns a single listing, 5 of 8 times the London listing priced in USD (e.g. `IWDA.L`, about 10% above the EUR price). |
| `<ISIN>.SG` symbols | 0 / 8. No price data. |
| OpenFIGI, German (`GR`) ticker + `.DE` | 6 / 8. Bloomberg and Yahoo tickers differ for the other 2 (`XMWO` vs `XDWD`, `DAXEX` vs `EXS1`). |
| Both, keeping only candidates Yahoo prices in EUR | 7 / 8. The 8th had no EUR candidate and stays unresolved. |

A second set of 9 ISINs (7 ETFs, 2 US stocks), each with a real EUR fill price
and date: all 8 still-listed instruments resolved to a EUR listing whose Yahoo
close on the fill date was within ±1% of the fill price. Wrong-currency
candidates were 9-19% off. One `.DE` ticker was reported by Yahoo in GBP, so
the currency check must not rely on the suffix. One fund had been liquidated
and had no candidates left.

## Decisions

1. Resolve with OpenFIGI + Yahoo search, keep EUR-priced candidates only,
   manual override for the rest.
2. Keep `ticker_symbol` on transactions and schedules, linked by a new
   nullable `isin`. Pricing, the dashboard and the scheduler are unchanged.
   Changing an instrument's ticker rewrites `ticker_symbol` on its linked rows.
3. Sanity check against a reference fill price uses Yahoo's close on the fill
   date, tolerance 5%.

## Data model (one Alembic migration)

New table `instruments`:

| Column | Type | Notes |
|---|---|---|
| `isin` | `String(12)` | Primary key. Validated (format and check digit) before storing. |
| `yahoo_ticker` | `String`, nullable | NULL means unresolved. |
| `name` | `String`, nullable | From the caller, else OpenFIGI or Yahoo. |
| `currency` | `String(3)`, nullable | Currency Yahoo reports for `yahoo_ticker`. Always `EUR` when set. |
| `resolved_at` | `DateTime`, nullable | When the ticker was last set. |
| `manual_override` | `Boolean`, not null, default false | True when the ticker was set by hand. Automatic lookups never change it. |
| `resolution_note` | `Text`, nullable | Why it is or is not resolved, with candidates. |
| `created_at` | `DateTime`, server default now | |

New column `isin` (`String(12)`, nullable, indexed, foreign key to
`instruments.isin`) on `etf_transactions` and `etf_purchase_schedule`.
Existing rows stay NULL.

## Resolver (`app/core/instruments.py`)

No database or FastAPI code. Network access goes through three small
functions passed in as arguments (defaults are the real implementations), so
tests use plain fake functions instead of patching internals:

- `figi_tickers(isin) -> list[str]`: OpenFIGI `v3/mapping`, `idType=ID_ISIN`,
  tickers on exchange code `GR`, each with `.DE` appended. No API key.
- `yahoo_search(isin) -> list[tuple[str, str | None]]`: yfinance `Search(isin)`
  quote symbols with their short names (the name source).
- `yahoo_quote(ticker, on: date | None) -> (currency, close)`: currency from
  Yahoo's metadata; close is the last close on or before `on` (within a few
  days), or the latest close when `on` is None. Raises or returns no close
  when Yahoo has no data.

```python
@dataclass
class Candidate:
    ticker: str
    currency: str | None
    close: Decimal | None
    accepted: bool
    reason: str  # e.g. "priced in USD", "no Yahoo data", "4.1% off reference"

@dataclass
class Resolution:
    isin: str
    ticker: str | None
    currency: str | None
    name: str | None
    candidates: list[Candidate]
    note: str

def resolve_isin(isin, reference=None, *, figi_tickers=..., yahoo_search=...,
                 yahoo_quote=...) -> Resolution
```

`reference` is an optional `(date, Decimal eur_price)`.

Steps:

1. Validate the ISIN (two letters, nine alphanumerics, check digit). Invalid
   raises `ValueError` and makes no network call.
2. Candidates: `figi_tickers` then `yahoo_search`, de-duplicated, order kept.
3. Quote each candidate (on the reference date if given). Accept only
   candidates Yahoo prices in EUR with a close.
4. Pick the first accepted `.DE` candidate, else the first accepted candidate.
5. With a reference, the pick's close must be within 5% of the reference
   price. If not, nothing is picked: the result is unresolved and the note
   says by how much it was off.
6. No accepted candidate: unresolved, note lists the candidates and reasons.
7. A lookup error (timeout, HTTP error, rate limit) from any source is caught
   per source: the other source is still used. If no candidate could be
   checked because of errors, the note says "lookup failed, retry later".
   `resolve_isin` never raises for network problems.

Timeouts: about 10 seconds per HTTP call.

Without a reference, only the EUR check applies and the note says the pick
was not checked against a fill price.

## Service layer (in `app/core/instruments.py` or a sibling module)

Database operations used by the API and later by #45. All changes to tickers
go through one function:

- `set_instrument_ticker(db, instrument, ticker, currency, *, manual)`: sets
  the instrument's ticker, currency, `resolved_at`, `manual_override`, and
  updates `ticker_symbol` on every `etf_transactions` and
  `etf_purchase_schedule` row with that ISIN. Caller commits.
- `get_or_resolve(db, isin, name=None, reference=None)`: returns the stored
  instrument if it exists, resolved or not, without a lookup; else creates it
  and runs `resolve_isin`. Retrying an unresolved instrument is always an
  explicit re-resolve. Used by `POST /instruments` and by #45.
- `link_ticker(db, instrument, ticker_symbol)`: sets `isin` on rows with that
  `ticker_symbol` and NULL `isin`. If the instrument is resolved, their
  `ticker_symbol` becomes the instrument's ticker. Rows already linked to a
  different ISIN are left alone and counted as conflicts.

## API (`/v1/investments`, parents only like the rest of the router)

| Method and path | Body | Result |
|---|---|---|
| `GET /instruments` | | All instruments with status (`resolved`, `unresolved`, `override`), note, and counts of linked transactions and schedules. |
| `POST /instruments` | `{isin, name?}` | Create and resolve, or return the existing one without a new lookup. 400 for an invalid ISIN. |
| `POST /instruments/{isin}/resolve` | | Run the lookup again. 409 for a manual override. 404 if unknown. |
| `PUT /instruments/{isin}/ticker` | `{yahoo_ticker, confirm?}` | Manual override. 400 unless Yahoo prices it in EUR. If the instrument has a reference (latest linked transaction's price and date) and the close is more than 5% off, 409 with the numbers unless `confirm` is true. |
| `POST /instruments/{isin}/link` | `{ticker_symbol}` | Link existing rows. Returns `{transactions, schedules, conflicts}`. 404 if no rows have that ticker. |
| `POST /etf/schedule` | new optional `isin` query param | If given, the instrument must exist and be resolved (400 otherwise); the schedule's ticker comes from it. |

Lookups run inside the request. This is an admin-only screen used rarely.

## Admin page (`investments-frontend/src/views/AdminView.vue`)

New "Instruments" section:

- Table: ISIN, name, ticker, currency, status and note. Unresolved rows are
  highlighted.
- Per row: "Re-resolve" (hidden for overrides), "Set ticker" (input +
  button; on a 409 mismatch shows the numbers and asks to confirm), "Link
  existing ticker" (input + button, shows the counts).
- "Add ISIN" form (ISIN, optional name).
- The schedule form gets an optional ISIN field.

## Testing

- Resolver unit tests with fake lookup functions shaped like the spike:
  GBP-priced `.DE` rejected; USD listings rejected; `.DE` preferred over
  another EUR listing; falls back to a non-`.DE` EUR listing; reference more
  than 5% off leaves it unresolved; no candidates leaves it unresolved; one
  source failing still uses the other; both failing gives "lookup failed";
  invalid ISIN raises with no lookup calls.
- ISIN check digit: valid public ISINs and corrupted versions.
- API tests with the resolver's lookups faked: create then cached (no second
  lookup); invalid ISIN 400; override EUR check; mismatch 409 then confirm;
  override rewrites linked rows' `ticker_symbol`; link sets `isin`, syncs
  tickers and counts conflicts; re-resolve refuses an override; schedule with
  a resolved and an unresolved ISIN; 401 without login.
- Migration: `alembic upgrade head` then `downgrade -1` and `upgrade head`
  against the test database (CI builds tables with `create_all`).
- One live test against OpenFIGI and Yahoo with a public ISIN, marked
  `live_api` so it is skipped by default.

## Rollout

The release contains a migration. The app's startup `create_all` creates
`instruments` but not the new `isin` columns, so the migration skips creating
`instruments` if it exists, and on the Pi it runs before the API restarts:
build, then `docker compose run --rm api alembic -c /code/alembic.ini upgrade
head`, then `docker compose up -d api investments-ui`. Existing data is
untouched. Afterwards, add ISINs and link the
existing tickers in the admin panel.

## Out of scope

- The Trade Republic export import (#45). Noted for it: a liquidated
  instrument has no ticker but still has history; #45 decides how to store
  its rows (proposal: use the ISIN as `ticker_symbol`).
- An `isin` column in `/etf/bulk-add`.
- Converting non-EUR prices.
- Deleting instruments.
