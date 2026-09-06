import asyncio
from fastapi import (APIRouter, Depends, HTTPException, Form,
                     Query, WebSocket, WebSocketDisconnect)
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.database.database import get_db
from app.core.storage import get_image_url
from app.models.message_model import Conversation, ConversationMember, Message
from app.models.user_models import User
from app.api.v1.family_photos import get_current_user, SECRET_KEY, ALGORITHM
from datetime import datetime, timedelta
from jose import jwt, JWTError

messaging_router = APIRouter()

MESSAGE_DELETE_WINDOW = timedelta(hours=24)
# A client that vanishes without a clean close (phone locks, network
# drops, browser killed) can leave a socket the server still considers
# open -- send_json() on it may then hang indefinitely waiting on a
# peer that's gone, rather than raising. Without a timeout, one such
# zombie connection would block delivery to every connection after it
# in the same user's list.
SEND_TIMEOUT_SECONDS = 5


class ConnectionManager:
    """In-process registry of live WebSocket connections, keyed by
    user id. A user may have several connections open at once (e.g.
    phone + laptop), so each key maps to a list."""

    def __init__(self):
        self.active_connections: dict[int, list[WebSocket]] = {}

    async def connect(self, user_id: int, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.setdefault(user_id, []).append(websocket)

    def disconnect(self, user_id: int, websocket: WebSocket):
        connections = self.active_connections.get(user_id)
        if not connections:
            return
        if websocket in connections:
            connections.remove(websocket)
        if not connections:
            self.active_connections.pop(user_id, None)

    async def send_to_user(self, user_id: int, payload: dict):
        for websocket in list(self.active_connections.get(user_id, [])):
            try:
                await asyncio.wait_for(
                    websocket.send_json(payload), timeout=SEND_TIMEOUT_SECONDS)
            except Exception:
                self.disconnect(user_id, websocket)

    async def broadcast_to_users(self, user_ids, payload: dict):
        for user_id in user_ids:
            await self.send_to_user(user_id, payload)


manager = ConnectionManager()


def format_message(message: Message) -> dict:
    is_deleted = message.deleted_at is not None
    return {
        "id": message.id,
        "conversation_id": message.conversation_id,
        "client_id": message.client_id,
        "sender_id": message.sender_id,
        "body": None if is_deleted else message.body,
        "photo_id": None if is_deleted else message.photo_id,
        "photo_url": (
            get_image_url(message.photo.minio_key)
            if not is_deleted and message.photo else None
        ),
        # Explicit isoformat(), not the raw datetime: FastAPI's normal
        # response pipeline runs return values through jsonable_encoder
        # (which handles datetime), but WebSocket.send_json() -- used
        # to push this same dict over the wire for live delivery --
        # does not, and raises TypeError on a raw datetime.
        "created_at": message.created_at.isoformat(),
        "deleted": is_deleted,
    }


def _get_membership_or_403(db: Session, conversation_id: int,
                           user_id: int) -> ConversationMember:
    membership = db.query(ConversationMember).filter_by(
        conversation_id=conversation_id, user_id=user_id).first()
    if not membership:
        raise HTTPException(
            status_code=403,
            detail="Not a member of this conversation")
    return membership


def _delete_conversation_if_empty(db: Session, conversation_id: int):
    remaining = db.query(ConversationMember).filter_by(
        conversation_id=conversation_id).count()
    if remaining == 0:
        conversation = db.query(Conversation).filter_by(
            id=conversation_id).first()
        if conversation:
            db.delete(conversation)


@messaging_router.get("/conversations")
def list_conversations(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)):
    memberships = db.query(ConversationMember).filter_by(
        user_id=current_user.id).all()

    result = []
    for membership in memberships:
        conversation = membership.conversation
        last_message = (
            db.query(Message)
            .filter(Message.conversation_id == conversation.id)
            .order_by(Message.id.desc())
            .first()
        )
        unread_count = db.query(Message).filter(
            Message.conversation_id == conversation.id,
            Message.deleted_at.is_(None),
            Message.id > (membership.last_read_message_id or 0),
        ).count()

        result.append({
            "id": conversation.id,
            "is_group": conversation.is_group,
            "title": conversation.title,
            "created_by": conversation.created_by,
            "member_ids": [m.user_id for m in conversation.members],
            "unread_count": unread_count,
            "last_message": (
                format_message(last_message) if last_message else None
            ),
        })

    return result


@messaging_router.post("/conversations")
def create_conversation(
        is_group: bool = Form(False),
        title: str = Form(None),
        member_ids: str = Form(...,
                               description="Comma-separated user ids to "
                                           "add alongside the creator"),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)):
    other_ids = {
        int(raw) for raw in member_ids.split(",") if raw.strip()
    }
    all_member_ids = other_ids | {current_user.id}

    conversation = Conversation(
        is_group=is_group,
        title=title,
        created_by=current_user.id,
    )
    db.add(conversation)
    db.flush()

    for user_id in all_member_ids:
        db.add(ConversationMember(conversation_id=conversation.id,
                                  user_id=user_id))

    db.commit()
    db.refresh(conversation)

    return {
        "id": conversation.id,
        "is_group": conversation.is_group,
        "title": conversation.title,
        "created_by": conversation.created_by,
        "member_ids": sorted(all_member_ids),
    }


@messaging_router.get("/conversations/{conversation_id}/messages")
def get_messages(
        conversation_id: int,
        after_id: int = Query(None, description="Sync forward from here"),
        before_id: int = Query(None, description="Scroll back from here"),
        limit: int = Query(50, le=200),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)):
    _get_membership_or_403(db, conversation_id, current_user.id)

    query = db.query(Message).filter(
        Message.conversation_id == conversation_id)

    if after_id is not None:
        messages = (
            query.filter(Message.id > after_id)
            .order_by(Message.id.asc())
            .limit(limit)
            .all()
        )
    else:
        if before_id is not None:
            query = query.filter(Message.id < before_id)
        messages = (
            query.order_by(Message.id.desc())
            .limit(limit)
            .all()
        )
        messages.reverse()

    return [format_message(m) for m in messages]


@messaging_router.post("/conversations/{conversation_id}/messages")
async def send_message(
        conversation_id: int,
        client_id: str = Form(...),
        body: str = Form(None),
        photo_id: int = Form(None),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)):
    membership = _get_membership_or_403(db, conversation_id, current_user.id)

    existing = db.query(Message).filter_by(
        conversation_id=conversation_id, client_id=client_id).first()
    if existing:
        return format_message(existing)

    message = Message(
        conversation_id=conversation_id,
        sender_id=current_user.id,
        body=body,
        photo_id=photo_id,
        client_id=client_id,
    )
    db.add(message)
    try:
        db.commit()
    except IntegrityError:
        # A concurrent retry of the same client_id landed first.
        db.rollback()
        existing = db.query(Message).filter_by(
            conversation_id=conversation_id, client_id=client_id).first()
        if existing:
            return format_message(existing)
        raise
    db.refresh(message)

    # The sender has, by definition, already seen the message they just
    # sent -- advance their own read pointer so it doesn't count as
    # unread to themselves (e.g. in the nav badge) on their next fetch.
    membership.last_read_message_id = message.id
    db.commit()

    payload = format_message(message)

    other_member_ids = [
        m.user_id for m in db.query(ConversationMember)
        .filter_by(conversation_id=conversation_id).all()
        if m.user_id != current_user.id
    ]
    await manager.broadcast_to_users(
        other_member_ids, {"type": "message", "data": payload})

    return payload


@messaging_router.post("/conversations/{conversation_id}/read")
def mark_read(
        conversation_id: int,
        message_id: int = Form(...),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)):
    membership = _get_membership_or_403(db, conversation_id, current_user.id)

    if (membership.last_read_message_id is None
            or message_id > membership.last_read_message_id):
        membership.last_read_message_id = message_id
        db.commit()

    return {"status": "ok",
            "last_read_message_id": membership.last_read_message_id}


@messaging_router.get("/sync")
def sync(
        after_id: int = Query(0),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)):
    conversation_ids = [
        m.conversation_id for m in
        db.query(ConversationMember).filter_by(
            user_id=current_user.id).all()
    ]

    messages = []
    if conversation_ids:
        messages = (
            db.query(Message)
            .filter(Message.conversation_id.in_(conversation_ids),
                    Message.id > after_id)
            .order_by(Message.id.asc())
            .all()
        )

    return {
        "messages": [format_message(m) for m in messages],
        "max_id": messages[-1].id if messages else after_id,
    }


@messaging_router.delete("/messages/{message_id}")
def delete_message(
        message_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)):
    message = db.query(Message).filter(Message.id == message_id).first()
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    is_parent = current_user.role == "parent"
    is_sender = message.sender_id == current_user.id

    if not is_parent:
        if not is_sender:
            raise HTTPException(
                status_code=403,
                detail="Not authorized to delete this message")
        if datetime.utcnow() - message.created_at > MESSAGE_DELETE_WINDOW:
            raise HTTPException(
                status_code=403,
                detail="Messages can only be deleted within 24 hours "
                       "of sending")

    message.deleted_at = datetime.utcnow()
    db.commit()

    return {"status": "deleted"}


@messaging_router.post("/conversations/{conversation_id}/leave")
def leave_conversation(
        conversation_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)):
    membership = _get_membership_or_403(db, conversation_id, current_user.id)

    db.delete(membership)
    db.flush()
    _delete_conversation_if_empty(db, conversation_id)
    db.commit()

    return {"status": "left"}


@messaging_router.delete("/conversations/{conversation_id}/members/{user_id}")
def remove_member(
        conversation_id: int,
        user_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)):
    conversation = db.query(Conversation).filter_by(
        id=conversation_id).first()
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    is_creator = conversation.created_by == current_user.id
    is_parent = current_user.role == "parent"
    if not (is_creator or is_parent):
        raise HTTPException(
            status_code=403,
            detail="Only the group creator or a parent can remove members")

    membership = db.query(ConversationMember).filter_by(
        conversation_id=conversation_id, user_id=user_id).first()
    if not membership:
        raise HTTPException(status_code=404, detail="Member not found")

    db.delete(membership)
    db.flush()
    _delete_conversation_if_empty(db, conversation_id)
    db.commit()

    return {"status": "removed"}


@messaging_router.delete("/conversations/{conversation_id}")
def delete_conversation(
        conversation_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)):
    conversation = db.query(Conversation).filter_by(
        id=conversation_id).first()
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    is_creator = conversation.created_by == current_user.id
    is_parent = current_user.role == "parent"
    if not (is_creator or is_parent):
        raise HTTPException(
            status_code=403,
            detail="Only the conversation creator or a parent can "
                   "delete this conversation")

    db.delete(conversation)
    db.commit()

    return {"status": "deleted"}


def _authenticate_websocket(token: str, db: Session):
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            return None
    except JWTError:
        return None
    return db.query(User).filter(User.id == int(user_id)).first()


@messaging_router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket,
                             db: Session = Depends(get_db)):
    token = websocket.query_params.get("token")
    user = _authenticate_websocket(token, db)

    if not user:
        await websocket.close(code=4401)
        return

    await manager.connect(user.id, websocket)
    try:
        while True:
            # Clients don't need to send anything; this just keeps the
            # connection open and detects disconnects.
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(user.id, websocket)
