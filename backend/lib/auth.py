from flask import jsonify
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from lib.config import _CLOUD_RUN_URL


def verify_cloud_tasks_token(req):
    """Verify the OIDC bearer token Cloud Tasks sends on every request.

    Returns None on success. Returns a (response, status_code) tuple on failure
    so callers can do: err = verify_cloud_tasks_token(request); if err: return err
    """
    auth_header = req.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return jsonify({'error': 'Unauthorized'}), 403

    token = auth_header.split('Bearer ', 1)[1]
    try:
        request_adapter = google_requests.Request()
        # verify_oauth2_token handles OIDC tokens from service accounts
        # (what Cloud Tasks uses), unlike verify_firebase_token which is
        # for Firebase user ID tokens.
        google_id_token.verify_oauth2_token(
            token, request_adapter, audience=_CLOUD_RUN_URL
        )
    except Exception as e:
        print(f'[auth] OIDC verification failed: {e}')
        return jsonify({'error': 'Unauthorized'}), 403

    return None
