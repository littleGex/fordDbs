# tests/test_photo_content_type.py
"""
Images are stored with their content type, so signed links serve them
as images rather than application/octet-stream (#59). Also covers the
profile photo sent with a new registration, which never uploaded.
Needs the disposable test MinIO (see minio_test_bucket in conftest.py).
"""
import pytest

from app.core.storage import BUCKET_NAME, minio_client, stored_image_type
from app.models.photo_model import Photo
from app.models.user_models import User

pytestmark = [pytest.mark.integration,
              pytest.mark.usefixtures("minio_test_bucket")]

BASE = "/v1/family-photos"
TINY_PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a4944415478da62620000060003013122f00e0000000049454e44ae426082"
)


def stored_type(key):
    return minio_client.stat_object(BUCKET_NAME, key).content_type


class TestStoredImageType:

    @pytest.mark.parametrize("name,sent,expected", [
        ("a.png", "image/png", "image/png"),
        ("a.jpg", "application/octet-stream", "image/jpeg"),
        ("a.HEIC", "", "image/heic"),
        ("a.webp", None, "image/webp"),
        ("noext", "application/octet-stream", "image/jpeg"),
        ("a.png", "text/html", "image/png"),
        ("a.html", "text/html", "image/jpeg"),
    ])
    def test_type_from_upload_then_extension(self, name, sent, expected):
        assert stored_image_type(name, sent) == expected


class TestFeedPhoto:

    def test_feed_photo_stored_with_its_type(self, client, make_user,
                                             auth_headers, db_session):
        uploader = make_user(username="uploader")

        resp = client.post(f"{BASE}/upload",
                           files={"file": ("p.png", TINY_PNG_BYTES,
                                           "image/png")},
                           headers=auth_headers(uploader))

        assert resp.status_code == 200, resp.text
        photo = db_session.query(Photo).one()
        assert stored_type(photo.minio_key) == "image/png"

    def test_generic_upload_type_falls_back_to_extension(
            self, client, make_user, auth_headers, db_session):
        uploader = make_user(username="uploader")

        resp = client.post(f"{BASE}/upload",
                           files={"file": ("p.jpg", TINY_PNG_BYTES,
                                           "application/octet-stream")},
                           headers=auth_headers(uploader))

        assert resp.status_code == 200, resp.text
        photo = db_session.query(Photo).one()
        assert stored_type(photo.minio_key) == "image/jpeg"


class TestProfilePhotos:

    def test_registration_with_photo_creates_user_and_stores_it(
            self, client, db_session):
        resp = client.post(f"{BASE}/users", data={
            "username": "newbie", "display_name": "Newbie",
            "password": "password1", "birth_year": 1980},
            files={"file": ("me.png", TINY_PNG_BYTES, "image/png")})

        assert resp.status_code == 200, resp.text
        user = db_session.query(User).filter_by(username="newbie").one()
        assert user.profile_photo_key.startswith("avatars/")
        assert user.profile_photo_key.endswith(".png")
        assert stored_type(user.profile_photo_key) == "image/png"

    def test_profile_update_photo_stored_with_its_type(
            self, client, make_user, auth_headers, db_session):
        user = make_user(username="me")

        resp = client.post(f"{BASE}/profile/update",
                           files={"file": ("me.jpg", TINY_PNG_BYTES,
                                           "application/octet-stream")},
                           headers=auth_headers(user))

        assert resp.status_code == 200, resp.text
        db_session.refresh(user)
        assert stored_type(user.profile_photo_key) == "image/jpeg"
