from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database.database import get_db
from app.core.storage import upload_image_to_storage, get_image_url
from app.models.photo_model import Photo, Like, Comment, View
import uuid


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
def get_feed(db: Session = Depends(get_db)):
    photos = db.query(Photo).order_by(Photo.timestamp.desc()).all()

    feed = []
    for p in photos:
        feed.append({
            "id": p.id,
            "url": get_image_url(p.minio_key),
            "caption": p.caption,
            "uploader": p.uploader.username if p.uploader else "Unknown",
            "likes_count": len(p.likes),
            "views_count": len(p.views),  # New: Count total views
            "viewed_by": [v.user_id for v in p.views],
            "comments": [
                {"user": c.user_id, "text": c.text} for c in p.comments
            ]
        })
    return feed


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
def delete_photo(photo_id: int, db: Session = Depends(get_db)):
    photo = db.query(Photo).filter(Photo.id == photo_id).first()
    if not photo:
        raise HTTPException(status_code=404,
                            detail="Photo not found")

    # Note: In a full app, you'd also delete the file from MinIO here
    db.delete(photo)
    db.commit()
    return {"message": "Deleted"}


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
