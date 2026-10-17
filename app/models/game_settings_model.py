from sqlalchemy import Column, Integer, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from app.database.database import Base


class GameSettings(Base):
    """The Ford House game's settings: players' names and looks, and the
    job groups switched off. One family, so one row (id 1)."""
    __tablename__ = "game_settings"

    id = Column(Integer, primary_key=True)
    data = Column(JSONB, nullable=False)
    # +1 on every save, so a device saving over a newer copy is refused
    version = Column(Integer, nullable=False, default=0,
                     server_default="0")
    updated_at = Column(DateTime(timezone=True), nullable=False)
