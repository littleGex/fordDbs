import os
from minio import Minio
from minio.error import S3Error
from datetime import timedelta

# 1. INTERNAL connection (Docker to Docker)
# Using the service name from your docker-compose
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "admin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "password")

# 2. EXTERNAL address (What family phones will use)
EXTERNAL_URL_HOST = os.getenv("EXTERNAL_URL_HOST",
                              "ford-home-pi.local:9000")
BUCKET_NAME = "family-photos"


# Initialize using the INTERNAL Docker network
minio_client = Minio(
    MINIO_ENDPOINT,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=False
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
                            file_size: int,
                            content_type: str = "image/jpeg"):
    """Uploads file over the fast, internal Docker network."""
    try:
        minio_client.put_object(
            bucket_name=BUCKET_NAME,
            object_name=file_name,
            data=file_stream,
            length=file_size,
            content_type=content_type
        )
        return file_name
    except S3Error as err:
        print(f"❌ MinIO Error uploading {file_name}: {err}")
        raise err


def get_image_url(key: str):
    if not key:
        return None
    # Return a direct public link instead of a signed one
    return f"http://{EXTERNAL_URL_HOST}/{BUCKET_NAME}/{key}"


def get_image_url_old(file_name: str,
                  expires_in_hours: int = 2):
    """Generates a secure link for the frontend."""
    try:
        # MinIO generates a link using its own internal endpoint
        # (minio:9000)
        url = minio_client.get_presigned_url(
            "GET",
            BUCKET_NAME,
            file_name,
            expires=timedelta(hours=expires_in_hours),
        )

        # We swap the internal Docker name for the external Pi address
        # so the family's web browser can actually load the image.
        if MINIO_ENDPOINT in url:
            url = url.replace(MINIO_ENDPOINT, EXTERNAL_URL_HOST)

        return url
    except S3Error as err:
        print(f"❌ MinIO Error generating URL for {file_name}: {err}")
        return None
