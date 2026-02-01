# app/core/scheduler.py
from datetime import date
from sqlalchemy.orm import Session
from app.database.database import SessionLocal
from app.models.user_models import Child, Transaction


def calculate_age(birth_date: date,
                  reference_date: date = None) -> int:
    """
    Calculates age.
    reference_date is used for testing, else defaults to today.
    """
    if not birth_date:
        return 0

    # Use the provided reference (for tests) or the real 'today'
    target = reference_date or date.today()

    return target.year - birth_date.year - (
            (target.month, target.day) < (birth_date.month, birth_date.day))


def run_weekly_payout():
    """Scheduled task: Runs every Friday @ 07:30"""
    db: Session = SessionLocal()
    try:
        children = db.query(Child).all()
        for child in children:
            if not child.birth_date:
                continue

            # This call is now safe because reference_date defaults to None
            age = calculate_age(child.birth_date)
            payout_amount = age * 0.5

            if payout_amount > 0:
                child.balance += payout_amount
                new_trans = Transaction(
                    child_id=child.id,
                    amount=payout_amount,
                    description=f"Weekly Pocket Money (Age {age})",
                    category="Pocket Money"
                )
                db.add(new_trans)

        db.commit()
    finally:
        db.close()
