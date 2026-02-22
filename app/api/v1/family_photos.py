from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database.database import get_db
from app.core.storage import (upload_image_to_storage, get_image_url,
                              minio_client, BUCKET_NAME)
from app.models.photo_model import Photo, Like, Comment, View
from app.models.user_models import User
from minio.error import S3Error
import uuid
import logging


logger = logging.getLogger("app.api.users")
family_photos_router = APIRouter()


@family_photos_router.post("/upload")
async def upload_photo(
        caption: str,
        uploader_id: int,
        file: UploadFile = File(...),
        db: Session = Depends(get_db)
):
    # 1. Generate unique filename for MinIO
    file_ext = file.filename.split(".")[-1]
    unique_name = f"{uuid.uuid4()}.{file_ext}"

    # 2. Upload to MinIO via our storage helper
    file_content = await file.read()
    upload_image_to_storage(unique_name,
                            file_content,
                            len(file_content),
                            file.content_type)

    # 3. Save Record to Postgres
    new_photo = Photo(minio_key=unique_name,
                      caption=caption,
                      uploader_id=uploader_id)
    db.add(new_photo)
    db.commit()
    db.refresh(new_photo)
    return new_photo


@family_photos_router.get("/feed")
def get_feed(limit: int = 10,
             offset: int = 0,
             db: Session = Depends(get_db)):
    # Query with limit/offset for scrolling
    photos = db.query(Photo).order_by(
        Photo.timestamp.desc()).limit(limit).offset(offset).all()

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
            # Just return the last 3 comments for the "preview"
            "recent_comments": [
                {"username": c.user.username, "text": c.text}
                for c in p.comments[-3:]
            ]
        })
    return feed_data


@family_photos_router.post("/{photo_id}/like")
def like_photo(photo_id: int,
               user_id: int,
               db: Session = Depends(get_db)):
    # Check if already liked to prevent duplicates
    existing = db.query(Like).filter_by(photo_id=photo_id,
                                        user_id=user_id).first()
    if existing:
        db.delete(existing)
        db.commit()
        return {"message": "Unliked"}

    new_like = Like(photo_id=photo_id, user_id=user_id)
    db.add(new_like)
    db.commit()
    return {"message": "Liked"}


@family_photos_router.delete("/{photo_id}")
def delete_photo(photo_id: int,
                 user_id: int,
                 db: Session = Depends(get_db)):
    photo = db.query(Photo).filter(Photo.id == photo_id).first()

    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")

    # Simple Permission Check: Only the uploader or a 'parent' can delete
    requesting_user = db.query(User).filter(User.id == user_id).first()
    if photo.uploader_id != user_id and requesting_user.role != "parent":
        raise HTTPException(status_code=403,
                            detail="Not authorized to delete this photo")

    try:
        # 1. Remove from MinIO
        minio_client.remove_object(BUCKET_NAME, photo.minio_key)

        # 2. Remove from Postgres (Cascade will handle Likes/Comments/Views)
        db.delete(photo)
        db.commit()
        return {"status": "success", "message": "Photo and file deleted"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500,
                            detail=f"Cleanup failed: {str(e)}")


@family_photos_router.post("/{photo_id}/comment")
def add_comment(photo_id: int,
                user_id: int,
                text: str,
                db: Session = Depends(get_db)):
    # Verify the photo exists
    photo = db.query(Photo).filter(Photo.id == photo_id).first()
    if not photo:
        raise HTTPException(status_code=404,
                            detail="Photo not found")

    new_comment = Comment(
        photo_id=photo_id,
        user_id=user_id,
        text=text
    )
    db.add(new_comment)
    db.commit()
    db.refresh(new_comment)
    return {"message": "Comment added",
            "comment": new_comment.text}


@family_photos_router.post("/{photo_id}/view")
def record_view(photo_id: int,
                user_id: int,
                db: Session = Depends(get_db)):
    # Check if this user has already viewed this photo to avoid
    # duplicate counts
    existing_view = db.query(View).filter_by(photo_id=photo_id,
                                             user_id=user_id).first()

    if not existing_view:
        new_view = View(photo_id=photo_id, user_id=user_id)
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
        user_id: int,
        display_name: str = None,
        bio: str = None,
        file: UploadFile = File(None),
        db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

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
        new_photo_key = f"profiles/{user_id}_{uuid.uuid4().hex[:6]}.{file_ext}"

        try:
            file_content = await file.read()
            upload_image_to_storage(
                new_photo_key,
                file_content,
                len(file_content),
                file.content_type
            )
            user.profile_photo_key = new_photo_key
        except Exception as e:
            logger.error("Failed to upload new profile photo for user "
                         f"{user_id}: {e}")
            raise HTTPException(status_code=500,
                                detail="Storage upload failed")

    try:
        # 4. Commit DB changes first (The point of no return)
        db.commit()
        db.refresh(user)
    except Exception as e:
        db.rollback()
        logger.error(f"Database commit failed for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Database update failed")

    # 5. Cleanup OLD photo only AFTER successful DB commit
    if file and old_photo_key:
        try:
            minio_client.remove_object(BUCKET_NAME, old_photo_key)
        except S3Error as e:
            # We don't raise an exception here because the user's
            # new profile is already active and saved.
            if e.code == "NoSuchKey":
                logger.warning(f"Old photo {old_photo_key}"
                               f" already gone from MinIO.")
            else:
                logger.error(
                    f"Non-critical cleanup failure for {old_photo_key}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error during old photo cleanup: {e}")

    return {
        "status": "Profile updated",
        "profile_photo_url": get_image_url(
            user.profile_photo_key) if user.profile_photo_key else None
    }
