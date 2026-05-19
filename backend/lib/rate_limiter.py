"""lib/rate_limiter.py — Per-user daily rate limiting for Saucer agent endpoints.

Limits are read from Firestore config/limits (same document as task_queue.py).
Counters live at users/{user_id}/counters/{counter_name}.

Default limits (configurable via config/limits):
  max_agent_calls_per_user_per_day:  20
  max_voice_calls_per_user_per_day:  30

Uses the same transactional counter pattern as task_queue.py to prevent races.
Fails open on transaction errors — a broken counter should not block agent use.
"""

import sys
from datetime import datetime, timezone

from google.cloud import firestore as _firestore

from lib.firestore_client import get_db


def _read_limit(key: str, default: int) -> int:
    """Read a configurable limit from config/limits. Returns default if not set."""
    try:
        db = get_db()
        doc = db.collection('config').document('limits').get()
        if doc.exists:
            return int(doc.to_dict().get(key, default))
    except Exception as e:
        print(f'[rate_limiter] config/limits read error: {e}', file=sys.stderr)
    return default


def check_and_increment(user_id: str, counter_name: str, limit_key: str, default_limit: int) -> dict:
    """Atomically check and increment a per-user daily counter.

    Returns {'allowed': True} if the action is within the daily limit.
    Returns {'allowed': False, 'reason': str} if the limit has been reached.

    Fails open on any Firestore error (logs and returns allowed=True) so that
    infra issues do not silently block the user.

    Args:
        user_id:       User email used as the Firestore namespace key.
        counter_name:  Name of the counter document (e.g. 'daily_agent_calls').
        limit_key:     Key in config/limits document (e.g. 'max_agent_calls_per_user_per_day').
        default_limit: Default cap if the config document does not specify the key.
    """
    limit = _read_limit(limit_key, default_limit)
    today_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    db = get_db()
    counter_ref = (
        db.collection('users')
        .document(user_id)
        .collection('counters')
        .document(counter_name)
    )

    @_firestore.transactional
    def _run_transaction(transaction, ref):
        snap = ref.get(transaction=transaction)
        if snap.exists:
            data = snap.to_dict()
            count = data.get('count', 0) if data.get('reset_date') == today_str else 0
        else:
            count = 0

        if count >= limit:
            return False

        transaction.set(ref, {'count': count + 1, 'reset_date': today_str})
        return True

    try:
        transaction = db.transaction()
        allowed = _run_transaction(transaction, counter_ref)
        if allowed:
            return {'allowed': True}
        return {
            'allowed': False,
            'reason': f'Daily limit of {limit} {counter_name} reached. Resets tomorrow.',
        }
    except Exception as e:
        print(
            f'[rate_limiter] transaction failed for user={user_id} counter={counter_name}: {e}',
            file=sys.stderr,
        )
        # Fail open — infra issue should not block the user.
        return {'allowed': True}
