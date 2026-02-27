from datetime import datetime
from fastapi import (APIRouter, UploadFile, File, Depends,
                     HTTPException, Form)
from sqlalchemy.orm import Session
from app.database.database import get_db
from app.core.storage import (upload_image_to_storage, get_image_url,
                              minio_client, BUCKET_NAME)
from app.models.photo_model import Photo, Like, Comment, View
from app.models.user_models import User
from minio.error import S3Error
import uuid
import logging
import os
from jose import jwt, JWTError
from passlib.context import CryptContext
from datetime import datetime, timedelta, timezone
from fastapi.security import OAuth2PasswordBearer

logger = logging.getLogger("app.api.users")
family_photos_router = APIRouter()

# Load from your .env
SECRET_KEY = os.getenv("SECRET_KEY", "your-default-secret")
ALGORITHM = "HS256"
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login", auto_error=False)


# Utilities
def hash_pw(pw):
    return pwd_context.hash(pw)


def verify_pw(pw, hashed):
    return pwd_context.verify(pw, hashed)


# JWT Dependency to protect routes
async def get_current_user(token: str = Depends(oauth2_scheme),
                           db: Session = Depends(get_db)):
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if not user_id: raise HTTPException(status_code=401)
    except JWTError:
        raise HTTPException(status_code=401)

    user = db.query(User).filter(User.id == int(user_id)).first()
    return user


@family_photos_router.post("/login")
def login(data: dict, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == data.get('user_id')).first()
    if not user: raise HTTPException(status_code=404)

    # 1. Check if user needs to set a password (Null check)
    if user.hashed_password is None:
        return {"status": "needs_initial_password"}

    # 2. Verify password
    if not verify_pw(data.get('password'), user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid password")

    # 3. Create Token
    token = jwt.encode({"sub": str(user.id), "exp": datetime.now(timezone.utc) + timedelta(hours=24)}, SECRET_KEY,
                       algorithm=ALGORITHM)
    return {"access_token": token, "token_type": "bearer", "user": {"id": user.id, "role": user.role}}


@family_photos_router.post("/users/set-password")
def set_password(data: dict, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == data.get('user_id')).first()
    if user and user.hashed_password is None:
        user.hashed_password = hash_pw(data.get('password'))
        db.commit()
        return {"status": "success"}
    raise HTTPException(status_code=400, detail="Password already set or user not found")


@family_photos_router.post("/upload")
async def upload_photo(
        caption: str = Form(None),
        file: UploadFile = File(...),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    file_ext = file.filename.split(".")[-1]
    minio_key = f"{uuid.uuid4()}.{file_ext}"

    minio_client.put_object(
        "family-photos",
        minio_key,
        file.file,
        length=-1,
        part_size=10 * 1024 * 1024
    )

    new_photo = Photo(
        minio_key=minio_key,
        caption=caption,
        uploader_id=current_user.id,  # TRUST THE TOKEN, NOT THE FORM
        timestamp=datetime.now(timezone.utc)
    )
    db.add(new_photo)
    db.commit()

    return {"message": "Success"}


@family_photos_router.get("/feed")
def get_feed(
        user_id: int = None,
        limit: int = 10,
        offset: int = 0,
        db: Session = Depends(get_db)):
    # 1. Start with the base query
    query = db.query(Photo)

    # 2. If a user_id is provided, filter the photos by that uploader
    if user_id:
        query = query.filter(Photo.uploader_id == user_id)

    # 3. Apply ordering and pagination
    photos = query.order_by(Photo.timestamp.desc()).limit(limit).offset(offset).all()

    feed_data = []
    for p in photos:
        feed_data.append({
            "id": p.id,
            "url": get_image_url(p.minio_key),
            "caption": p.caption,
            "timestamp": p.timestamp,
            "uploader": {
                "id": p.uploader.id,
                "username": p.uploader.username,
                "display_name": p.uploader.display_name or p.uploader.username,
                "profile_photo_url": get_image_url(
                    p.uploader.profile_photo_key) if
                p.uploader.profile_photo_key else None
            },
            "stats": {
                "likes": len(p.likes),
                "comments": len(p.comments),
                "views": len(p.views)
            },
            "recent_comments": [
                {"username": c.user.username, "text": c.text}
                for c in p.comments[-3:]
            ]
        })
    return feed_data


@family_photos_router.post("/{photo_id}/like")
def like_photo(
        photo_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    # Toggle logic using current_user.id
    like = db.query(Like).filter_by(photo_id=photo_id,
                                    user_id=current_user.id).first()
    if like:
        db.delete(like)
    else:
        db.add(Like(photo_id=photo_id, user_id=current_user.id))
    db.commit()
    return {"status": "updated"}


@family_photos_router.delete("/{photo_id}")
def delete_photo(
    photo_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user) # Secure identity from JWT
):
    photo = db.query(Photo).filter(Photo.id == photo_id).first()

    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")

    # Permission Check: Only the uploader or a 'parent' can delete
    # We now trust current_user.id from the token
    if photo.uploader_id != current_user.id and current_user.role != "parent":
        raise HTTPException(
            status_code=403,
            detail="Not authorized to delete this photo"
        )

    try:
        # 1. Remove file from storage
        minio_client.remove_object(BUCKET_NAME, photo.minio_key)

        # 2. Remove from database
        db.delete(photo)
        db.commit()
        return {"status": "success", "message": "Photo and file deleted"}
    except Exception as e:
        db.rollback()
        logger.error(f"Delete failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Cleanup failed")


@family_photos_router.post("/{photo_id}/comment")
def add_comment(
        photo_id: int,
        text: str = Form(...),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    db.add(Comment(photo_id=photo_id,
                   user_id=current_user.id,
                   text=text))
    db.commit()
    return {"status": "added"}


@family_photos_router.post("/{photo_id}/view")
def record_view(
        photo_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user) # Added JWT dependency
):
    # Use current_user.id instead of a passed parameter
    existing_view = db.query(View).filter_by(
        photo_id=photo_id,
        user_id=current_user.id
    ).first()

    if not existing_view:
        new_view = View(photo_id=photo_id, user_id=current_user.id)
        db.add(new_view)
        db.commit()
        return {"status": "view_recorded"}

    return {"status": "already_viewed"}


@family_photos_router.get("/{photo_id}/stats")
def get_photo_stats(photo_id: int, db: Session = Depends(get_db)):
    photo = db.query(Photo).filter(Photo.id == photo_id).first()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")

    return {
        "viewed_by": [v.user.username for v in photo.views],
        "liked_by": [like.user.username for like in photo.likes],
        "comment_count": len(photo.comments)
    }


@family_photos_router.post("/profile/update")
async def update_profile(
        display_name: str = Form(None),
        bio: str = Form(None),
        file: UploadFile = File(None),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)  # Secure: Identity from token
):
    # Use the user object directly from the JWT payload
    user = current_user

    # 1. Store the old key for later cleanup
    old_photo_key = user.profile_photo_key
    new_photo_key = None

    # 2. Handle metadata updates
    if display_name:
        user.display_name = display_name
    if bio:
        user.bio = bio

    # 3. Process new photo if provided
    if file:
        file_ext = file.filename.split(".")[-1]
        new_photo_key = f"profiles/{user.id}_{uuid.uuid4().hex[:6]}.{file_ext}"

        try:
            upload_image_to_storage(
                new_photo_key,
                file.file,
                -1,
                file.content_type
            )
            user.profile_photo_key = new_photo_key
        except Exception as e:
            logger.error(f"Failed to upload profile photo for user {user.id}: {e}")
            raise HTTPException(status_code=500, detail="Storage upload failed")

    try:
        db.commit()
        db.refresh(user)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database update failed")

    # 4. Cleanup OLD photo
    if file and old_photo_key:
        try:
            minio_client.remove_object(BUCKET_NAME, old_photo_key)
        except Exception as e:
            logger.error(f"Cleanup failure: {e}")

    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "role": user.role,
        "bio": user.bio,
        "profile_photo_url": get_image_url(user.profile_photo_key) if user.profile_photo_key else None
    }


@family_photos_router.get("/users")
def get_all_users(db: Session = Depends(get_db)):
    users = db.query(User).all()
    user_list = []

    for user in users:
        user_list.append({
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name or user.username,
            "role": user.role,
            "profile_photo_url": get_image_url(
                user.profile_photo_key) if user.profile_photo_key else None,
            "bio": user.bio
        })

    return user_list


@family_photos_router.post("/users")
def create_user(data: dict, db: Session = Depends(get_db)):
    # Updated to include password
    new_user = User(
        username=data['username'],
        display_name=data['display_name'],
        hashed_password=hash_pw(data['password']),
        role="child"
    )
    db.add(new_user)
    db.commit()
    return {"status": "success"}


# Admin Reset Override
@family_photos_router.post("/admin/reset-password")
def admin_reset(target_id: int, new_pass: str, current_user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    if current_user.role != "parent":
        raise HTTPException(status_code=403, detail="Only parents can reset passwords")
    target = db.query(User).filter(User.id == target_id).first()
    target.hashed_password = hash_pw(new_pass)
    db.commit()
    return {"status": "reset successful"}


@family_photos_router.post("/refresh")
def refresh_token(
    current_user: User = Depends(get_current_user), # Validates current identity
    db: Session = Depends(get_db)
):
    # Generate a new token with a fresh expiration (e.g., another 24 hours)
    access_token_expires = timedelta(hours=24)

    new_token = jwt.encode(
        {"sub": str(current_user.id), "exp": datetime.now(timezone.utc) + access_token_expires},
        SECRET_KEY,
        algorithm=ALGORITHM
    )

    return {"access_token": new_token}
