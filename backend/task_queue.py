"""task_queue.py — Cloud Tasks enqueue helper for Saucer / Hana.

Provides enqueue_action(user_id, action) which:
  1. Reads min_confidence_threshold from config/limits (default 0.7).
     Refuses to enqueue if action.confidence is below the threshold.
  2. Reads max_tasks_per_user_per_day from config/limits (default 30).
     Checks and increments users/{user_id}/counters/daily_tasks.
     Refuses if the daily cap is reached.
  3. Creates a Cloud Tasks task targeting POST /tasks/handle-action on
     the Cloud Run service, authenticated via OIDC token.
  4. Returns True on success, False on any rejection or error.

Queue: hana-actions (us-central1, project mediationmate)
Retry config is set on the queue itself: max_attempts=3, min_backoff=10s,
max_backoff=300s, max_doublings=3.
"""

import json
import os
import sys
from datetime import datetime, timezone

from google.cloud import firestore as _firestore
from google.cloud import tasks_v2

_PROJECT = 'mediationmate'
_LOCATION = 'us-central1'
_QUEUE = 'hana-actions'
_HANDLER_PATH = '/tasks/handle-action'

# Cloud Run service URL — read from env so it works in all environments.
# Must be set on the Cloud Run service. Example:
#   CLOUD_RUN_URL=https://saucer-backend-987132498395.us-central1.run.app
_CLOUD_RUN_URL = os.environ.get(
    'CLOUD_RUN_URL',
    'https://saucer-backend-987132498395.us-central1.run.app',
)

# Service account that Cloud Tasks uses to generate OIDC tokens when calling
# the Cloud Run service. Must have roles/run.invoker on the Cloud Run service.
_SERVICE_ACCOUNT_EMAIL = os.environ.get(
    'CLOUD_TASKS_SERVICE_ACCOUNT',
    'saucer-doc-service@mediationmate.iam.gserviceaccount.com',
)

_DEFAULT_MIN_CONFIDENCE = 0.7
_DEFAULT_MAX_DAILY_TASKS = 30


def _get_db() -> _firestore.Client:
    return _firestore.Client(project=_PROJECT)


def _read_config_limits(db: _firestore.Client) -> dict:
    """Read the config/limits document. Returns empty dict if not present."""
    try:
        doc = db.collection('config').document('limits').get()
        return doc.to_dict() or {} if doc.exists else {}
    except Exception as e:
        print(f'[task_queue] config/limits read error: {e}', file=sys.stderr)
        return {}


def _check_and_increment_daily_counter(
    db: _firestore.Client,
    user_id: str,
    cap: int,
) -> bool:
    """Atomically check and increment users/{user_id}/counters/daily_tasks.

    Returns True if the counter was incremented (action is allowed).
    Returns False if the cap has been reached for today.

    Resets the counter when reset_date differs from today's date.
    Uses a Firestore transaction to prevent race conditions.
    """
    today_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    counter_ref = (
        db.collection('users')
        .document(user_id)
        .collection('counters')
        .document('daily_tasks')
    )

    @_firestore.transactional
    def _run_transaction(transaction, ref):
        snap = ref.get(transaction=transaction)
        if snap.exists:
            data = snap.to_dict()
            stored_date = data.get('reset_date', '')
            count = data.get('count', 0)
            if stored_date != today_str:
                # New day — reset counter
                count = 0
        else:
            count = 0

        if count >= cap:
            return False  # cap reached

        transaction.set(ref, {
            'count': count + 1,
            'reset_date': today_str,
        })
        return True

    try:
        transaction = db.transaction()
        return _run_transaction(transaction, counter_ref)
    except Exception as e:
        print(
            f'[task_queue] daily counter transaction failed for user={user_id}: {e}',
            file=sys.stderr,
        )
        # Fail open — if we can't read the counter, log and allow rather than
        # silently dropping the action. This is a deliberate choice: a broken
        # counter should not stop all proactive work. If you prefer fail-closed,
        # change this to return False.
        return True


def enqueue_action(user_id: str, action) -> bool:
    """Enqueue a Hana action into Cloud Tasks.

    Args:
        user_id: The user's email address (used as the Firestore namespace key
                 and included in the Cloud Tasks payload).
        action:  An object with at minimum:
                   - action_id (str): the Firestore pending_actions doc ID
                   - confidence (float | None): Hana's confidence score (0.0–1.0)
                   - action_type (str): machine-readable action type

    Returns:
        True  — task successfully enqueued.
        False — rejected (low confidence, daily cap reached) or error.
    """
    db = _get_db()
    limits = _read_config_limits(db)

    # ── Gate 1: confidence threshold ─────────────────────────────────────────
    min_confidence = limits.get('min_confidence_threshold', _DEFAULT_MIN_CONFIDENCE)
    action_confidence = getattr(action, 'confidence', None)

    if action_confidence is None:
        print(
            f'[task_queue] REJECTED user={user_id} action_id={getattr(action, "action_id", "?")} '
            f'reason=no_confidence_score (threshold={min_confidence})',
            file=sys.stderr,
        )
        return False

    if action_confidence < min_confidence:
        print(
            f'[task_queue] REJECTED user={user_id} action_id={getattr(action, "action_id", "?")} '
            f'reason=below_confidence_threshold '
            f'confidence={action_confidence} threshold={min_confidence}',
            file=sys.stderr,
        )
        return False

    # ── Gate 2: per-user daily cap ────────────────────────────────────────────
    daily_cap = int(limits.get('max_tasks_per_user_per_day', _DEFAULT_MAX_DAILY_TASKS))
    allowed = _check_and_increment_daily_counter(db, user_id, daily_cap)
    if not allowed:
        print(
            f'[task_queue] REJECTED user={user_id} action_id={getattr(action, "action_id", "?")} '
            f'reason=daily_cap_reached cap={daily_cap}',
            file=sys.stderr,
        )
        return False

    # ── Enqueue into Cloud Tasks ──────────────────────────────────────────────
    action_id = getattr(action, 'action_id', None)
    if not action_id:
        print(
            f'[task_queue] ERROR user={user_id} reason=missing_action_id',
            file=sys.stderr,
        )
        return False

    payload = {
        'user_id': user_id,
        'action_id': action_id,
    }
    handler_url = _CLOUD_RUN_URL.rstrip('/') + _HANDLER_PATH

    task = {
        'http_request': {
            'http_method': tasks_v2.HttpMethod.POST,
            'url': handler_url,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps(payload).encode('utf-8'),
            'oidc_token': {
                'service_account_email': _SERVICE_ACCOUNT_EMAIL,
                'audience': _CLOUD_RUN_URL,
            },
        }
    }

    try:
        client = tasks_v2.CloudTasksClient()
        queue_path = client.queue_path(_PROJECT, _LOCATION, _QUEUE)
        response = client.create_task(
            request={'parent': queue_path, 'task': task}
        )
        print(
            f'[task_queue] ENQUEUED user={user_id} action_id={action_id} '
            f'action_type={getattr(action, "action_type", "unknown")} '
            f'task_name={response.name}',
            file=sys.stderr,
        )
        return True
    except Exception as e:
        print(
            f'[task_queue] ERROR enqueue failed user={user_id} action_id={action_id}: {e}',
            file=sys.stderr,
        )
        return False
