# tests/test_family_photos.py
"""
Tests for `app/api/v1/family_photos.py`, focused on the "liked_by" avatar
feature (who-liked-this-photo UI) added on top of the like/unlike toggle,
plus baseline coverage of the endpoints that feature depends on.

There was previously no test coverage at all for this router.
"""
import pytest

from app.core.storage import get_image_url

pytestmark = pytest.mark.integration


class TestLikedByFeed:

    def test_no_likes_returns_empty_liked_by(self, parent_client, make_user,
                                             make_photo):
        uploader = make_user(username="uploader")
        photo = make_photo(uploader)

        resp = parent_client.get("/v1/family-photos/feed")

        assert resp.status_code == 200
        body = next(p for p in resp.json() if p["id"] == photo.id)
        assert body["liked_by"] == []
        assert body["stats"]["likes"] == 0

    def test_single_like_appears_in_liked_by_with_avatar(
            self, parent_client, client, make_user, make_photo, auth_headers):
        uploader = make_user(username="uploader")
        liker = make_user(
            username="liker", display_name="Liker Person",
            profile_photo_key="avatars/liker.jpg")
        photo = make_photo(uploader)

        like_resp = client.post(f"/v1/family-photos/{photo.id}/like",
                                headers=auth_headers(liker))
        assert like_resp.status_code == 200

        feed = parent_client.get("/v1/family-photos/feed").json()
        body = next(p for p in feed if p["id"] == photo.id)

        assert body["liked_by"] == [{
            "id": liker.id,
            "display_name": "Liker Person",
            "profile_photo_url": get_image_url("avatars/liker.jpg"),
        }]
        assert body["stats"]["likes"] == 1

    def test_liked_by_falls_back_to_username_without_display_name(
            self, parent_client, client, make_user, make_photo, auth_headers):
        uploader = make_user(username="uploader")
        liker = make_user(username="no_nickname", display_name=None)
        photo = make_photo(uploader)

        client.post(f"/v1/family-photos/{photo.id}/like",
                    headers=auth_headers(liker))

        feed = parent_client.get("/v1/family-photos/feed").json()
        body = next(p for p in feed if p["id"] == photo.id)

        assert body["liked_by"][0]["display_name"] == "no_nickname"

    def test_liked_by_profile_photo_url_none_without_photo(
            self, parent_client, client, make_user, make_photo, auth_headers):
        uploader = make_user(username="uploader")
        liker = make_user(username="no_avatar", profile_photo_key=None)
        photo = make_photo(uploader)

        client.post(f"/v1/family-photos/{photo.id}/like",
                    headers=auth_headers(liker))

        feed = parent_client.get("/v1/family-photos/feed").json()
        body = next(p for p in feed if p["id"] == photo.id)

        assert body["liked_by"][0]["profile_photo_url"] is None

    def test_multiple_likers_all_appear_in_liked_by(
            self, parent_client, client, make_user, make_photo, auth_headers):
        uploader = make_user(username="uploader")
        alice = make_user(username="alice", display_name="Alice")
        bob = make_user(username="bob", display_name="Bob")
        carol = make_user(username="carol", display_name="Carol")
        photo = make_photo(uploader)

        for user in (alice, bob, carol):
            client.post(f"/v1/family-photos/{photo.id}/like",
                        headers=auth_headers(user))

        feed = parent_client.get("/v1/family-photos/feed").json()
        body = next(p for p in feed if p["id"] == photo.id)

        assert {u["id"] for u in body["liked_by"]} == {
            alice.id, bob.id, carol.id
        }
        assert body["stats"]["likes"] == 3
        assert len(body["liked_by"]) == body["stats"]["likes"]

    def test_unlike_removes_user_from_liked_by(
            self, parent_client, client, make_user, make_photo, auth_headers):
        uploader = make_user(username="uploader")
        liker = make_user(username="liker")
        photo = make_photo(uploader)
        headers = auth_headers(liker)

        client.post(f"/v1/family-photos/{photo.id}/like", headers=headers)
        # Second call toggles the like back off
        toggle_off = client.post(f"/v1/family-photos/{photo.id}/like",
                                 headers=headers)
        assert toggle_off.status_code == 200

        feed = parent_client.get("/v1/family-photos/feed").json()
        body = next(p for p in feed if p["id"] == photo.id)

        assert body["liked_by"] == []
        assert body["stats"]["likes"] == 0

    def test_like_requires_authentication(self, client, make_user,
                                          make_photo):
        uploader = make_user(username="uploader")
        photo = make_photo(uploader)

        resp = client.post(f"/v1/family-photos/{photo.id}/like")

        assert resp.status_code == 401

    def test_stats_no_longer_include_view_count(self, parent_client, client,
                                                make_user, make_photo):
        """Locks in the intentional removal of `stats.views` from the
        payload -- viewing is implicit and no longer surfaced in the UI."""
        uploader = make_user(username="uploader")
        photo = make_photo(uploader)

        feed = parent_client.get("/v1/family-photos/feed").json()
        body = next(p for p in feed if p["id"] == photo.id)

        assert "views" not in body["stats"]


class TestLikedByAcrossListingEndpoints:
    """format_photo_list() backs several list endpoints -- make sure
    liked_by shows up consistently everywhere photos are listed, not
    just on /feed."""

    def test_liked_by_present_on_archive(self, parent_client, client,
                                         make_user, make_photo, auth_headers):
        uploader = make_user(username="uploader")
        liker = make_user(username="liker", display_name="Liker")
        photo = make_photo(uploader)

        client.post(f"/v1/family-photos/{photo.id}/like",
                    headers=auth_headers(liker))

        archive = parent_client.get("/v1/family-photos/archive").json()
        body = next(p for p in archive if p["id"] == photo.id)

        assert body["liked_by"] == [{
            "id": liker.id,
            "display_name": "Liker",
            "profile_photo_url": None,
        }]

    def test_liked_by_present_on_album_photos(self, parent_client, client,
                                              make_user, make_photo,
                                              auth_headers):
        uploader = make_user(username="uploader")
        liker = make_user(username="liker", display_name="Liker")

        album_resp = client.post(
            "/v1/family-photos/albums",
            data={"title": "Test Album"},
            headers=auth_headers(uploader),
        )
        assert album_resp.status_code == 200
        album_id = album_resp.json()["id"]

        photo = make_photo(uploader, album_id=album_id)
        client.post(f"/v1/family-photos/{photo.id}/like",
                    headers=auth_headers(liker))

        album_photos = parent_client.get(
            f"/v1/family-photos/albums/{album_id}/photos").json()
        body = next(p for p in album_photos if p["id"] == photo.id)

        assert body["liked_by"][0]["id"] == liker.id


class TestPhotoReadsRequireLogin:
    """Every route that returns photos, albums or stats needs a token."""

    @pytest.mark.parametrize("path", [
        "/feed", "/historical", "/archive", "/albums",
        "/albums/1/photos", "/1/stats",
    ])
    def test_no_token_returns_401(self, client, path):
        assert client.get(f"/v1/family-photos{path}").status_code == 401

    @pytest.mark.parametrize("role", ["parent", "child"])
    def test_any_logged_in_user_can_read_the_feed(
            self, client_for, make_user, make_photo, role):
        photo = make_photo(make_user(username="uploader"))

        reader = client_for(make_user(role=role))

        resp = reader.get("/v1/family-photos/feed")

        assert resp.status_code == 200
        assert [p["id"] for p in resp.json()] == [photo.id]

    def test_user_list_requires_login(self, client, parent_client,
                                      make_user):
        make_user(username="alice")

        assert client.get("/v1/family-photos/users").status_code == 401
        listed = parent_client.get("/v1/family-photos/users")
        assert "alice" in [u["username"] for u in listed.json()]

    def test_login_options_expose_only_what_the_picker_needs(
            self, client, make_user):
        user = make_user(username="alice", display_name="Alice",
                         role="child")

        resp = client.get("/v1/family-photos/login-options")

        assert resp.status_code == 200
        assert resp.json() == [{"id": user.id, "display_name": "Alice",
                                "profile_photo_url": None}]

    @pytest.mark.parametrize("audience,expected", [
        (None, {"Dad", "Mum", "Oma", "Kid"}),
        ("parents", {"Dad", "Mum"}),
        ("household", {"Dad", "Mum", "Kid"}),
    ])
    def test_login_options_can_be_narrowed_to_an_audience(
            self, client, make_user, audience, expected):
        for name, role in [("Dad", "admin"), ("Mum", "parent"),
                           ("Oma", "adult"), ("Kid", "child")]:
            make_user(username=name.lower(), display_name=name, role=role)
        make_user(username="waiting", display_name="Waiting",
                  role="parent", status="pending")

        resp = client.get("/v1/family-photos/login-options",
                          params={"audience": audience} if audience else {})

        assert resp.status_code == 200
        assert {u["display_name"] for u in resp.json()} == expected
        assert set(resp.json()[0]) == {"id", "display_name",
                                       "profile_photo_url"}

    def test_unknown_audience_rejected(self, client):
        resp = client.get("/v1/family-photos/login-options",
                          params={"audience": "everyone-please"})

        assert resp.status_code == 422

    def test_me_requires_a_token(self, client):
        assert client.get("/v1/family-photos/me").status_code == 401

    def test_me_returns_the_profile_and_linked_child(
            self, client_for, make_user, make_child, db_session):
        user = make_user(username="penny", display_name="Penny",
                         role="child")
        child = make_child(name="Penelope")
        child.user_id = user.id
        db_session.commit()

        resp = client_for(user).get("/v1/family-photos/me")

        assert resp.status_code == 200
        assert resp.json() == {
            "id": user.id, "username": "penny", "display_name": "Penny",
            "role": "child", "profile_photo_url": None, "bio": None,
            "child_id": child.id, "child_name": "Penelope"}

    def test_me_without_a_linked_child(self, client_for, make_user):
        resp = client_for(make_user(role="parent")).get(
            "/v1/family-photos/me")

        assert resp.json()["child_name"] is None
        assert resp.json()["child_id"] is None

    def test_me_rejects_a_deactivated_account(self, client_for, make_user,
                                              db_session):
        user = make_user(role="adult")
        client = client_for(user)
        user.status = "pending"
        db_session.commit()

        assert client.get("/v1/family-photos/me").status_code == 401

    def test_login_returns_the_full_profile(self, client, make_user):
        user = make_user(username="alice", display_name="Alice",
                         role="child", password="pw")

        resp = client.post("/v1/family-photos/login",
                           json={"user_id": user.id, "password": "pw"})

        assert resp.status_code == 200
        assert resp.json()["user"] == {
            "id": user.id, "username": "alice", "display_name": "Alice",
            "role": "child", "profile_photo_url": None, "bio": None}


class TestDbManagerRemoved:

    @pytest.mark.parametrize("method,path", [
        ("get", "/v1/list-tables"),
        ("get", "/v1/tables/users"),
        ("post", "/v1/tables/users/records"),
        ("post", "/v1/create-table/anything"),
    ])
    def test_generic_table_routes_are_gone(self, parent_client, method,
                                           path):
        resp = getattr(parent_client, method)(path)

        assert resp.status_code == 404
