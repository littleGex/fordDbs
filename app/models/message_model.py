from sqlalchemy import (Column, Integer, String, Boolean,
                        DateTime, ForeignKey, Text, func,
                        UniqueConstraint)
from sqlalchemy.orm import relationship
from app.database.database import Base


class Conversation(Base):
    __tablename__ = "conversations"
    id = Column(Integer, primary_key=True, index=True)
    is_group = Column(Boolean, nullable=False, default=False)
    title = Column(String, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=func.now())

    creator = relationship("User")
    members = relationship("ConversationMember",
                           back_populates="conversation",
                           cascade="all, delete-orphan")
    messages = relationship("Message",
                            back_populates="conversation",
                            cascade="all, delete-orphan")


class ConversationMember(Base):
    __tablename__ = "conversation_members"
    __table_args__ = (
        UniqueConstraint("conversation_id", "user_id",
                         name="uq_conversation_member"),
    )
    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer,
                             ForeignKey("conversations.id"),
                             nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    # Not a ForeignKey on purpose: keeping this a plain pointer avoids
    # ORM/DB delete-ordering headaches when a conversation (and its
    # messages) is deleted -- see Conversation.messages' cascade.
    last_read_message_id = Column(Integer, nullable=True)
    joined_at = Column(DateTime, default=func.now())

    conversation = relationship("Conversation", back_populates="members")
    user = relationship("User")


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("conversation_id", "client_id",
                         name="uq_message_client_id"),
    )
    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer,
                             ForeignKey("conversations.id"),
                             nullable=False, index=True)
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    body = Column(Text, nullable=True)
    photo_id = Column(Integer, ForeignKey("photos.id"), nullable=True)
    # Client-generated id, used to dedupe retries when a send times out
    # on a flaky connection but actually landed server-side.
    client_id = Column(String, nullable=False)
    created_at = Column(DateTime, default=func.now())
    deleted_at = Column(DateTime, nullable=True)

    conversation = relationship("Conversation", back_populates="messages")
    sender = relationship("User")
    photo = relationship("Photo")
