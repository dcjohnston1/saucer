import traceback as _tb

from flask import Blueprint, request, jsonify

import email_store
import pending_actions
from lib.auth import verify_cloud_tasks_token
from lib.config import _DAN

tasks_bp = Blueprint('tasks', __name__)


@tasks_bp.route('/pending-actions', methods=['GET'])
def get_pending_actions():
    """Return pending actions filtered by status (default: 'pending').

    Query params:
      status   — 'pending' | 'approved' | 'rejected' | 'expired' (default: 'pending')
      user_id  — user email namespace (default: dcjohnston1@gmail.com)
    """
    status = request.args.get('status', 'pending')
    user_id = request.args.get('user_id', _DAN)
    results = pending_actions.list_pending_actions(user_id=user_id, status=status)
    return jsonify({'pending_actions': results})


@tasks_bp.route('/pending-actions/<path:action_id>/resolve', methods=['POST'])
def resolve_pending_action(action_id):
    """Approve, reject, or expire a pending action.

    Body fields:
      resolution  — 'approved' | 'rejected' | 'expired'
      resolved_by — who resolved it (default: 'user')
      user_id     — user email namespace (default: dcjohnston1@gmail.com)
    """
    data = request.get_json() or {}
    resolution = data.get('resolution')
    if not resolution:
        return jsonify({'error': 'Missing resolution'}), 400
    if resolution not in ('approved', 'rejected', 'expired'):
        return jsonify({'error': "resolution must be 'approved', 'rejected', or 'expired'"}), 400
    resolved_by = data.get('resolved_by', 'user')
    user_id = data.get('user_id', _DAN)
    success = pending_actions.resolve_pending_action(user_id, action_id, resolution, resolved_by)
    if not success:
        return jsonify({'error': 'Action not found'}), 404
    return jsonify({'status': 'ok'})


@tasks_bp.route('/tasks/handle-action', methods=['POST'])
def handle_action():
    """Cloud Tasks handler — executes a single pending Hana action.

    Called by Cloud Tasks (not by humans). Secured with OIDC token verification.
    Idempotent: if the action is already in_progress or complete, returns 200
    immediately without re-executing.

    Expected JSON body: {"user_id": "...", "action_id": "..."}

    On success: sets processing_status = 'complete', returns 200.
    On failure: sets processing_status = 'failed', returns 500 (triggers retry).
    """
    err = verify_cloud_tasks_token(request)
    if err:
        print('[handle-action] REJECTED: OIDC verification failed')
        return err

    data = request.get_json(force=True) or {}
    user_id = data.get('user_id', '').strip()
    action_id = data.get('action_id', '').strip()

    if not user_id or not action_id:
        print(f'[handle-action] ERROR: missing user_id or action_id in payload: {data}')
        return jsonify({'error': 'Missing user_id or action_id'}), 400

    action_doc = pending_actions.get_pending_action(user_id, action_id)
    if not action_doc:
        print(f'[handle-action] ERROR: action not found user_id={user_id} action_id={action_id}')
        # Return 200 so Cloud Tasks does not retry a permanently missing document.
        return jsonify({'status': 'not_found'}), 200

    processing_status = action_doc.get('processing_status', 'pending')
    if processing_status in ('in_progress', 'complete'):
        print(
            f'[handle-action] IDEMPOTENT SKIP user_id={user_id} action_id={action_id} '
            f'processing_status={processing_status}'
        )
        return jsonify({'status': 'already_' + processing_status}), 200

    pending_actions.update_processing_status(user_id, action_id, 'in_progress')

    action_type = action_doc.get('action_type', '')
    payload = action_doc.get('payload', {})

    print(f'[handle-action] EXECUTING user_id={user_id} action_id={action_id} action_type={action_type}')

    try:
        if action_type == 'gmail_draft':
            # The draft was already created synchronously in the agent session.
            # This handler records the successful execution and marks it complete.
            # Future action types (task_add, SMS, etc.) will execute here.
            draft_id = payload.get('draft_id')
            print(f'[handle-action] gmail_draft acknowledged draft_id={draft_id}')
            # No additional work needed — draft was created during agent run.

        else:
            print(f'[handle-action] WARNING: unknown action_type={action_type!r} — marking complete')

        pending_actions.update_processing_status(user_id, action_id, 'complete')
        print(f'[handle-action] COMPLETE user_id={user_id} action_id={action_id}')
        return jsonify({'status': 'complete'}), 200

    except Exception as e:
        err_msg = _tb.format_exc()
        print(f'[handle-action] FAILED user_id={user_id} action_id={action_id}: {err_msg}')
        try:
            pending_actions.update_processing_status(user_id, action_id, 'failed')
        except Exception as status_err:
            print(f'[handle-action] ERROR updating failed status: {status_err}')
        # Return 500 so Cloud Tasks retries according to queue retry config.
        return jsonify({'error': str(e)}), 500


@tasks_bp.route('/tasks/process-email', methods=['POST'])
def process_email_task():
    """Cloud Tasks handler — runs process_single_email for one qualifying email.

    Called by Cloud Tasks after the Pub/Sub webhook enqueues the task.
    Secured with OIDC token verification (same as handle-action).

    Expected JSON body: {"email_id": "...", "email_address": "..."}

    Returns 200 on success, 500 on failure (triggers Cloud Tasks retry).
    """
    err = verify_cloud_tasks_token(request)
    if err:
        print('[process-email] REJECTED: OIDC verification failed')
        return err

    data = request.get_json(force=True) or {}
    email_id = data.get('email_id', '').strip()
    email_address = data.get('email_address', '').strip()

    if not email_id:
        print(f'[process-email] ERROR: missing email_id in payload: {data}')
        return jsonify({'error': 'Missing email_id'}), 400

    print(f'[process-email] EXECUTING email_id={email_id} email_address={email_address}')

    try:
        email = email_store.get_email(email_id)
        if not email:
            print(f'[process-email] email not found in store: {email_id}')
            # Return 200 so Cloud Tasks does not retry a permanently missing email.
            return jsonify({'status': 'not_found'}), 200

        from agent import process_single_email
        briefing_id = process_single_email(email)
        print(f'[process-email] COMPLETE email_id={email_id} briefing_id={briefing_id}')
        return jsonify({'status': 'complete', 'briefing_id': briefing_id}), 200

    except Exception as e:
        print(f'[process-email] FAILED email_id={email_id}: {_tb.format_exc()}')
        # Return 500 so Cloud Tasks retries.
        return jsonify({'error': str(e)}), 500
