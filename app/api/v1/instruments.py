# app/api/v1/instruments.py
"""
Instruments (#38): ISINs and the Yahoo tickers used to price them.
Mounted under /v1/investments, parents only (see app/main.py).
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core import instruments as svc
from app.database.database import get_db
from app.models.shares_models import (EtfPurchaseSchedule, EtfTransaction,
                                      Instrument)

instruments_router = APIRouter()


class InstrumentCreate(BaseModel):
    isin: str
    name: Optional[str] = None


class TickerOverride(BaseModel):
    yahoo_ticker: str
    confirm: bool = False


class LinkRequest(BaseModel):
    ticker_symbol: str


def _status(instrument: Instrument) -> str:
    if instrument.manual_override:
        return "override"
    return "resolved" if instrument.yahoo_ticker else "unresolved"


def _to_json(db: Session, instrument: Instrument) -> dict:
    def count(model):
        return db.query(model).filter(
            model.isin == instrument.isin).count()

    return {
        "isin": instrument.isin,
        "name": instrument.name,
        "yahoo_ticker": instrument.yahoo_ticker,
        "currency": instrument.currency,
        "status": _status(instrument),
        "resolution_note": instrument.resolution_note,
        "resolved_at": instrument.resolved_at,
        "transactions": count(EtfTransaction),
        "schedules": count(EtfPurchaseSchedule),
    }


def _get_instrument(db: Session, isin: str) -> Instrument:
    try:
        isin = svc.normalize_isin(isin)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    instrument = db.get(Instrument, isin)
    if instrument is None:
        raise HTTPException(status_code=404,
                            detail=f"Unknown ISIN {isin}")
    return instrument


@instruments_router.get("/instruments")
def list_instruments(db: Session = Depends(get_db)):
    rows = db.query(Instrument).order_by(Instrument.isin).all()
    return [_to_json(db, i) for i in rows]


@instruments_router.post("/instruments")
def add_instrument(body: InstrumentCreate, db: Session = Depends(get_db)):
    """Add an ISIN and look up its ticker; an ISIN already stored is
    returned as it is."""
    try:
        instrument = svc.get_or_resolve(db, body.isin, name=body.name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    db.commit()
    return _to_json(db, instrument)


@instruments_router.post("/instruments/{isin}/resolve")
def resolve_instrument(isin: str, db: Session = Depends(get_db)):
    instrument = _get_instrument(db, isin)
    try:
        svc.re_resolve(db, instrument)
    except PermissionError as e:
        raise HTTPException(status_code=409, detail=str(e))
    db.commit()
    return _to_json(db, instrument)


@instruments_router.put("/instruments/{isin}/ticker")
def override_ticker(isin: str, body: TickerOverride,
                    db: Session = Depends(get_db)):
    """Set the ticker by hand. Yahoo must price it in EUR; a close more
    than PRICE_TOLERANCE off the latest linked fill needs confirm."""
    instrument = _get_instrument(db, isin)
    ticker = body.yahoo_ticker.strip().upper()
    if not ticker:
        raise HTTPException(status_code=400, detail="Ticker is empty")

    reference = svc.reference_for(db, instrument.isin)
    try:
        currency, close = svc.yahoo_quote(
            ticker, reference[0] if reference else None)
    except LookupError:
        raise HTTPException(status_code=400,
                            detail=f"Yahoo has no data for {ticker}")
    except Exception:
        raise HTTPException(status_code=502,
                            detail="Could not check the ticker with "
                                   "Yahoo; try again later")
    if currency != "EUR":
        priced_in = currency or "an unknown currency"
        raise HTTPException(
            status_code=400,
            detail=f"{ticker} is priced in {priced_in}, not EUR")
    if close is None:
        raise HTTPException(status_code=400,
                            detail=f"Yahoo has no recent price for {ticker}")

    note = f"Set by hand to {ticker}."
    if reference:
        ref_date, ref_price = reference
        off = abs(close - ref_price) / ref_price
        if off > svc.PRICE_TOLERANCE:
            if not body.confirm:
                raise HTTPException(status_code=409, detail={
                    "message": f"{ticker} closed at {close} on {ref_date}, "
                               f"{off:.1%} off the fill price {ref_price}.",
                    "reference_date": ref_date.isoformat(),
                    "reference_price": str(ref_price),
                    "close": str(close),
                })
            note += (f" Confirmed although its close was {off:.1%} off "
                     f"the fill price on {ref_date}.")

    svc.set_instrument_ticker(db, instrument, ticker, currency, manual=True)
    instrument.resolution_note = note
    db.commit()
    return _to_json(db, instrument)


@instruments_router.post("/instruments/{isin}/link")
def link_instrument(isin: str, body: LinkRequest,
                    db: Session = Depends(get_db)):
    """Attach existing transactions and schedules with a ticker to this
    ISIN."""
    instrument = _get_instrument(db, isin)
    try:
        counts = svc.link_ticker(db, instrument, body.ticker_symbol)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    db.commit()
    return counts
