from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.database.database import get_db
from app.models.user_models import Child, Transaction


pocket_money_router = APIRouter()


@pocket_money_router.get("/balance/{child_name}")
def get_balance(child_name: str,
                db: Session = Depends(get_db)):
    child = db.query(Child).filter(Child.name == child_name).first()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")
    return {"name": child.name, "balance": child.balance}


@pocket_money_router.patch("/adjust-balance/{child_id}")
def adjust_balance(child_id: int,
                   new_balance: float,
                   db: Session = Depends(get_db)):
    child = db.query(Child).filter(Child.id == child_id).first()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    # Record why the manual adjustment happened
    adjustment_entry = Transaction(
        child_id=child.id,
        amount=new_balance - child.balance,
        description="Manual Balance Adjustment",
        category="Correction"
    )

    child.balance = new_balance
    db.add(adjustment_entry)
    db.commit()
    return {"message": "Balance updated", "new_balance": child.balance}


@pocket_money_router.post("/add-child/{name}")
def add_child(name: str, db: Session = Depends(get_db)):
    new_child = Child(name=name, balance=0.0)
    db.add(new_child)
    db.commit()
    db.refresh(new_child)
    return new_child


@pocket_money_router.get("/child-id/{name}")
def get_child_id_by_name(name: str, db: Session = Depends(get_db)):
    child = db.query(Child).filter(Child.name == name).first()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")
    return {"id": child.id, "name": child.name}


@pocket_money_router.post("/deposit/{child_id}")
def deposit_money(child_id: int,
                  amount: float,
                  description: str,
                  db: Session = Depends(get_db)):
    # 1. Find the child
    child = db.query(Child).filter(Child.id == child_id).first()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    # 2. Create the Transaction record (Now Transaction is USED!)
    new_transaction = Transaction(
        child_id=child.id,
        amount=amount,
        description=description,
        category="Deposit"
    )

    # 3. Update the Child's balance
    child.balance += amount

    # 4. Save everything together (Atomic transaction)
    db.add(new_transaction)
    db.commit()
    db.refresh(child)

    return {"message": "Deposit successful", "new_balance": child.balance}


@pocket_money_router.get("/history/{child_id}")
def get_transaction_history(
        child_id: int,
        skip: int = 0,
        limit: int = 20,
        db: Session = Depends(get_db)
):
    transactions = db.query(Transaction) \
        .filter(Transaction.child_id == child_id) \
        .order_by(Transaction.timestamp.desc()) \
        .offset(skip) \
        .limit(limit) \
        .all()

    return transactions


@pocket_money_router.get("/stats/{child_id}")
def get_spending_stats(child_id: int, db: Session = Depends(get_db)):
    # Sum up amounts grouped by category
    stats = db.query(
        Transaction.category,
        func.sum(Transaction.amount).label("total")
    ).filter(Transaction.child_id == child_id)\
     .group_by(Transaction.category).all()

    # Convert to a dictionary: {"Chore": 50.0, "Spend": -10.0}
    return {category: total for category, total in stats}
