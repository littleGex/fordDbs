from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import List
from app.core.auth import (get_current_user, require_parent,
                           require_parent_or_service, is_parent,
                           authorize_child_access)
from app.database.database import get_db
from app.models.deductions_models import DeductionType
from app.models.user_models import Child, Transaction, Wish, User
from app.schema.deduction_schema import (DeductionItem,
                                         DeductionTypeUpdate,
                                         DeductionTypeCreate)


pocket_money_router = APIRouter()


@pocket_money_router.get("/balance/{child_name}")
def get_balance(child_name: str,
                db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)):
    child = db.query(Child).filter(Child.name == child_name).first()
    if not is_parent(current_user) and (
            child is None or child.user_id != current_user.id):
        raise HTTPException(status_code=403, detail="Forbidden")
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")
    return {"name": child.name, "balance": child.balance}


@pocket_money_router.patch("/adjust-balance/{child_id}")
def adjust_balance(child_id: int,
                   new_balance: float,
                   db: Session = Depends(get_db),
                   current_user: User = Depends(require_parent)):
    child = db.query(Child).filter(Child.id == child_id).first()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    new_balance_dec = Decimal(str(new_balance)).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP)
    current_balance = Decimal(str(child.balance)).quantize(Decimal("0.01"))

    if new_balance_dec < 0:
        raise HTTPException(status_code=422,
                            detail="Balance cannot be negative")

    adjustment_entry = Transaction(
        child_id=child.id,
        amount=new_balance_dec - current_balance,
        description="Manual Balance Adjustment",
        category="Correction"
    )

    child.balance = new_balance_dec
    db.add(adjustment_entry)
    db.commit()
    db.refresh(child)

    return {"message": "Balance updated",
            "new_balance": float(child.balance)}


@pocket_money_router.post("/add-child/{name}")
def add_child(name: str,
              birth_date: str = None,
              db: Session = Depends(get_db),
              current_user: User = Depends(require_parent)):
    parsed_date = None
    if birth_date:
        parsed_date = datetime.strptime(birth_date,
                                        "%Y-%m-%d").date()
    new_child = Child(name=name, balance=0.00, birth_date=parsed_date)
    db.add(new_child)
    db.commit()
    db.refresh(new_child)
    return new_child


@pocket_money_router.get("/children")
def get_all_children(db: Session = Depends(get_db),
                     current_user: User = Depends(get_current_user)):
    # Parents see everyone; a child only sees their own profile
    query = db.query(Child)
    if not is_parent(current_user):
        query = query.filter(Child.user_id == current_user.id)
    return query.all()


@pocket_money_router.get("/child-id/{name}")
def get_child_id_by_name(name: str,
                         db: Session = Depends(get_db),
                         caller=Depends(require_parent_or_service)):
    child = db.query(Child).filter(Child.name == name).first()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")
    return {"id": child.id, "name": child.name}


@pocket_money_router.patch("/child/{child_id}")
def update_child(child_id: int,
                 name: str,
                 birth_date: str = None,
                 db: Session = Depends(get_db),
                 current_user: User = Depends(require_parent)):
    child = db.query(Child).filter(Child.id == child_id).first()
    if not child:
        raise HTTPException(status_code=404,
                            detail="Child not found")

    child.name = name
    if birth_date:
        child.birth_date = birth_date

    db.commit()
    db.refresh(child)

    return child


@pocket_money_router.delete("/child/{child_id}")
def delete_child(child_id: int,
                 db: Session = Depends(get_db),
                 current_user: User = Depends(require_parent)):
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
    db: Session = Depends(get_db),
    current_user: User = Depends(require_parent)
):
    amount_dec = Decimal(str(amount)).quantize(Decimal("0.01"),
                                               rounding=ROUND_HALF_UP)

    # Logic: If amount is positive, use deposit logic.
    if amount_dec > 0:
        return _deposit(child_id=child_id,
                        amount=float(amount_dec),
                        description=description,
                        db=db)
    elif amount_dec < 0:
        return _withdraw(child_id=child_id,
                         amount=float(abs(amount_dec)),
                         description=description,
                         category=category, db=db)
    else:
        return {"message": "No adjustment made (amount was 0)"}


@pocket_money_router.post("/deposit/{child_id}")
def deposit_money(child_id: int,
                  amount: float,
                  description: str,
                  db: Session = Depends(get_db),
                  caller=Depends(require_parent_or_service)):
    return _deposit(child_id=child_id, amount=amount,
                    description=description, db=db)


def _deposit(child_id: int, amount: float, description: str, db: Session):
    # 1. Find the child
    child = db.query(Child).filter(Child.id == child_id).first()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    deposit_amount = Decimal(str(amount)).quantize(Decimal("0.01"),
                                                   rounding=ROUND_HALF_UP)
    current_balance = Decimal(str(child.balance)).quantize(Decimal("0.01"))

    if deposit_amount <= 0:
        raise HTTPException(status_code=422,
                            detail="Deposit amount must be positive")

    new_transaction = Transaction(
        child_id=child.id,
        amount=deposit_amount,
        description=description,
        category="Deposit"
    )

    # 3. Update the Child's balance
    child.balance = current_balance + deposit_amount

    # 4. Save everything together (Atomic transaction)
    db.add(new_transaction)
    db.commit()
    db.refresh(child)

    return {"message": "Deposit successful",
            "new_balance": float(child.balance)}


@pocket_money_router.get("/history/{child_id}")
def get_transaction_history(
        child_id: int,
        skip: int = 0,
        limit: int = 20,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    authorize_child_access(child_id, current_user, db)
    transactions = db.query(Transaction) \
        .filter(Transaction.child_id == child_id) \
        .order_by(Transaction.timestamp.desc()) \
        .offset(skip) \
        .limit(limit) \
        .all()

    return transactions


@pocket_money_router.post("/withdraw/{child_id}")
def withdraw_money(child_id: int,
                   amount: float,
                   description: str,
                   category: str = "Spend",
                   db: Session = Depends(get_db),
                   current_user: User = Depends(require_parent)):
    return _withdraw(child_id=child_id, amount=amount,
                     description=description, category=category, db=db)


def _withdraw(child_id: int, amount: float, description: str,
              category: str, db: Session):
    child = db.query(Child).filter(Child.id == child_id).first()

    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    withdraw_amount = Decimal(str(amount)).quantize(Decimal("0.01"),
                                                    rounding=ROUND_HALF_UP)
    current_balance = Decimal(str(child.balance)).quantize(Decimal("0.01"))

    # Check if sufficient money available
    if current_balance < withdraw_amount:
        raise HTTPException(
            status_code=422,
            detail=f"Insufficient funds. {child.name} only has"
                   f" {current_balance} available.")
    # Create negative transaction record
    new_transaction = Transaction(
        child_id=child.id,
        amount=-withdraw_amount,
        description=description,
        category=category
    )

    # Update balance of child
    child.balance = current_balance - withdraw_amount
    db.add(new_transaction)
    db.commit()
    db.refresh(child)

    return {
        "status": "success",
        "child_name": child.name,
        "withdrawn": float(withdraw_amount),
        "new_balance": float(child.balance),
        "transaction_id": new_transaction.id
    }


@pocket_money_router.get("/wishes/{child_id}")
def get_wishes(child_id: int,
               db: Session = Depends(get_db),
               current_user: User = Depends(get_current_user)):
    authorize_child_access(child_id, current_user, db)
    return db.query(Wish).filter(Wish.child_id == child_id).all()


@pocket_money_router.post("/wish/{child_id}")
def add_wish(child_id: int,
             item_name: str,
             cost: float,
             db: Session = Depends(get_db),
             current_user: User = Depends(get_current_user)):
    authorize_child_access(child_id, current_user, db)
    cost_dec = Decimal(str(cost)).quantize(Decimal("0.01"),
                                           rounding=ROUND_HALF_UP)

    if cost_dec < 0:
        raise HTTPException(status_code=422,
                            detail="Cost cannot be negative")

    new_wish = Wish(child_id=child_id,
                    item_name=item_name,
                    cost=cost_dec)
    db.add(new_wish)
    db.commit()
    db.refresh(new_wish)

    return new_wish


@pocket_money_router.get("/stats/{child_id}")
def get_combined_stats(child_id: int,
                       db: Session = Depends(get_db),
                       current_user: User = Depends(get_current_user)):
    authorize_child_access(child_id, current_user, db)
    category_query = db.query(
        Transaction.category,
        func.sum(Transaction.amount).label("total")
    ).filter(Transaction.child_id == child_id) \
        .group_by(Transaction.category).all()

    spending_by_category = {category: float(total) for category, total in
                            category_query}

    wishes_bought = db.query(Transaction).filter(
        Transaction.child_id == child_id,
        Transaction.category == "Goal Met"
    ).count()

    return {
        "wishes_bought": wishes_bought,
        "spending_summary": spending_by_category,
        "total_spent": sum(v for v in spending_by_category.values() if v < 0)
    }


@pocket_money_router.delete("/wish/{wish_id}")
def delete_wish(wish_id: int,
                db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)):
    # 1. Query for the wish first
    wish = db.query(Wish).filter(Wish.id == wish_id).first()

    # 2. Safety check: If the wish doesn't exist, return a 404 error
    # instead of letting the database operation fail with a 500 error.
    if not wish:
        raise HTTPException(
            status_code=404,
            detail=f"Wish with ID {wish_id} not found."
        )

    authorize_child_access(wish.child_id, current_user, db)

    # 3. Proceed with deletion only if found
    db.delete(wish)
    db.commit()

    return {"detail": "Wish deleted successfully"}


@pocket_money_router.patch("/wish/{wish_id}")
def update_wish(wish_id: int,
                item_name: str = None,
                cost: float = None,
                db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)):
    wish = db.query(Wish).filter(Wish.id == wish_id).first()

    if not wish:
        raise HTTPException(status_code=404, detail="Wish not found")

    authorize_child_access(wish.child_id, current_user, db)

    if item_name is not None:
        wish.item_name = item_name
    if cost is not None:
        cost_dec = Decimal(str(cost)).quantize(Decimal("0.01"),
                                               rounding=ROUND_HALF_UP)
        if cost_dec < 0:
            raise HTTPException(status_code=422,
                                detail="Cost cannot be negative")

        wish.cost = cost_dec

    db.commit()
    db.refresh(wish)
    return wish


@pocket_money_router.get("/deductions")
def get_deduction_types(db: Session = Depends(get_db),
                        current_user: User = Depends(require_parent)):
    """
    Fetches catalog of available deductions for UI.
    """
    return db.query(DeductionType).all()


@pocket_money_router.post("/deduct-batch/{child_id}")
def deduct_batch(child_id: int,
                 items: List[DeductionItem],
                 db: Session = Depends(get_db),
                 current_user: User = Depends(require_parent)):
    """
    Allows batch deduction operations for the selected child.

    :param child_id: The child id
    :param items: A list of items to be deducted.
    :param db: Session
    :param current_user: The logged-in parent.
    """
    summary = ", ".join([f"{i.name} x {i.count}" for i in items])
    total_fine = sum(
        (Decimal(str(i.total)).quantize(Decimal("0.01"),
                                        rounding=ROUND_HALF_UP)
         for i in items),
        start=Decimal("0.00")
    )

    return _withdraw(
        child_id=child_id,
        amount=float(total_fine),
        description=f"Deductions: {summary}",
        category="Behaviour Deductions",
        db=db
    )


@pocket_money_router.post("/deductions")
def create_deduction_type(
        item: DeductionTypeCreate,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_parent)
):
    """Creates a new deduction type for the catalog."""
    # Check if one with the same name already exists
    existing = db.query(DeductionType).filter(
        DeductionType.name == item.name).first()
    if existing:
        raise HTTPException(status_code=400,
                            detail="Deduction type already exists")

    new_deduction = DeductionType(name=item.name,
                                  default_amount=item.default_amount)
    db.add(new_deduction)
    db.commit()
    db.refresh(new_deduction)
    return new_deduction


@pocket_money_router.patch("/deductions/{deduction_id}")
def update_deduction_type(
        deduction_id: int,
        item: DeductionTypeUpdate,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_parent)
):
    """Updates an existing deduction type's name or price."""
    deduction = db.query(DeductionType).filter(
        DeductionType.id == deduction_id).first()
    if not deduction:
        raise HTTPException(status_code=404, detail="Deduction type not found")

    if item.name is not None:
        deduction.name = item.name
    if item.default_amount is not None:
        deduction.default_amount = item.default_amount

    db.commit()
    db.refresh(deduction)
    return deduction


@pocket_money_router.delete("/deductions/{deduction_id}")
def delete_deduction_type(
        deduction_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_parent)
):
    """Removes an item from the deduction catalog."""
    deduction = db.query(DeductionType).filter(
        DeductionType.id == deduction_id).first()
    if not deduction:
        raise HTTPException(status_code=404,
                            detail="Deduction type not found")

    db.delete(deduction)
    db.commit()
    return {"detail": f"Deduction '{deduction.name}' deleted successfully"}
