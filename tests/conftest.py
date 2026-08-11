# tests/conftest.py
"""
Shared pytest fixtures for the pocket money test suite.

Requires a REAL Postgres instance for tests (set via env vars below),
since the precision bug this suite guards against is Postgres-specific
NUMERIC behavior that SQLite does not faithfully replicate.

Recommended: run a disposable Postgres container alongside your dev DB,
e.g.:

    docker run --rm -d \
        --name forddbs-test-db \
        -e POSTGRES_USER=test \
        -e POSTGRES_PASSWORD=test \
        -e POSTGRES_DB=forddbs_test \
        -p 5434:5432 \
        postgres:15-alpine

Then run tests with:

    TEST_DB_HOST=localhost TEST_DB_PORT=5434 \
    TEST_POSTGRES_USER=test TEST_POSTGRES_PASSWORD=test \
    TEST_POSTGRES_DB=forddbs_test \
    pytest

If TEST_* env vars are not set, sensible localhost defaults matching the
container command above are used.
"""
import os
import pytest
from decimal import Decimal
from datetime import date, datetime, timedelta, timezone

from jose import jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

# --- Build the test database URL BEFORE importing any app modules ---
# app/database/database.py reads env vars at import time, so we override
# them here first to point the whole app at the test database.
os.environ["POSTGRES_USER"] = os.getenv("TEST_POSTGRES_USER", "test")
os.environ["POSTGRES_PASSWORD"] = os.getenv("TEST_POSTGRES_PASSWORD", "test")
os.environ["DB_HOST"] = os.getenv("TEST_DB_HOST", "localhost")
os.environ["DB_PORT"] = os.getenv("TEST_DB_PORT", "5434")
os.environ["POSTGRES_DB"] = os.getenv("TEST_POSTGRES_DB", "forddbs_test")
os.environ.setdefault("ADMIN_PASSWORD", "test-admin-password")
os.environ.setdefault("ALLOWED_ORIGINS", "")

from app.database.database import Base, get_db, get_db_url  # noqa: E402
from app.models.user_models import Child, Transaction, Wish, User  # noqa: E402
from app.models.deductions_models import DeductionType  # noqa: E402
# Importing these registers them on Base.metadata / SQLAlchemy's mapper
# registry, mirroring what app.main does — without this, mapper
# configuration fails with errors like KeyError: 'Photo'.
from app.models.photo_model import Photo, Album, Like, Comment, View  # noqa: E402,F401
from app.models.shares_models import (  # noqa: E402,F401
    EmployeeShare, EtfTransaction, EtfPurchaseSchedule
)
from app.models.utilities import Utils  # noqa: E402,F401
from app.api.v1.family_photos import hash_pw, SECRET_KEY, ALGORITHM  # noqa: E402


TEST_DATABASE_URL = get_db_url()


@pytest.fixture(scope="session")
def db_engine():
    """
    Session-scoped engine pointed at the test Postgres database.
    Creates all tables once at the start of the test session and drops
    them at the end. Fails loudly if it can't connect — we never want
    this suite silently running against the wrong (e.g. production) DB.
    """
    engine = create_engine(TEST_DATABASE_URL)

    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
    except Exception as exc:
        pytest.exit(
            "Could not connect to the TEST Postgres database at "
            f"{TEST_DATABASE_URL!r}. Refusing to run — these tests must "
            "run against a real, disposable Postgres instance, never "
            "against production. Original error: "
            f"{exc}"
        )

    # Safety check: never run against something that looks like the
    # real app database.
    if "forddbs_test" not in TEST_DATABASE_URL and "test" not in TEST_DATABASE_URL:
        pytest.exit(
            "Refusing to run: TEST_DATABASE_URL does not look like a "
            f"test database ({TEST_DATABASE_URL!r}). Set TEST_* env vars "
            "to point at a disposable test database."
        )

    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture
def db_session(db_engine):
    """
    Function-scoped session wrapped in a transaction that's rolled back
    after every test, so tests never leak state into one another.
    """
    connection = db_engine.connect()
    transaction = connection.begin()
    SessionLocal = sessionmaker(autocommit=False, autoflush=False,
                                bind=connection)
    session = SessionLocal()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def app(db_session):
    """
    FastAPI app instance with the get_db dependency overridden to use
    the rollback-wrapped test session.
    """
    from app.main import create_app

    test_app = create_app()

    def override_get_db():
        try:
            yield db_session
        finally:
            pass  # session lifecycle is managed by db_session fixture

    test_app.dependency_overrides[get_db] = override_get_db
    return test_app


@pytest.fixture
def client(app):
    """Synchronous TestClient for hitting the API directly."""
    return TestClient(app)


@pytest.fixture
def admin_password():
    return os.environ["ADMIN_PASSWORD"]


# ---------------------------------------------------------------------
# Factory fixtures
# ---------------------------------------------------------------------

@pytest.fixture
def make_child(db_session):
    """Factory fixture: make_child(name="Penelope", balance="0.00")"""
    created = []

    def _make_child(name="TestChild", balance="0.00", birth_date=None):
        child = Child(
            name=name,
            balance=Decimal(balance),
            birth_date=birth_date,
        )
        db_session.add(child)
        db_session.commit()
        db_session.refresh(child)
        created.append(child)
        return child

    return _make_child


@pytest.fixture
def make_deduction_type(db_session):
    """Factory fixture: make_deduction_type(name="Unmade Bed", default_amount="0.50")"""
    def _make(name="Unmade Bed", default_amount="0.50"):
        dtype = DeductionType(name=name, default_amount=Decimal(default_amount))
        db_session.add(dtype)
        db_session.commit()
        db_session.refresh(dtype)
        return dtype

    return _make


@pytest.fixture
def child_age_10(make_child):
    """A child whose birth date makes them exactly 10 years old today."""
    today = date.today()
    birth_date = date(today.year - 10, today.month, today.day)
    return make_child(name="DecadeKid", balance="0.00", birth_date=birth_date)


@pytest.fixture
def make_real_child():
    """
    Factory fixture: like make_child, but commits through a genuinely
    separate SessionLocal() connection instead of the rollback-wrapped
    db_session.

    db_session is bound to a Connection that already has an external
    transaction started via connection.begin() (see db_session above).
    Under Postgres's default READ COMMITTED isolation, rows "committed"
    through that session are never actually committed at the protocol
    level -- they're invisible to any other connection until the outer
    transaction itself commits, which it never does (only rollback, at
    teardown). Code under test that opens its own independent session
    -- like run_weekly_payout(), which calls SessionLocal() directly --
    therefore can't see anything created via make_child/child_age_10,
    no matter how many times db_session.commit() is called.

    Use this fixture (not make_child/child_age_10) for any test that
    calls such code and asserts on rows it reads or writes.
    """
    from app.database.database import SessionLocal as RealSessionLocal
    created_ids = []

    def _make_real_child(name="RealChild", balance="0.00", birth_date=None):
        session = RealSessionLocal()
        try:
            child = Child(name=name, balance=Decimal(balance),
                          birth_date=birth_date)
            session.add(child)
            session.commit()
            session.refresh(child)
            created_ids.append(child.id)
            return child
        finally:
            session.close()

    yield _make_real_child

    if created_ids:
        session = RealSessionLocal()
        try:
            session.query(Transaction).filter(
                Transaction.child_id.in_(created_ids)
            ).delete(synchronize_session=False)
            session.query(Child).filter(
                Child.id.in_(created_ids)
            ).delete(synchronize_session=False)
            session.commit()
        finally:
            session.close()


@pytest.fixture
def real_child_age_10(make_real_child):
    """A genuinely-committed child, exactly 10 years old today."""
    today = date.today()
    birth_date = date(today.year - 10, today.month, today.day)
    return make_real_child(name="RealDecadeKid", balance="0.00",
                           birth_date=birth_date)


@pytest.fixture
def make_user(db_session):
    """Factory fixture: make_user(username="alice", display_name="Alice")"""
    counter = {"n": 0}

    def _make_user(username=None, display_name=None, role="parent",
                   profile_photo_key=None, password=None):
        counter["n"] += 1
        user = User(
            username=username or f"user{counter['n']}",
            display_name=display_name,
            role=role,
            profile_photo_key=profile_photo_key,
            hashed_password=hash_pw(password) if password else None,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
        return user

    return _make_user


@pytest.fixture
def make_photo(db_session):
    """Factory fixture: make_photo(uploader, caption="...")"""
    counter = {"n": 0}

    def _make_photo(uploader, caption=None, album_id=None):
        counter["n"] += 1
        photo = Photo(
            minio_key=f"test-photo-{counter['n']}.jpg",
            caption=caption,
            uploader_id=uploader.id,
            album_id=album_id,
        )
        db_session.add(photo)
        db_session.commit()
        db_session.refresh(photo)
        return photo

    return _make_photo


@pytest.fixture
def auth_headers():
    """auth_headers(user) -> a valid Bearer-token header dict for that user."""
    def _auth_headers(user):
        token = jwt.encode(
            {"sub": str(user.id),
             "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
            SECRET_KEY,
            algorithm=ALGORITHM,
        )
        return {"Authorization": f"Bearer {token}"}

    return _auth_headers


# ---------------------------------------------------------------------
# live_api opt-in gate
# ---------------------------------------------------------------------
#
# live_api tests call real external APIs (e.g. Yahoo Finance) and are
# excluded by default, ALWAYS, regardless of any -m marker expression
# used on the command line. This is deliberately NOT implemented via
# `addopts = -m "not live_api"` in pytest.ini, because pytest's -m flag
# on the command line REPLACES addopts' -m rather than combining with
# it -- so `pytest -m "not integration"` would silently let live_api
# tests back in if exclusion relied on addopts. Using a collection
# hook instead means live_api tests are skipped unconditionally unless
# the new --run-live-api flag is passed, independent of any -m usage.

def pytest_addoption(parser):
    parser.addoption(
        "--run-live-api",
        action="store_true",
        default=False,
        help="Run tests marked live_api (hits real external APIs, e.g. "
             "Yahoo Finance). Excluded by default for determinism.",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-live-api"):
        return  # explicitly requested -- don't skip anything

    skip_live_api = pytest.mark.skip(
        reason="live_api tests are excluded by default; run with "
               "--run-live-api to include them"
    )
    for item in items:
        if "live_api" in item.keywords:
            item.add_marker(skip_live_api)
