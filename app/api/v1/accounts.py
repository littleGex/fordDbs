import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.api.v1.family_photos import user_profile
from app.core.auth import (require_admin, hash_pw, ADMIN_ROLE,
                           ASSIGNABLE_ROLES, SELF_SERVICE_ROLES,
                           STATUS_ACTIVE, STATUS_PENDING)
from app.core.storage import minio_client, BUCKET_NAME
from app.database.database import get_db
from app.models.user_models import User
from app.schema.account_schema import (ApproveAccount, RoleChange,
                                       PasswordReset)

logger = logging.getLogger("app.api.accounts")
accounts_router = APIRouter()


def _get_user(user_id: int, db: Session) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def _get_pending(user_id: int, db: Session) -> User:
    user = _get_user(user_id, db)
    if user.status != STATUS_PENDING:
        raise HTTPException(status_code=400,
                            detail="Account is not waiting for approval")
    return user


@accounts_router.get("/admin/pending")
def list_pending_accounts(db: Session = Depends(get_db),
                          admin: User = Depends(require_admin)):
    """Self-registered accounts waiting for the admin's decision."""
    pending = db.query(User).filter(User.status == STATUS_PENDING) \
        .order_by(User.created_at).all()
    return [user_profile(user) for user in pending]


@accounts_router.post("/admin/users/{user_id}/approve")
def approve_account(user_id: int,
                    data: ApproveAccount = None,
                    db: Session = Depends(get_db),
                    admin: User = Depends(require_admin)):
    """
    Activates a pending account. The role suggested from the birth year
    can be corrected to child or adult here; making someone a parent is
    a separate step via the role route.
    """
    user = _get_pending(user_id, db)

    if data and data.role is not None:
        if data.role not in SELF_SERVICE_ROLES:
            raise HTTPException(status_code=422,
                                detail="Role must be child or adult")
        user.role = data.role

    user.status = STATUS_ACTIVE
    db.commit()
    db.refresh(user)
    return user_profile(user)


@accounts_router.post("/admin/users/{user_id}/reject")
def reject_account(user_id: int,
                   db: Session = Depends(get_db),
                   admin: User = Depends(require_admin)):
    """Deletes a pending account and its uploaded avatar."""
    user = _get_pending(user_id, db)
    avatar_key = user.profile_photo_key

    db.delete(user)
    db.commit()

    if avatar_key:
        try:
            minio_client.remove_object(BUCKET_NAME, avatar_key)
        except Exception as e:
            logger.error(f"Cleanup failure: {e}")

    return {"status": "rejected"}


@accounts_router.post("/admin/users/{user_id}/role")
def change_role(user_id: int,
                data: RoleChange,
                db: Session = Depends(get_db),
                admin: User = Depends(require_admin)):
    if data.role not in ASSIGNABLE_ROLES:
        raise HTTPException(status_code=422,
                            detail="Role must be child, adult or parent")

    user = _get_user(user_id, db)
    # Admins are only made or unmade from the server (app/cli.py), so
    # the last admin can't be demoted by a slip in the UI.
    if user.role == ADMIN_ROLE:
        raise HTTPException(status_code=403,
                            detail="An admin's role can't be changed here")

    user.role = data.role
    db.commit()
    db.refresh(user)
    return user_profile(user)


@accounts_router.post("/admin/users/{user_id}/reset-password")
def reset_password(user_id: int,
                   data: PasswordReset,
                   db: Session = Depends(get_db),
                   admin: User = Depends(require_admin)):
    if not data.password:
        raise HTTPException(status_code=422, detail="Password is required")

    user = _get_user(user_id, db)
    user.hashed_password = hash_pw(data.password)
    db.commit()
    return {"status": "reset successful"}
