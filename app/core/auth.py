import hmac
import os
from dotenv import load_dotenv
from fastapi import Depends, Header, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from app.database.database import get_db
from app.models.user_models import Child, User


load_dotenv()

# Load from your .env. There is deliberately no fallback: a default
# signing key would let anyone forge a login token.
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY is not set; refusing to start")
ALGORITHM = "HS256"
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login", auto_error=False)

# Each role includes the abilities of the ones after it
ADMIN_ROLE = "admin"
ALL_ROLES = ("admin", "parent", "adult", "child")
# Roles allowed to manage every child's money
PARENT_ROLES = {"parent", "admin"}
# What the admin may hand out from the UI; admins are made on the server
ASSIGNABLE_ROLES = ("child", "adult", "parent")
# What a self-registration can end up as
SELF_SERVICE_ROLES = ("child", "adult")

STATUS_ACTIVE = "active"
STATUS_PENDING = "pending"


# Utilities
def hash_pw(pw):
    return pwd_context.hash(pw)


def verify_pw(pw, hashed):
    return pwd_context.verify(pw, hashed)


def _user_from_token(token: str, db: Session, verify_exp: bool = True):
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token,
                             SECRET_KEY,
                             algorithms=[ALGORITHM],
                             options={"verify_exp": verify_exp})
        user_id: str = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401,
                            detail="Could not validate credentials")

    user = db.query(User).filter(User.id == int(user_id)).first()

    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    if user.status != STATUS_ACTIVE:
        raise HTTPException(status_code=401, detail="Account is not active")

    return user


# JWT Dependency to protect routes
def get_current_user(token: str = Depends(oauth2_scheme),
                     db: Session = Depends(get_db)):
    return _user_from_token(token, db)


def get_current_user_for_refresh(
        token: str = Depends(oauth2_scheme),
        db: Session = Depends(get_db)):
    # This ignores expiration ONLY to identify who needs a new token
    return _user_from_token(token, db, verify_exp=False)


def is_parent(user: User) -> bool:
    return user.role in PARENT_ROLES


def require_admin(current_user: User = Depends(get_current_user)):
    if current_user.role != ADMIN_ROLE:
        raise HTTPException(status_code=403, detail="Admin only")
    return current_user


def require_parent(current_user: User = Depends(get_current_user)):
    if not is_parent(current_user):
        raise HTTPException(status_code=403, detail="Parents only")
    return current_user


def require_parent_or_service(
        token: str = Depends(oauth2_scheme),
        x_service_key: str = Header(None),
        db: Session = Depends(get_db)):
    """
    Allows a logged-in parent, or another backend (e.g. the chore
    tracker) presenting POCKET_MONEY_SERVICE_KEY in the X-Service-Key
    header. Returns the User, or None for a service call.
    """
    if x_service_key is not None:
        expected = os.getenv("POCKET_MONEY_SERVICE_KEY")
        if expected and hmac.compare_digest(x_service_key.encode(),
                                            expected.encode()):
            return None
        raise HTTPException(status_code=401, detail="Invalid service key")

    user = _user_from_token(token, db)
    if not is_parent(user):
        raise HTTPException(status_code=403, detail="Parents only")
    return user


def authorize_child_access(child_id: int, user: User, db: Session):
    """Parents may access any child; a child only their own profile."""
    if is_parent(user):
        return
    child = db.query(Child).filter(Child.id == child_id).first()
    if child is None or child.user_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
