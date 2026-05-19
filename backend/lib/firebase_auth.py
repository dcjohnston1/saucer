"""lib/firebase_auth.py — Firebase Auth JWT verification helper for Saucer.

Sprint 13: infrastructure-only. The verify_firebase_token() helper and the
@firebase_auth_required decorator are wired and ready, but no existing route
uses them yet. Mobile-specific routes will apply @firebase_auth_required
starting Sprint 14 when the mobile client is built.

Hard enforcement (returning 401 on missing/invalid token for existing routes)
ships with the mobile client — not before.
"""

import os
import tempfile
from functools import wraps

from flask import request, jsonify


def _get_firebase_app():
    """Initialize and return the Firebase Admin app (idempotent)."""
    import firebase_admin
    if not firebase_admin._apps:
        from firebase_admin import credentials
        creds_json = os.environ.get('GOOGLE_CREDENTIALS_JSON')
        if creds_json:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                f.write(creds_json)
                creds_path = f.name
            cred = credentials.Certificate(creds_path)
        else:
            cred = credentials.ApplicationDefault()
        firebase_admin.initialize_app(cred)
    return firebase_admin.get_app()


def verify_firebase_token(req):
    """Verify a Firebase Auth ID token from the Authorization header.

    Returns (user_id: str, None) on success.
    Returns (None, (response, status_code)) on failure.

    The token must be a Firebase ID token issued by Firebase Auth for this
    project. It is NOT an OIDC token from Cloud Tasks — that uses
    lib/auth.py:verify_cloud_tasks_token() instead.
    """
    auth_header = req.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return None, (jsonify({'error': 'Missing or malformed Authorization header'}), 401)
    id_token = auth_header.split('Bearer ', 1)[1].strip()
    try:
        import firebase_admin.auth as firebase_auth_sdk
        _get_firebase_app()
        decoded = firebase_auth_sdk.verify_id_token(id_token)
        return decoded['uid'], None
    except Exception as e:
        return None, (jsonify({'error': f'Invalid Firebase token: {e}'}), 401)


def firebase_auth_required(f):
    """Flask route decorator: require a valid Firebase Auth ID token.

    On success, passes user_id as a keyword argument to the route function.
    On failure, returns 401 JSON.

    Usage:
        @some_bp.route('/mobile/resource', methods=['GET'])
        @firebase_auth_required
        def get_resource(user_id):
            ...
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        user_id, err = verify_firebase_token(request)
        if err:
            return err
        return f(*args, user_id=user_id, **kwargs)
    return decorated
