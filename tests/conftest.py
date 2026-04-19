import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database.database import Base


@pytest.fixture(scope="session")
def admin_password():
    """Provides the secret password for admin-protected endpoints."""
    # This ensures the test matches the environment variable the app expects
    return os.getenv("ADMIN_PASSWORD", "testpassword")


@pytest.fixture(scope="function")
def db_session():
    # Use an in-memory SQLite database for testing
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(bind=engine)

    session = TestingSessionLocal()
    yield session
    session.close()
