import json
import os
from google.cloud import storage

BUCKET_NAME = os.environ.get('GCS_BUCKET', 'saucer-data-mediationmate')


def _bucket():
    return storage.Client().bucket(BUCKET_NAME)


def read_json(filename, default=None):
    try:
        blob = _bucket().blob(filename)
        if not blob.exists():
            return default
        return json.loads(blob.download_as_text())
    except Exception as e:
        print(f"GCS read error ({filename}): {e}")
        return default


def write_json(filename, data):
    try:
        blob = _bucket().blob(filename)
        blob.upload_from_string(json.dumps(data), content_type='application/json')
    except Exception as e:
        print(f"GCS write error ({filename}): {e}")


def upload_file(file_bytes: bytes, gcs_path: str, content_type: str = 'application/octet-stream') -> bool:
    try:
        blob = _bucket().blob(gcs_path)
        blob.upload_from_string(file_bytes, content_type=content_type)
        return True
    except Exception as e:
        print(f"GCS upload error ({gcs_path}): {e}")
        return False


def delete_file(gcs_path: str) -> bool:
    try:
        blob = _bucket().blob(gcs_path)
        blob.delete()
        return True
    except Exception as e:
        print(f"GCS delete error ({gcs_path}): {e}")
        return False


def download_file(gcs_path: str) -> tuple:
    """Return (file_bytes, content_type) or (None, None) on error."""
    try:
        blob = _bucket().blob(gcs_path)
        content_type = blob.content_type or 'application/octet-stream'
        return blob.download_as_bytes(), content_type
    except Exception as e:
        print(f"GCS download error ({gcs_path}): {e}")
        return None, None


def upload_avatar(email: str, image_bytes: bytes, content_type: str = 'image/jpeg') -> str | None:
    import hashlib
    path = f"avatars/{hashlib.md5(email.encode()).hexdigest()}.jpg"
    try:
        blob = _bucket().blob(path)
        blob.upload_from_string(image_bytes, content_type=content_type)
        return path
    except Exception as e:
        print(f"Avatar upload error: {e}")
        return None


def get_avatar(email: str) -> tuple:
    import hashlib
    path = f"avatars/{hashlib.md5(email.encode()).hexdigest()}.jpg"
    return download_file(path)


def generate_signed_url(gcs_path: str, expiry_minutes: int = 15):
    """Generate a V4 signed URL using workload identity credentials (Cloud Run compatible)."""
    try:
        import datetime
        import google.auth
        from google.auth.transport import requests as _req
        creds, _ = google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
        if hasattr(creds, 'refresh'):
            creds.refresh(_req.Request())
        blob = _bucket().blob(gcs_path)
        url = blob.generate_signed_url(
            version='v4',
            expiration=datetime.timedelta(minutes=expiry_minutes),
            method='GET',
            service_account_email=getattr(creds, 'service_account_email', None),
            access_token=getattr(creds, 'token', None),
        )
        return url
    except Exception as e:
        print(f"GCS signed URL error ({gcs_path}): {e}")
        return None
