from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database.database import get_db
from app.core.utils_core import prepare_dashboard_data
from app.models.utilities import Utils
from datetime import datetime


utils_router = APIRouter()


@utils_router.post("/add-util")
def add_util(util_date: str,
             utility: str,
             util_reading: float,
             db: Session = Depends(get_db)):
    parsed_date = None

    if util_date:
        parsed_date = datetime.strptime(util_date,
                                        "%Y-%m-%d").date()
    new_util = Utils(reading_date=parsed_date,
                     utility_name=utility,
                     reading_value=util_reading)

    db.add(new_util)
    db.commit()
    db.refresh(new_util)

    return new_util


@utils_router.get("/dashboard")
def data_for_dashboard(
        db: Session = Depends(get_db)):
    raw_readings = db.query(Utils).all()

    if not raw_readings:
        return {
            "latest": {"readings": {}, "usage": {}},
            "history": []
        }

    dashboard_data = prepare_dashboard_data(raw_readings)

    return dashboard_data
