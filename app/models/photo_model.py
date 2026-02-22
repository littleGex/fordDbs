from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.database.database import Base


class Photo(Base):
    __tablename__ = "photos"
    id = Column(Integer, primary_key=True, index=True)
    minio_key = Column(String, nullable=False)
    caption = Column(String)
    # Changed: removed () so it calls the function on insert
    timestamp = Column(DateTime,
                       default=lambda: datetime.now(timezone.utc))
    uploader_id = Column(Integer, ForeignKey("users.id"))

    uploader = relationship("User", back_populates="photos")
    likes = relationship("Like",
                         back_populates="photo",
                         cascade="all, delete-orphan")
    comments = relationship("Comment",
                            back_populates="photo",
                            cascade="all, delete-orphan")
    views = relationship("View",
                         back_populates="photo",
                         cascade="all, delete-orphan")


class Like(Base):
    __tablename__ = "photo_likes"
    id = Column(Integer, primary_key=True)
    photo_id = Column(Integer, ForeignKey("photos.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    photo = relationship("Photo", back_populates="likes")
    user = relationship("User")


class Comment(Base):
    __tablename__ = "photo_comments"
    id = Column(Integer, primary_key=True)
    photo_id = Column(Integer, ForeignKey("photos.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    text = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    photo = relationship("Photo", back_populates="comments")
    user = relationship("User")


class View(Base):
    __tablename__ = "photo_views"
    id = Column(Integer, primary_key=True)
    photo_id = Column(Integer, ForeignKey("photos.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    photo = relationship("Photo", back_populates="views")
    user = relationship("User")
