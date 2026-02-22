from sqlalchemy import (Column, Integer, String, Float,
                        DateTime, ForeignKey, Date)
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.database.database import Base


class Child(Base):
    __tablename__ = "children"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True)
    balance = Column(Float, default=0.0)
    birth_date = Column(Date, nullable=True)

    # --- ADD THESE TWO LINES ---
    # This matches the database column we added manually
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    user = relationship("User", back_populates="child_profile")
    # ---------------------------

    transactions = relationship(
        "Transaction",
        back_populates="child")
    wishes = relationship(
        "Wish",
        back_populates="child",
        cascade="all, delete-orphan"
    )


class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True)
    child_id = Column(Integer, ForeignKey("children.id"))
    amount = Column(Float)
    description = Column(String)
    category = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow)
    child = relationship(
        "Child", back_populates="transactions")


class Wish(Base):
    __tablename__ = "wishes"

    id = Column(Integer, primary_key=True, index=True)
    child_id = Column(Integer, ForeignKey("children.id"))
    item_name = Column(String)
    cost = Column(Float)

    child = relationship("Child", back_populates="wishes")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    role = Column(String, default="parent")

    profile_photo_key = Column(String, nullable=True)
    bio = Column(String(160), nullable=True)
    display_name = Column(String, nullable=True)

    created_at = Column(DateTime,
                        default=lambda: datetime.now(timezone.utc))

    # Relationships
    child_profile = relationship("Child",
                                 back_populates="user",
                                 uselist=False)

    # Note: Ensure "Photo" is imported or defined in your photo_model
    photos = relationship("Photo",
                          back_populates="uploader")
