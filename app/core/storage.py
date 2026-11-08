import os
from minio import Minio
from minio.error import S3Error
from datetime import datetime, timedelta, timezone

# 1. INTERNAL connection (Docker to Docker)
# Using the service name from your docker-compose
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "admin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "password")

# 2. EXTERNAL address (What family phones will use)
EXTERNAL_URL_HOST = os.getenv("EXTERNAL_URL_HOST",
                              "ford-home-pi.local:9000")
EXTERNAL_URL_SECURE = os.getenv("EXTERNAL_URL_SECURE",
                                "true").lower() != "false"
BUCKET_NAME = "family-photos"

# Signed links are dated to the start of a fixed window, so a photo has
# the same link for the whole window and browsers can cache it. Each
# link stays valid for between LINK_VALID_FOR - LINK_WINDOW (24 h) and
# LINK_VALID_FOR (30 h) after it is handed out.
LINK_WINDOW = timedelta(hours=6)
LINK_VALID_FOR = timedelta(hours=30)


# Initialize using the INTERNAL Docker network
minio_client = Minio(
    MINIO_ENDPOINT,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=False
)

# Only signs links, never connects: the host is part of the signature,
# so links must be signed for the address phones use, not minio:9000.
# Setting the region stops the SDK from asking the server for it.
_link_signer = Minio(
    EXTERNAL_URL_HOST,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=EXTERNAL_URL_SECURE,
    region="us-east-1",
)


def init_storage():
    """Ensure bucket exists on startup."""
    try:
        if not minio_client.bucket_exists(BUCKET_NAME):
            minio_client.make_bucket(BUCKET_NAME)
            print(f"✅ MinIO: Bucket '{BUCKET_NAME}' "
                  "created successfully.")
        else:
            print(f"✅ MinIO: Bucket '{BUCKET_NAME}' "
                  "already exists.")
    except S3Error as err:
        print(f"❌ MinIO Error initializing bucket: {err}")


def upload_image_to_storage(file_name: str,
                            file_stream,
                            file_size: int = -1,
                            content_type: str = "image/jpeg"):

    minio_client.put_object(
        bucket_name=BUCKET_NAME,
        object_name=file_name,
        data=file_stream,
        length=file_size,
        part_size=10 * 1024 * 1024,
        content_type=content_type
    )


def get_image_url(key: str, now: datetime = None):
    """A signed, expiring link to a photo or video for the frontend."""
    if not key:
        return None
    now = now or datetime.now(timezone.utc)
    window = int(now.timestamp() // LINK_WINDOW.total_seconds())
    signed_at = datetime.fromtimestamp(
        window * LINK_WINDOW.total_seconds(), timezone.utc)
    return _link_signer.presigned_get_object(
        BUCKET_NAME, key, expires=LINK_VALID_FOR, request_date=signed_at)
