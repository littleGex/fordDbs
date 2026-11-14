"""
Tests for the Trade Republic export import (#45): the external_id
column, the parser and the import service in app/core/tr_import.py.

The fixture is synthetic: public ISINs, invented ids and amounts. Never
commit a real export.
"""
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.shares_models import EtfTransaction


class TestExternalIdColumn:

    def test_external_id_is_unique(self, db_session):
        for _ in range(2):
            db_session.add(EtfTransaction(
                ticker_symbol="EUNL.DE", fiat_invested=Decimal("1"),
                shares_acquired=Decimal("1"), external_id="tx-1"))
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_external_id_is_optional(self, db_session):
        txn = EtfTransaction(ticker_symbol="EUNL.DE",
                             fiat_invested=Decimal("1"),
                             shares_acquired=Decimal("1"))
        db_session.add(txn)
        db_session.flush()
        assert txn.external_id is None
