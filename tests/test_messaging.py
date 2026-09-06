# tests/test_messaging.py
"""
Tests for `app/api/v1/messaging.py`: membership enforcement, client_id
retry dedupe, unread counts against last_read_message_id, the 24h
message delete window, and cascade cleanup when the last member of a
conversation leaves.
"""
from datetime import datetime, timedelta

import pytest

from app.models.message_model import Conversation, Message

pytestmark = pytest.mark.integration


class TestMembershipEnforcement:

    def test_non_member_cannot_fetch_messages(
            self, client, make_user, make_conversation, auth_headers):
        alice = make_user(username="alice")
        bob = make_user(username="bob")
        outsider = make_user(username="outsider")
        conversation = make_conversation(alice, bob)

        resp = client.get(
            f"/v1/messaging/conversations/{conversation.id}/messages",
            headers=auth_headers(outsider))

        assert resp.status_code == 403

    def test_non_member_cannot_send_message(
            self, client, make_user, make_conversation, auth_headers):
        alice = make_user(username="alice")
        bob = make_user(username="bob")
        outsider = make_user(username="outsider")
        conversation = make_conversation(alice, bob)

        resp = client.post(
            f"/v1/messaging/conversations/{conversation.id}/messages",
            data={"client_id": "c1", "body": "hi"},
            headers=auth_headers(outsider))

        assert resp.status_code == 403

    def test_non_member_cannot_mark_read(
            self, client, make_user, make_conversation, make_message,
            auth_headers):
        alice = make_user(username="alice")
        bob = make_user(username="bob")
        outsider = make_user(username="outsider")
        conversation = make_conversation(alice, bob)
        message = make_message(conversation, alice)

        resp = client.post(
            f"/v1/messaging/conversations/{conversation.id}/read",
            data={"message_id": message.id},
            headers=auth_headers(outsider))

        assert resp.status_code == 403

    def test_non_member_cannot_leave(
            self, client, make_user, make_conversation, auth_headers):
        alice = make_user(username="alice")
        bob = make_user(username="bob")
        outsider = make_user(username="outsider")
        conversation = make_conversation(alice, bob)

        resp = client.post(
            f"/v1/messaging/conversations/{conversation.id}/leave",
            headers=auth_headers(outsider))

        assert resp.status_code == 403

    def test_member_can_fetch_messages(
            self, client, make_user, make_conversation, make_message,
            auth_headers):
        alice = make_user(username="alice")
        bob = make_user(username="bob")
        conversation = make_conversation(alice, bob)
        make_message(conversation, alice, body="hello bob")

        resp = client.get(
            f"/v1/messaging/conversations/{conversation.id}/messages",
            headers=auth_headers(bob))

        assert resp.status_code == 200
        assert len(resp.json()) == 1
        assert resp.json()[0]["body"] == "hello bob"

    def test_unauthenticated_request_is_rejected(
            self, client, make_user, make_conversation):
        alice = make_user(username="alice")
        bob = make_user(username="bob")
        conversation = make_conversation(alice, bob)

        resp = client.get(
            f"/v1/messaging/conversations/{conversation.id}/messages")

        assert resp.status_code == 401


class TestClientIdDedupe:

    def test_retry_with_same_client_id_returns_existing_message(
            self, client, make_user, make_conversation, auth_headers):
        alice = make_user(username="alice")
        bob = make_user(username="bob")
        conversation = make_conversation(alice, bob)
        headers = auth_headers(alice)
        payload = {"client_id": "retry-1", "body": "are you there?"}

        first = client.post(
            f"/v1/messaging/conversations/{conversation.id}/messages",
            data=payload, headers=headers)
        assert first.status_code == 200

        retry = client.post(
            f"/v1/messaging/conversations/{conversation.id}/messages",
            data=payload, headers=headers)
        assert retry.status_code == 200

        assert first.json()["id"] == retry.json()["id"]

        messages = client.get(
            f"/v1/messaging/conversations/{conversation.id}/messages",
            headers=headers).json()
        assert len(messages) == 1

    def test_same_client_id_in_different_conversations_is_not_deduped(
            self, client, make_user, make_conversation, auth_headers):
        alice = make_user(username="alice")
        bob = make_user(username="bob")
        carol = make_user(username="carol")
        conv1 = make_conversation(alice, bob)
        conv2 = make_conversation(alice, carol)
        headers = auth_headers(alice)

        resp1 = client.post(
            f"/v1/messaging/conversations/{conv1.id}/messages",
            data={"client_id": "shared-id", "body": "hi bob"},
            headers=headers)
        resp2 = client.post(
            f"/v1/messaging/conversations/{conv2.id}/messages",
            data={"client_id": "shared-id", "body": "hi carol"},
            headers=headers)

        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert resp1.json()["id"] != resp2.json()["id"]


class TestUnreadCounts:

    def test_unread_count_reflects_last_read_message_id(
            self, client, make_user, make_conversation, make_message,
            auth_headers):
        alice = make_user(username="alice")
        bob = make_user(username="bob")
        conversation = make_conversation(alice, bob)
        m1 = make_message(conversation, alice, body="one")
        make_message(conversation, alice, body="two")
        make_message(conversation, alice, body="three")

        convos = client.get(
            "/v1/messaging/conversations", headers=auth_headers(bob)).json()
        summary = next(c for c in convos if c["id"] == conversation.id)
        assert summary["unread_count"] == 3

        client.post(
            f"/v1/messaging/conversations/{conversation.id}/read",
            data={"message_id": m1.id}, headers=auth_headers(bob))

        convos = client.get(
            "/v1/messaging/conversations", headers=auth_headers(bob)).json()
        summary = next(c for c in convos if c["id"] == conversation.id)
        assert summary["unread_count"] == 2

    def test_new_conversation_with_no_reads_is_fully_unread(
            self, client, make_user, make_conversation, make_message,
            auth_headers):
        alice = make_user(username="alice")
        bob = make_user(username="bob")
        conversation = make_conversation(alice, bob)
        make_message(conversation, alice)
        make_message(conversation, alice)

        convos = client.get(
            "/v1/messaging/conversations", headers=auth_headers(bob)).json()
        summary = next(c for c in convos if c["id"] == conversation.id)
        assert summary["unread_count"] == 2

    def test_sender_does_not_see_their_own_new_message_as_unread(
            self, client, make_user, make_conversation, auth_headers):
        alice = make_user(username="alice")
        bob = make_user(username="bob")
        conversation = make_conversation(alice, bob)

        client.post(
            f"/v1/messaging/conversations/{conversation.id}/messages",
            data={"client_id": "c1", "body": "hi bob"},
            headers=auth_headers(alice))

        convos = client.get(
            "/v1/messaging/conversations", headers=auth_headers(alice)).json()
        summary = next(c for c in convos if c["id"] == conversation.id)
        assert summary["unread_count"] == 0

    def test_mark_read_ignores_older_message_id(
            self, client, make_user, make_conversation, make_message,
            auth_headers):
        alice = make_user(username="alice")
        bob = make_user(username="bob")
        conversation = make_conversation(alice, bob)
        m1 = make_message(conversation, alice, body="one")
        m2 = make_message(conversation, alice, body="two")
        headers = auth_headers(bob)

        client.post(
            f"/v1/messaging/conversations/{conversation.id}/read",
            data={"message_id": m2.id}, headers=headers)
        resp = client.post(
            f"/v1/messaging/conversations/{conversation.id}/read",
            data={"message_id": m1.id}, headers=headers)

        assert resp.json()["last_read_message_id"] == m2.id


class TestDeleteWindow:

    def test_sender_can_delete_within_window(
            self, client, make_user, make_conversation, make_message,
            auth_headers):
        alice = make_user(username="alice", role="child")
        bob = make_user(username="bob", role="child")
        conversation = make_conversation(alice, bob)
        message = make_message(conversation, alice)

        resp = client.delete(
            f"/v1/messaging/messages/{message.id}",
            headers=auth_headers(alice))
        assert resp.status_code == 200

        messages = client.get(
            f"/v1/messaging/conversations/{conversation.id}/messages",
            headers=auth_headers(bob)).json()
        assert messages[0]["deleted"] is True
        assert messages[0]["body"] is None

    def test_sender_cannot_delete_after_window(
            self, client, make_user, make_conversation, make_message,
            auth_headers):
        alice = make_user(username="alice", role="child")
        bob = make_user(username="bob", role="child")
        conversation = make_conversation(alice, bob)
        old_timestamp = datetime.utcnow() - timedelta(hours=25)
        message = make_message(conversation, alice, created_at=old_timestamp)

        resp = client.delete(
            f"/v1/messaging/messages/{message.id}",
            headers=auth_headers(alice))

        assert resp.status_code == 403

    def test_sender_can_delete_just_inside_window(
            self, client, make_user, make_conversation, make_message,
            auth_headers):
        alice = make_user(username="alice", role="child")
        bob = make_user(username="bob", role="child")
        conversation = make_conversation(alice, bob)
        recent_timestamp = datetime.utcnow() - timedelta(hours=23)
        message = make_message(
            conversation, alice, created_at=recent_timestamp)

        resp = client.delete(
            f"/v1/messaging/messages/{message.id}",
            headers=auth_headers(alice))

        assert resp.status_code == 200

    def test_non_sender_cannot_delete(
            self, client, make_user, make_conversation, make_message,
            auth_headers):
        alice = make_user(username="alice", role="child")
        bob = make_user(username="bob", role="child")
        conversation = make_conversation(alice, bob)
        message = make_message(conversation, alice)

        resp = client.delete(
            f"/v1/messaging/messages/{message.id}",
            headers=auth_headers(bob))

        assert resp.status_code == 403

    def test_parent_can_delete_anytime(
            self, client, make_user, make_conversation, make_message,
            auth_headers):
        alice = make_user(username="alice", role="child")
        bob = make_user(username="bob", role="child")
        parent = make_user(username="mom", role="parent")
        conversation = make_conversation(alice, bob)
        old_timestamp = datetime.utcnow() - timedelta(days=30)
        message = make_message(conversation, alice, created_at=old_timestamp)

        resp = client.delete(
            f"/v1/messaging/messages/{message.id}",
            headers=auth_headers(parent))

        assert resp.status_code == 200


class TestLeaveConversationCascade:

    def test_conversation_survives_while_a_member_remains(
            self, client, make_user, make_conversation, make_message,
            db_session, auth_headers):
        alice = make_user(username="alice")
        bob = make_user(username="bob")
        conversation = make_conversation(alice, bob)
        make_message(conversation, alice)
        conversation_id = conversation.id

        resp = client.post(
            f"/v1/messaging/conversations/{conversation_id}/leave",
            headers=auth_headers(alice))

        assert resp.status_code == 200
        assert db_session.query(Conversation).filter_by(
            id=conversation_id).first() is not None

    def test_conversation_and_messages_removed_when_last_member_leaves(
            self, client, make_user, make_conversation, make_message,
            db_session, auth_headers):
        alice = make_user(username="alice")
        bob = make_user(username="bob")
        conversation = make_conversation(alice, bob)
        make_message(conversation, alice)
        make_message(conversation, bob)
        conversation_id = conversation.id

        client.post(
            f"/v1/messaging/conversations/{conversation_id}/leave",
            headers=auth_headers(alice))
        client.post(
            f"/v1/messaging/conversations/{conversation_id}/leave",
            headers=auth_headers(bob))

        assert db_session.query(Conversation).filter_by(
            id=conversation_id).first() is None
        assert db_session.query(Message).filter_by(
            conversation_id=conversation_id).count() == 0

    def test_second_leave_attempt_is_rejected_not_a_member(
            self, client, make_user, make_conversation, auth_headers):
        alice = make_user(username="alice")
        bob = make_user(username="bob")
        conversation = make_conversation(alice, bob)
        conversation_id = conversation.id

        client.post(
            f"/v1/messaging/conversations/{conversation_id}/leave",
            headers=auth_headers(alice))
        resp = client.post(
            f"/v1/messaging/conversations/{conversation_id}/leave",
            headers=auth_headers(alice))

        assert resp.status_code == 403


class TestWebSocketDelivery:
    """format_message()'s dict is returned two ways: as a normal HTTP
    JSON response (where FastAPI's jsonable_encoder silently converts
    datetime -> str) and pushed raw over a WebSocket via send_json(),
    which does NOT run jsonable_encoder and raises TypeError on a bare
    datetime. A plain HTTP-only test can't catch that divergence --
    this exercises the actual send_json() wire path via a real
    WebSocketTestSession, the way manual testing caught it."""

    def test_new_message_is_delivered_live_to_other_member(
            self, client, make_user, make_conversation, auth_headers):
        alice = make_user(username="alice")
        bob = make_user(username="bob")
        conversation = make_conversation(alice, bob)

        bob_token = auth_headers(bob)["Authorization"].split(" ")[1]

        with client.websocket_connect(
                f"/v1/messaging/ws?token={bob_token}") as websocket:
            resp = client.post(
                f"/v1/messaging/conversations/{conversation.id}/messages",
                data={"client_id": "ws-1", "body": "hello over the wire"},
                headers=auth_headers(alice))
            assert resp.status_code == 200

            event = websocket.receive_json()

        assert event["type"] == "message"
        assert event["data"]["body"] == "hello over the wire"
        assert event["data"]["sender_id"] == alice.id
        # The regression this guards: created_at must already be a
        # JSON-safe string, not a raw datetime that send_json() can't
        # encode.
        assert isinstance(event["data"]["created_at"], str)

    def test_sender_does_not_receive_their_own_message_over_the_socket(
            self, client, make_user, make_conversation, auth_headers):
        alice = make_user(username="alice")
        bob = make_user(username="bob")
        conversation = make_conversation(alice, bob)

        alice_token = auth_headers(alice)["Authorization"].split(" ")[1]

        with client.websocket_connect(
                f"/v1/messaging/ws?token={alice_token}") as websocket:
            resp = client.post(
                f"/v1/messaging/conversations/{conversation.id}/messages",
                data={"client_id": "ws-2", "body": "just for bob"},
                headers=auth_headers(alice))
            assert resp.status_code == 200

            # A second, unrelated message confirms the socket is alive
            # and simply was never sent the first one -- not stalled.
            client.post(
                f"/v1/messaging/conversations/{conversation.id}/messages",
                data={"client_id": "ws-3", "body": "from bob"},
                headers=auth_headers(bob))

            event = websocket.receive_json()

        assert event["data"]["body"] == "from bob"

    def test_invalid_token_closes_the_connection(self, client):
        with pytest.raises(Exception):
            with client.websocket_connect(
                    "/v1/messaging/ws?token=not-a-real-token") as websocket:
                websocket.receive_json()
