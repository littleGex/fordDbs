# tests/test_family_photos_video_upload.py
"""
Tests for video upload support on POST /v1/family-photos/upload:
server-side 30s duration enforcement (via ffprobe, not client-supplied
data) and H.264/AAC MP4 transcoding (via ffmpeg). See app/core/media.py.

Requires ffmpeg/ffprobe on PATH and a disposable test MinIO instance, in
addition to the real Postgres test database -- see make_video_file and
minio_test_bucket in conftest.py, which skip these tests at call time if
either isn't available locally (CI always has both).
"""
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("minio_test_bucket")]

# A minimal valid 1x1 PNG, for the image-path regression test.
TINY_PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a4944415478da62620000060003013122f00e0000000049454e44ae426082"
)


def _upload_video(client, headers, video_bytes, caption="A clip"):
    return client.post(
        "/v1/family-photos/upload",
        files={"file": ("clip.mp4", video_bytes, "video/mp4")},
        data={"caption": caption},
        headers=headers,
    )


class TestVideoUploadSuccess:

    def test_short_video_upload_succeeds_and_transcodes(
            self, client, make_user, auth_headers, make_video_file):
        uploader = make_user(username="uploader")
        clip = make_video_file(duration=2)

        resp = _upload_video(client, auth_headers(uploader), clip,
                             caption="Short clip")

        assert resp.status_code == 200

        feed = client.get("/v1/family-photos/feed").json()
        photo = feed[0]
        assert photo["media_type"] == "video"
        assert photo["caption"] == "Short clip"
        assert photo["url"].endswith(".mp4")
        # Allow encoder/frame-rounding slack around the requested duration.
        assert 1 <= photo["duration_seconds"] <= 4

    def test_video_near_cap_is_accepted(
            self, client, make_user, auth_headers, make_video_file):
        uploader = make_user(username="uploader")
        clip = make_video_file(duration=29)

        resp = _upload_video(client, auth_headers(uploader), clip)

        assert resp.status_code == 200
        feed = client.get("/v1/family-photos/feed").json()
        assert feed[0]["media_type"] == "video"


class TestVideoUploadRejection:

    def test_video_over_cap_rejected_no_photo_created(
            self, client, make_user, auth_headers, make_video_file):
        uploader = make_user(username="uploader")
        clip = make_video_file(duration=35)

        resp = _upload_video(client, auth_headers(uploader), clip)

        assert resp.status_code == 400
        assert client.get("/v1/family-photos/feed").json() == []

    def test_corrupt_video_input_rejected_cleanly(
            self, client, make_user, auth_headers):
        uploader = make_user(username="uploader")
        garbage = b"this is not a real video file, just garbage bytes"

        resp = _upload_video(client, auth_headers(uploader), garbage)

        assert resp.status_code == 400
        assert client.get("/v1/family-photos/feed").json() == []

    def test_video_upload_requires_authentication(
            self, client, make_video_file):
        clip = make_video_file(duration=2)

        resp = client.post(
            "/v1/family-photos/upload",
            files={"file": ("clip.mp4", clip, "video/mp4")},
        )

        assert resp.status_code == 401


class TestImageUploadRegression:

    def test_image_upload_still_sets_media_type_image(
            self, client, make_user, auth_headers):
        uploader = make_user(username="uploader")

        resp = client.post(
            "/v1/family-photos/upload",
            files={"file": ("photo.png", TINY_PNG_BYTES, "image/png")},
            data={"caption": "A photo"},
            headers=auth_headers(uploader),
        )

        assert resp.status_code == 200
        feed = client.get("/v1/family-photos/feed").json()
        photo = feed[0]
        assert photo["media_type"] == "image"
        assert photo["duration_seconds"] is None
        assert photo["url"].endswith(".png")
