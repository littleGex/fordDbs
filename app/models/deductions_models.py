from sqlalchemy import Column, Integer, String, Numeric
from app.database.database import Base


class DeductionType(Base):
    """
    The 'Catalog' of possible deductions.
    This allows the UI to fetch a list of items to show on the checklist.
    """
    __tablename__ = "deduction_types"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)  # e.g., "Unmade Bed"
    default_amount = Column(Numeric(10, 2), nullable=False)      # e.g., 0.50
