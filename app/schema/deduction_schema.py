from pydantic import BaseModel
from typing import Optional


class DeductionItem(BaseModel):
    name: str
    count: int
    total: float


class DeductionTypeCreate(BaseModel):
    name: str
    default_amount: float


class DeductionTypeUpdate(BaseModel):
    name: Optional[str] = None
    default_amount: Optional[float] = None
