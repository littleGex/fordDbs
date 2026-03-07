from fastapi import APIRouter, Depends, HTTPException
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
    parsed_date = datetime.strptime(util_date, "%Y-%m-%d").date()

    # Check if a record already exists for this date and utility
    existing_record = db.query(Utils).filter(
        Utils.reading_date == parsed_date,
        Utils.utility_name == utility
    ).first()

    if existing_record:
        # Update existing
        existing_record.reading_value = util_reading
        db.commit()
        db.refresh(existing_record)
        return {"status": "updated", "data": existing_record}

    # Create new
    new_util = Utils(reading_date=parsed_date,
                     utility_name=utility,
                     reading_value=util_reading)
    db.add(new_util)
    db.commit()
    db.refresh(new_util)

    return {"status": "created", "data": new_util}


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


@utils_router.put("/update-reading")
def update_reading(
        util_date: str,
        utility: str,
        value: float,
        db: Session = Depends(get_db)):
    # Find the specific record
    record = db.query(Utils).filter(
        Utils.reading_date == util_date,
        Utils.utility_name == utility
    ).first()

    if not record:
        raise HTTPException(status_code=404,
                            detail="Reading not found")

    record.reading_value = value
    db.commit()

    return {"status": "success"}
