from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database.database import Base


class Child(Base):
    __tablename__ = "children"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True)
    balance = Column(Float, default=0.0)
    transactions = relationship(
        "Transaction", back_populates="child")


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
