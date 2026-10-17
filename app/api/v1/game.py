import re
import unicodedata
from datetime import datetime, timezone
from typing import Annotated, List, Literal, Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import (BaseModel, ConfigDict, Field, StrictBool, StrictInt,
                      StrictStr, StringConstraints, field_validator)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.core.auth import require_user_or_game_token
from app.core.rate_limit import (client_address,
                                 game_settings_saves_per_client,
                                 refuse_if_blocked)
from app.database.database import get_db
from app.models.game_settings_model import GameSettings
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


# --- Game settings: names, looks and job switches, shared by every device.
# The rules mirror the game's own checks (house/js/settings.js and
# names.js in ford_games), so anything the game saves is accepted and
# anything else is refused rather than quietly cleaned.

SETTINGS_ID = 1
MAX_SETTINGS_BYTES = 8 * 1024

HAIR_STYLES = Literal["long", "shoulder", "ponytail", "bun", "swept",
                      "short", "spiky", "beanie", "bald"]
JOB_GROUPS = Literal["dragon", "keyboard", "clarinet", "bike", "solar",
                     "car", "shave", "loft", "halloween", "christmas",
                     "birthdays"]
Colour = Annotated[StrictStr, StringConstraints(
    pattern=r"^#[0-9a-fA-F]{6}$", to_lower=True)]
# Letters (any language), numbers, spaces and - ' . ; \w also allows _
NAME = re.compile(r"[\w .'-]{1,16}")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Look(Strict):
    # Each may be left out (the game fills in its default), but not null
    skin: Colour = None
    hair: HAIR_STYLES = None
    hairColor: Colour = None
    top: Union[Literal["own"], Colour] = None
    pants: Colour = None
    shoes: Colour = None
    glasses: StrictBool = None
    beard: StrictBool = None


class Player(Strict):
    # None: the usual nickname (Dad, Mum, P, Dude)
    name: Optional[StrictStr] = None
    look: Optional[Look] = None

    @field_validator("name")
    @classmethod
    def plain_name(cls, name):
        if name is None:
            return None
        name = unicodedata.normalize("NFC", name).strip()
        if "_" in name or not NAME.fullmatch(name):
            raise ValueError("a name is at most 16 letters, numbers, "
                             "spaces and - ' .")
        return name


class Players(Strict):
    dad: Optional[Player] = None
    mum: Optional[Player] = None
    girl: Optional[Player] = None
    boy: Optional[Player] = None


class Settings(Strict):
    players: Players
    off: List[JOB_GROUPS] = Field(default_factory=list)

    @field_validator("off")
    @classmethod
    def no_repeats(cls, off):
        if len(set(off)) != len(off):
            raise ValueError("each job group at most once")
        return off


class SettingsSave(Strict):
    base_version: StrictInt = Field(ge=0)
    settings: Settings


def limit_settings_saves(request: Request):
    key = client_address(request)
    refuse_if_blocked(game_settings_saves_per_client, key, "settings saves")
    game_settings_saves_per_client.record(key)


async def limit_settings_size(request: Request):
    if len(await request.body()) > MAX_SETTINGS_BYTES:
        raise HTTPException(status_code=413,
                            detail="Game settings are too large")


def settings_document(row: Optional[GameSettings]):
    if row is None:
        return {"version": 0, "updated_at": None, "settings": None}
    return {"version": row.version,
            "updated_at": row.updated_at.isoformat(),
            "settings": row.data}


@game_router.get("/settings")
def get_settings(db: Session = Depends(get_db),
                 caller=Depends(require_user_or_game_token)):
    """The family's game settings; version 0 and no settings until the
    first save."""
    return settings_document(db.get(GameSettings, SETTINGS_ID))


@game_router.put("/settings",
                 dependencies=[Depends(limit_settings_saves),
                               Depends(limit_settings_size)])
def save_settings(body: SettingsSave, db: Session = Depends(get_db),
                  caller=Depends(require_user_or_game_token)):
    """
    Saves the game settings if base_version is the version stored now.
    Otherwise another device saved in between: 409 with the current
    settings, so the game can re-apply its change and try again.
    """
    row = db.query(GameSettings).filter(GameSettings.id == SETTINGS_ID) \
        .with_for_update().first()
    current = row.version if row else 0
    if body.base_version != current:
        return settings_conflict(row)

    if row is None:
        row = GameSettings(id=SETTINGS_ID)
        db.add(row)
    row.data = body.settings.model_dump(exclude_unset=True)
    row.version = current + 1
    row.updated_at = datetime.now(timezone.utc)
    try:
        db.commit()
    except IntegrityError:
        # Two devices made the very first save at the same moment
        db.rollback()
        return settings_conflict(db.get(GameSettings, SETTINGS_ID))
    db.refresh(row)
    return settings_document(row)


def settings_conflict(row):
    return JSONResponse(status_code=409, content={
        "detail": "The settings were changed on another device",
        **settings_document(row)})
