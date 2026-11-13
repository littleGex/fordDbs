# tests/test_instruments.py
"""
Tests for ISIN instruments (#38): the Instrument model, ISIN validation,
the ticker resolver and the service layer in app/core/instruments.py.

Only public ISINs are used here; the repo is public.
"""
from decimal import Decimal

from app.models.shares_models import EtfTransaction, Instrument


class TestInstrumentModel:

    def test_transaction_can_link_to_instrument(self, db_session):
        db_session.add(Instrument(isin="IE00B4L5Y983",
                                  yahoo_ticker="EUNL.DE", currency="EUR"))
        db_session.flush()
        db_session.add(EtfTransaction(
            ticker_symbol="EUNL.DE", isin="IE00B4L5Y983",
            fiat_invested=Decimal("10"), shares_acquired=Decimal("0.1")))
        db_session.flush()

        inst = db_session.get(Instrument, "IE00B4L5Y983")
        db_session.refresh(inst)
        assert inst.manual_override is False
        assert inst.created_at is not None
