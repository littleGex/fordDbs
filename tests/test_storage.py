# tests/test_storage.py
"""
Tests for the signed photo links in `app/core/storage.py` (#32).

The bucket gives anonymous visitors nothing, so every photo, video and
avatar the frontend shows has to come from a link signed for the
external host.
"""
import io
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit

import pytest
import requests

from app.core import storage
from app.core.storage import (BUCKET_NAME, EXTERNAL_URL_HOST, get_image_url,
                              minio_client, upload_image_to_storage)

NOW = datetime(2026, 11, 8, 10, 30, tzinfo=timezone.utc)


@pytest.mark.unit
class TestSignedLinks:

    def test_no_key_gives_no_link(self):
        assert get_image_url(None) is None
        assert get_image_url("") is None

    def test_link_is_signed_for_the_external_host(self):
        url = urlsplit(get_image_url("abc.jpeg", now=NOW))
        query = parse_qs(url.query)

        assert url.netloc == EXTERNAL_URL_HOST
        assert url.path == f"/{BUCKET_NAME}/abc.jpeg"
        assert query["X-Amz-Algorithm"] == ["AWS4-HMAC-SHA256"]
        assert query["X-Amz-Signature"]
        assert query["X-Amz-Expires"] == [
            str(int(storage.LINK_VALID_FOR.total_seconds()))]

    def test_link_is_stable_within_a_window(self):
        later = NOW + timedelta(hours=1)
        assert get_image_url("abc.jpeg", now=NOW) == \
            get_image_url("abc.jpeg", now=later)

    def test_link_changes_in_the_next_window(self):
        next_window = NOW + storage.LINK_WINDOW
        assert get_image_url("abc.jpeg", now=NOW) != \
            get_image_url("abc.jpeg", now=next_window)

    def test_link_is_dated_to_the_window_start(self):
        query = parse_qs(urlsplit(get_image_url("abc.jpeg", now=NOW)).query)
        assert query["X-Amz-Date"] == ["20261108T060000Z"]

    def test_every_link_lasts_at_least_a_day(self):
        assert storage.LINK_VALID_FOR - storage.LINK_WINDOW >= \
            timedelta(hours=24)


class TestSignedLinksAgainstMinio:
    """Needs the disposable test MinIO; skipped when it isn't running."""

    @pytest.fixture
    def stored_object(self, minio_test_bucket):
        key = f"test-{uuid.uuid4()}.jpeg"
        body = b"\xff\xd8 not really a jpeg " * 50
        upload_image_to_storage(key, io.BytesIO(body), len(body))
        yield key, body
        minio_client.remove_object(BUCKET_NAME, key)

    def test_signed_link_downloads_the_object(self, stored_object):
        key, body = stored_object
        resp = requests.get(get_image_url(key), timeout=10)
        assert resp.status_code == 200
        assert resp.content == body

    def test_signed_link_serves_ranges_for_video_seeking(self,
                                                         stored_object):
        key, body = stored_object
        resp = requests.get(get_image_url(key),
                            headers={"Range": "bytes=0-9"}, timeout=10)
        assert resp.status_code == 206
        assert resp.content == body[:10]

    def test_unsigned_link_is_refused(self, stored_object):
        key, _ = stored_object
        resp = requests.get(f"http://{EXTERNAL_URL_HOST}/{BUCKET_NAME}/{key}",
                            timeout=10)
        assert resp.status_code == 403

    def test_tampered_link_is_refused(self, stored_object):
        key, _ = stored_object
        other = get_image_url(key).replace(key, "someone-else.jpeg")
        assert requests.get(other, timeout=10).status_code == 403
