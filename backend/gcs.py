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
