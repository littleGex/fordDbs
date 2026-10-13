from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.auth import require_user_or_game_token
from app.database.database import get_db
from app.models.user_models import Child, User

game_router = APIRouter()

# The Ford House game's four players
CHILD_GAME_KEYS = ("girl", "boy")
PARENT_GAME_KEYS = ("mum", "dad")


@game_router.get("/family")
def get_family(db: Session = Depends(get_db),
               caller=Depends(require_user_or_game_token)):
    """
    Birthdays for the Ford House game. Deliberately returns nothing but
    the game's own nicknames and a date: no names, ids or balances.
    Players without a game_key or a birthday are left out.
    """
    children = db.query(Child).filter(
        Child.game_key.isnot(None), Child.birth_date.isnot(None)) \
        .order_by(Child.id).all()
    parents = db.query(User).filter(
        User.game_key.isnot(None), User.birth_date.isnot(None)) \
        .order_by(User.id).all()

    return {"players": [
        {"key": person.game_key, "birthday": person.birth_date.isoformat()}
        for person in [*children, *parents]
    ]}
