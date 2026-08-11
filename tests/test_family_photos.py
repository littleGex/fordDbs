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

    def test_no_likes_returns_empty_liked_by(self, client, make_user,
                                             make_photo):
        uploader = make_user(username="uploader")
        photo = make_photo(uploader)

        resp = client.get("/v1/family-photos/feed")

        assert resp.status_code == 200
        body = next(p for p in resp.json() if p["id"] == photo.id)
        assert body["liked_by"] == []
        assert body["stats"]["likes"] == 0

    def test_single_like_appears_in_liked_by_with_avatar(
            self, client, make_user, make_photo, auth_headers):
        uploader = make_user(username="uploader")
        liker = make_user(
            username="liker", display_name="Liker Person",
            profile_photo_key="avatars/liker.jpg")
        photo = make_photo(uploader)

        like_resp = client.post(f"/v1/family-photos/{photo.id}/like",
                                headers=auth_headers(liker))
        assert like_resp.status_code == 200

        feed = client.get("/v1/family-photos/feed").json()
        body = next(p for p in feed if p["id"] == photo.id)

        assert body["liked_by"] == [{
            "id": liker.id,
            "display_name": "Liker Person",
            "profile_photo_url": get_image_url("avatars/liker.jpg"),
        }]
        assert body["stats"]["likes"] == 1

    def test_liked_by_falls_back_to_username_without_display_name(
            self, client, make_user, make_photo, auth_headers):
        uploader = make_user(username="uploader")
        liker = make_user(username="no_nickname", display_name=None)
        photo = make_photo(uploader)

        client.post(f"/v1/family-photos/{photo.id}/like",
                    headers=auth_headers(liker))

        feed = client.get("/v1/family-photos/feed").json()
        body = next(p for p in feed if p["id"] == photo.id)

        assert body["liked_by"][0]["display_name"] == "no_nickname"

    def test_liked_by_profile_photo_url_none_without_photo(
            self, client, make_user, make_photo, auth_headers):
        uploader = make_user(username="uploader")
        liker = make_user(username="no_avatar", profile_photo_key=None)
        photo = make_photo(uploader)

        client.post(f"/v1/family-photos/{photo.id}/like",
                    headers=auth_headers(liker))

        feed = client.get("/v1/family-photos/feed").json()
        body = next(p for p in feed if p["id"] == photo.id)

        assert body["liked_by"][0]["profile_photo_url"] is None

    def test_multiple_likers_all_appear_in_liked_by(
            self, client, make_user, make_photo, auth_headers):
        uploader = make_user(username="uploader")
        alice = make_user(username="alice", display_name="Alice")
        bob = make_user(username="bob", display_name="Bob")
        carol = make_user(username="carol", display_name="Carol")
        photo = make_photo(uploader)

        for user in (alice, bob, carol):
            client.post(f"/v1/family-photos/{photo.id}/like",
                       headers=auth_headers(user))

        feed = client.get("/v1/family-photos/feed").json()
        body = next(p for p in feed if p["id"] == photo.id)

        assert {u["id"] for u in body["liked_by"]} == {
            alice.id, bob.id, carol.id
        }
        assert body["stats"]["likes"] == 3
        assert len(body["liked_by"]) == body["stats"]["likes"]

    def test_unlike_removes_user_from_liked_by(
            self, client, make_user, make_photo, auth_headers):
        uploader = make_user(username="uploader")
        liker = make_user(username="liker")
        photo = make_photo(uploader)
        headers = auth_headers(liker)

        client.post(f"/v1/family-photos/{photo.id}/like", headers=headers)
        # Second call toggles the like back off
        toggle_off = client.post(f"/v1/family-photos/{photo.id}/like",
                                 headers=headers)
        assert toggle_off.status_code == 200

        feed = client.get("/v1/family-photos/feed").json()
        body = next(p for p in feed if p["id"] == photo.id)

        assert body["liked_by"] == []
        assert body["stats"]["likes"] == 0

    def test_like_requires_authentication(self, client, make_user,
                                          make_photo):
        uploader = make_user(username="uploader")
        photo = make_photo(uploader)

        resp = client.post(f"/v1/family-photos/{photo.id}/like")

        assert resp.status_code == 401

    def test_stats_no_longer_include_view_count(self, client, make_user,
                                                make_photo):
        """Locks in the intentional removal of `stats.views` from the
        payload -- viewing is implicit and no longer surfaced in the UI."""
        uploader = make_user(username="uploader")
        photo = make_photo(uploader)

        feed = client.get("/v1/family-photos/feed").json()
        body = next(p for p in feed if p["id"] == photo.id)

        assert "views" not in body["stats"]


class TestLikedByAcrossListingEndpoints:
    """format_photo_list() backs several list endpoints -- make sure
    liked_by shows up consistently everywhere photos are listed, not
    just on /feed."""

    def test_liked_by_present_on_archive(self, client, make_user,
                                         make_photo, auth_headers):
        uploader = make_user(username="uploader")
        liker = make_user(username="liker", display_name="Liker")
        photo = make_photo(uploader)

        client.post(f"/v1/family-photos/{photo.id}/like",
                    headers=auth_headers(liker))

        archive = client.get("/v1/family-photos/archive").json()
        body = next(p for p in archive if p["id"] == photo.id)

        assert body["liked_by"] == [{
            "id": liker.id,
            "display_name": "Liker",
            "profile_photo_url": None,
        }]

    def test_liked_by_present_on_album_photos(self, client, make_user,
                                              make_photo, auth_headers):
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

        album_photos = client.get(
            f"/v1/family-photos/albums/{album_id}/photos").json()
        body = next(p for p in album_photos if p["id"] == photo.id)

        assert body["liked_by"][0]["id"] == liker.id
