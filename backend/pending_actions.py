"""pending_actions.py — Firestore-backed queue for actions Hana wants to take.

Each document in users/{user_id}/pending_actions/{action_id} represents one
action that Hana has proposed or is executing.

Collection path: users/{user_id}/pending_actions/{action_id}
  — Multi-user namespaced per the zero-exception Sprint 4 constraint.

Status lifecycle (user-facing resolution):
  pending → approved | rejected | expired

processing_status lifecycle (Cloud Tasks execution tracking):
  pending → in_progress → complete | failed

The processing_status field is set by:
  - enqueue_pending_action():   sets 'pending'
  - update_processing_status(): transitions to in_progress / complete / failed
    (called by the POST /tasks/handle-action handler)
"""

import sys
from datetime import datetime, timezone
from typing import Optional

from google.cloud import firestore as _firestore

_PROJECT = 'mediationmate'

_VALID_PROCESSING_STATUSES = frozenset({'pending', 'in_progress', 'complete', 'failed'})
_VALID_RESOLUTIONS = frozenset({'approved', 'rejected', 'expired'})


def _get_db() -> _firestore.Client:
    return _firestore.Client(project=_PROJECT)


def _collection_ref(db: _firestore.Client, user_id: str):
    """Return the pending_actions CollectionReference for the given user."""
    return db.collection('users').document(user_id).collection('pending_actions')


def enqueue_pending_action(
    user_id: str,
    action_type: str,
    payload: dict,
    confidence: Optional[float] = None,
    email_id: Optional[str] = None,
    user_email: Optional[str] = None,
) -> str:
    """Create a new pending_actions document and return its ID.

    Args:
        user_id:     The user's email address (used as the Firestore namespace key).
        action_type: Machine-readable action type (e.g. 'gmail_draft', 'task_add').
        payload:     Action-specific data (e.g. draft_id, to, subject, body_preview).
        confidence:  Optional 0.0–1.0 confidence score from Hana's decision.
        email_id:    Source email ID if this action was triggered by an email.
        user_email:  Email of the household user (usually same as user_id).

    Returns:
        The new Firestore document ID.
    """
    db = _get_db()
    doc_data: dict = {
        'action_type': action_type,
        'payload': payload,
        'status': 'pending',
        'processing_status': 'pending',
        'created_at': datetime.now(timezone.utc),
        'user_id': user_id,
    }
    if confidence is not None:
        doc_data['confidence'] = confidence
    if email_id is not None:
        doc_data['email_id'] = email_id
    if user_email is not None:
        doc_data['user_email'] = user_email

    _, ref = _collection_ref(db, user_id).add(doc_data)
    return ref.id


def update_processing_status(
    user_id: str,
    action_id: str,
    status: str,
) -> bool:
    """Update the processing_status field on a pending_actions document.

    Called by the Cloud Tasks handler to track execution state.

    Args:
        user_id:   The user namespace.
        action_id: Firestore document ID.
        status:    One of 'pending', 'in_progress', 'complete', 'failed'.

    Returns:
        True on success, False if the document was not found.

    Raises:
        ValueError if status is not a valid processing status.
    """
    if status not in _VALID_PROCESSING_STATUSES:
        raise ValueError(
            f"processing_status must be one of {sorted(_VALID_PROCESSING_STATUSES)}; "
            f"got {status!r}"
        )
    db = _get_db()
    ref = _collection_ref(db, user_id).document(action_id)
    snap = ref.get()
    if not snap.exists:
        print(
            f'[pending_actions] update_processing_status: doc not found '
            f'user_id={user_id} action_id={action_id}',
            file=sys.stderr,
        )
        return False
    update_data = {
        'processing_status': status,
        'processing_updated_at': datetime.now(timezone.utc),
    }
    if status == 'complete':
        update_data['completed_at'] = datetime.now(timezone.utc)
    elif status == 'failed':
        update_data['failed_at'] = datetime.now(timezone.utc)
    ref.update(update_data)
    return True


def resolve_pending_action(
    user_id: str,
    action_id: str,
    resolution: str,
    resolved_by: str = 'user',
) -> bool:
    """Mark a pending action as approved, rejected, or expired.

    This is the user-facing resolution path — separate from processing_status.

    Args:
        user_id:     The user namespace.
        action_id:   Firestore document ID.
        resolution:  One of 'approved', 'rejected', 'expired'.
        resolved_by: Who resolved it (default 'user').

    Returns:
        True on success, False if the document was not found.
    """
    if resolution not in _VALID_RESOLUTIONS:
        raise ValueError(
            f"resolution must be one of {sorted(_VALID_RESOLUTIONS)}; got {resolution!r}"
        )
    db = _get_db()
    ref = _collection_ref(db, user_id).document(action_id)
    snap = ref.get()
    if not snap.exists:
        return False
    ref.update({
        'status': resolution,
        'resolved_at': datetime.now(timezone.utc),
        'resolved_by': resolved_by,
    })
    return True


def get_pending_action(user_id: str, action_id: str) -> Optional[dict]:
    """Fetch a single pending_actions document by user_id and action_id.

    Returns the document as a dict with an 'id' field added, or None if
    not found.
    """
    db = _get_db()
    snap = _collection_ref(db, user_id).document(action_id).get()
    if not snap.exists:
        return None
    data = snap.to_dict()
    data['id'] = snap.id
    return data


def list_pending_actions(
    user_id: str,
    status: str = 'pending',
    limit: int = 50,
) -> list:
    """Return pending_actions documents for the given user matching the given status.

    Results are ordered by created_at descending (newest first).

    Args:
        user_id: The user namespace.
        status:  Filter by status field (default 'pending').
        limit:   Maximum number of results to return (default 50).

    Returns:
        List of dicts, each with 'id' added from the document ID.
    """
    db = _get_db()
    query = (
        _collection_ref(db, user_id)
        .where('status', '==', status)
        .order_by('created_at', direction=_firestore.Query.DESCENDING)
        .limit(limit)
    )
    results = []
    for snap in query.stream():
        data = snap.to_dict()
        data['id'] = snap.id
        results.append(data)
    return results
