import os
from datetime import datetime
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.database.database import get_db
from app.models.user_models import Child, Transaction, Wish


load_dotenv()
SECRET_PASSWORD = os.getenv("ADMIN_PASSWORD")
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
def add_child(name: str,
              password: str,
              birth_date: str = None,
              db: Session = Depends(get_db)):
    if password != SECRET_PASSWORD:
        raise HTTPException(status_code=403, detail="Forbidden")

    parsed_date = None
    if birth_date:
        parsed_date = datetime.strptime(birth_date,
                                        "%Y-%m-%d").date()
    new_child = Child(name=name, balance=0.0, birth_date=parsed_date)
    db.add(new_child)
    db.commit()
    db.refresh(new_child)
    return new_child


@pocket_money_router.get("/children")
def get_all_children(db: Session = Depends(get_db)):
    children = db.query(Child).all()
    return children


@pocket_money_router.get("/child-id/{name}")
def get_child_id_by_name(name: str, db: Session = Depends(get_db)):
    child = db.query(Child).filter(Child.name == name).first()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")
    return {"id": child.id, "name": child.name}


@pocket_money_router.patch("/child/{child_id}")
def update_child(child_id: int,
                 name: str,
                 password: str,
                 birth_date: str = None,
                 db: Session = Depends(get_db)):
    if password != SECRET_PASSWORD:
        raise HTTPException(status_code=403,
                            detail="Forbidden")

    child = db.query(Child).filter(Child.id == child_id).first()
    if not child:
        raise HTTPException(status_code=404,
                            detail="Child not found")

    child.name = name
    if birth_date:
        child.birth_date = birth_date

    db.commit()

    return child


@pocket_money_router.delete("/child/{child_id}")
def delete_child(child_id: int,
                 password: str,
                 db: Session = Depends(get_db)):
    if password != SECRET_PASSWORD:
        raise HTTPException(status_code=403, detail="Forbidden")
    child = db.query(Child).filter(Child.id == child_id).first()

    if not child:
        raise HTTPException(status_code=404, detail="Child not found")
    db.delete(child)
    db.commit()
    return {"detail": "Child and history deleted"}


@pocket_money_router.post("/adjust/{child_id}")
def adjust_money(
    child_id: int,
    amount: float,
    description: str,
    category: str,
    password: str,
    db: Session = Depends(get_db)
):
    # 1. Security Check
    if password != SECRET_PASSWORD:
        raise HTTPException(status_code=403, detail="Forbidden")

    # 2. Logic: If amount is positive, use deposit logic.
    # If negative, use withdrawal logic.
    if amount > 0:
        return deposit_money(child_id=child_id,
                             amount=amount,
                             description=description,
                             db=db)
    elif amount < 0:
        # We pass the absolute value to withdraw_money because that
        # function subtracts it
        return withdraw_money(child_id=child_id,
                              amount=abs(amount),
                              description=description,
                              category=category, db=db)
    else:
        return {"message": "No adjustment made (amount was 0)"}


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


@pocket_money_router.post("/withdraw/{child_id}")
def withdraw_money(child_id: int,
                   amount: float,
                   description: str,
                   category: str = "Spend",
                   db: Session = Depends(get_db)):
    child = db.query(Child).filter(Child.id == child_id).first()

    if not child:
        raise HTTPException(status_code=404, detail="Child not found")
    # Check if sufficient money available
    if child.balance < amount:
        raise HTTPException(
            status_code=404,
            detail=f"Insufficient funds. {child.name} only has"
                   f" {child.balance} available.")
    # Create negative transaction record
    new_transaction = Transaction(
        child_id=child.id,
        amount=-abs(amount),
        description=description,
        category=category
    )

    # Update balance of child
    child.balance -= abs(amount)
    db.add(new_transaction)
    db.commit()
    db.refresh(child)

    return {
        "status": "success",
        "child_name": child.name,
        "withdrawn": amount,
        "new_balance": child.balance,
        "transaction_id": new_transaction.id
    }


@pocket_money_router.get("/wishes/{child_id}")
def get_wishes(child_id: int, db: Session = Depends(get_db)):
    return db.query(Wish).filter(Wish.child_id == child_id).all()


@pocket_money_router.post("/wish/{child_id}")
def add_wish(child_id: int,
             item_name: str,
             cost: float,
             db: Session = Depends(get_db)):
    new_wish = Wish(child_id=child_id, item_name=item_name, cost=cost)
    db.add(new_wish)
    db.commit()

    return new_wish


@pocket_money_router.get("/stats/{child_id}")
def get_child_stats(child_id: int,
                    db: Session = Depends(get_db)):
    bought_count = db.query(Transaction).filter(
        Transaction.child_id == child_id,
        Transaction.category == "Goal Met"
    ).count()

    return {"wishes_bought": bought_count}


@pocket_money_router.delete("/wish/{wish_id}")
def delete_wish(wish_id: int,
                db: Session = Depends(get_db)):
    # 1. Query for the wish first
    wish = db.query(Wish).filter(Wish.id == wish_id).first()

    # 2. Safety check: If the wish doesn't exist, return a 404 error
    # instead of letting the database operation fail with a 500 error.
    if not wish:
        raise HTTPException(
            status_code=404,
            detail=f"Wish with ID {wish_id} not found."
        )

    # 3. Proceed with deletion only if found
    db.delete(wish)
    db.commit()

    return {"detail": "Wish deleted successfully"}


@pocket_money_router.patch("/wish/{wish_id}")
def update_wish(wish_id: int,
                item_name: str = None,
                cost: float = None,
                db: Session = Depends(get_db)):
    wish = db.query(Wish).filter(Wish.id == wish_id).first()

    if not wish:
        raise HTTPException(status_code=404, detail="Wish not found")

    if item_name is not None:
        wish.item_name = item_name
    if cost is not None:
        wish.cost = cost

    db.commit()
    db.refresh(wish)
    return wish


@pocket_money_router.post("/verify-admin")
def verify_admin(password: str = Query(...)):
    if password == os.getenv("ADMIN_PASSWORD"):
        return {"success": "authenticated"}
    raise HTTPException(status_code=401,
                        detail="Invalid admin password")
