from sqlalchemy import (Column, Integer, String, Float,
                        DateTime, ForeignKey, Date)
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database.database import Base


class Child(Base):
    __tablename__ = "children"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True)
    balance = Column(Float, default=0.0)
    birth_date = Column(Date, nullable=True)
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
