from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    # strict=True: bool is a subclass of int, so True would otherwise
    # mean user 1
    user_id: int = Field(strict=True)
    # Defaults to "" rather than being required: a missing password
    # should count as a wrong password (401), not a validation error
    password: str = ""
