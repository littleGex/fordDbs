from sqlalchemy import (Column, Integer, String,
                        Date, func, Float)
from app.database.database import Base


class Utils(Base):
    __tablename__ = "utils"
    id = Column(Integer, primary_key=True, index=True)
    reading_date = Column(Date,
                          default=func.now())
    utility_name = Column(String, nullable=False)
    reading_value = Column(Float, nullable=False)
