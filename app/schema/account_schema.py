from pydantic import BaseModel
from typing import Optional


class ApproveAccount(BaseModel):
    role: Optional[str] = None


class RoleChange(BaseModel):
    role: str


class PasswordReset(BaseModel):
    password: str
