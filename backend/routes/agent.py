import os

from flask import Blueprint, request, jsonify
from google.cloud import firestore

import email_store
from lib.config import (
    _DAN,
    _EMILY,
    _PROJECT,
    _LOCATION,
    _QUEUE,
    _CLOUD_RUN_URL,
    _SA_EMAIL,
    _PUBSUB_TOPIC,
)
from lib.email_helpers import (
    _extract_sender_addr,
    _get_email_intent,
    _auto_save_pdf_attachments,
    _strip_raw_bytes,
)
from lib.firestore_client import get_db
from lib.rate_limiter import check_and_increment

agent_bp = Blueprint('agent', __name__)


@agent_bp.route('/agent/run', methods=['POST'])
def agent_run():
    agent_key = os.environ.get('AGENT_KEY', '')
    provided_key = request.headers.get('X-Agent-Key', '')
    if not agent_key or provided_key != agent_key:
        return jsonify({'error': 'Unauthorized'}), 401

    # Per-user rate limit: max_agent_calls_per_user_per_day (default 20)
    data = request.get_json(force=True, silent=True) or {}
    user_id = data.get('user', _DAN)
    rl = check_and_increment(user_id, 'daily_agent_calls', 'max_agent_calls_per_user_per_day', 20)
    if not rl['allowed']:
        return jsonify({'error': rl['reason']}), 429

    try:
        from agent import run_morning_agent
        briefing_id = run_morning_agent()
        return jsonify({'status': 'ok', 'briefing_id': briefing_id})
    except Exception as e:
        import traceback
        print(f'[main] agent_run error: {traceback.format_exc()}')
        return jsonify({'error': str(e)}), 500


@agent_bp.route('/briefing/latest', methods=['GET'])
def get_latest_briefing():
    from datetime import datetime, timezone
    user_email = request.args.get('user_email', '')
    if not user_email:
        return jsonify({'error': 'Missing user_email'}), 400

    db = get_db()
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')

    q = db.collection('morning_briefings').order_by(
        'timestamp', direction=firestore.Query.DESCENDING
    ).limit(1)

    briefing = None
    for doc in q.stream():
        d = doc.to_dict()
        d['_doc_id'] = doc.id
        briefing = d
        break

    if not briefing or briefing.get('date') != today:
        return jsonify({'briefing': None})

    is_dan = user_email == _DAN
    message_key = 'dan_message' if is_dan else 'emily_message'
    seen_key = 'dan_seen' if is_dan else 'emily_seen'

    return jsonify({
        'briefing': {
            'id': briefing['_doc_id'],
            'date': briefing.get('date'),
            'message': briefing.get(message_key, ''),
            'seen': briefing.get(seen_key, False),
            'tasks_added': briefing.get('tasks_added', 0),
            'emails_processed': briefing.get('emails_processed', 0),
        }
    })


@agent_bp.route('/briefing/<briefing_id>/feedback', methods=['POST'])
def briefing_feedback(briefing_id):
    from datetime import datetime, timezone
    data = request.get_json(force=True) or {}
    user_email = data.get('user_email', '')
    rating = data.get('rating', '')
    if not user_email or rating not in ('positive', 'negative'):
        return jsonify({'error': 'Missing or invalid user_email / rating'}), 400

    is_dan = user_email == _DAN
    rating_field = 'dan_rating' if is_dan else 'emily_rating'
    seen_field = 'dan_seen' if is_dan else 'emily_seen'

    db = get_db()
    briefing_ref = db.collection('morning_briefings').document(briefing_id)
    briefing_ref.update({rating_field: rating, seen_field: True})

    # Link rating to any Gemini decisions made in this briefing
    briefing_doc = briefing_ref.get()
    if briefing_doc.exists:
        decision_ids = briefing_doc.to_dict().get('decisions_made', [])
        for dec_id in decision_ids:
            try:
                db.collection('gemini_decisions').document(dec_id).update({
                    'user_feedback': rating,
                    'feedback_at': datetime.now(timezone.utc),
                    'feedback_by': user_email,
                })
            except Exception as e:
                print(f"[briefing_feedback] decision update failed {dec_id}: {e}")

    return jsonify({'ok': True})


@agent_bp.route('/briefing/<briefing_id>/seen', methods=['POST'])
def mark_briefing_seen(briefing_id):
    data = request.get_json(force=True) or {}
    user_email = data.get('user_email', '')
    if not user_email:
        return jsonify({'error': 'Missing user_email'}), 400
    is_dan = user_email == _DAN
    seen_field = 'dan_seen' if is_dan else 'emily_seen'
    db = get_db()
    db.collection('morning_briefings').document(briefing_id).update({seen_field: True})
    return jsonify({'ok': True})


@agent_bp.route('/agent/email-trigger', methods=['POST'])
def agent_email_trigger():
    """Pub/Sub push webhook — fires when Gmail delivers a new message notification."""
    import base64 as _base64
    import json as _json

    envelope = request.get_json(force=True) or {}
    message = envelope.get('message', {})
    data_b64 = message.get('data', '')

    if not data_b64:
        return jsonify({'ok': True})

    try:
        payload = _json.loads(_base64.b64decode(data_b64).decode('utf-8'))
    except Exception:
        return jsonify({'ok': True})

    email_address = payload.get('emailAddress', '')
    new_history_id = str(payload.get('historyId', ''))
    print(f"[email-trigger] account={email_address} historyId={new_history_id}")

    from gcs import read_json as _gcs_read
    _cfg_snapshot = _gcs_read('saucer-config.json', {})
    print(f"[email-trigger] saucer-config.json at entry: {_cfg_snapshot}")

    if not new_history_id:
        return jsonify({'ok': True})

    if email_address == _DAN:
        history_key = 'last_history_id_dan'
        refresh_token_key = 'GMAIL_REFRESH_TOKEN'
    elif email_address == _EMILY:
        history_key = 'last_history_id_emily'
        refresh_token_key = 'GMAIL_REFRESH_TOKEN_2'
    else:
        print(f"[email-trigger] unknown account: {email_address}, ignoring")
        return jsonify({'ok': True})

    from gcs import read_json, write_json
    from datetime import datetime, timezone
    config = read_json('saucer-config.json', {})
    last_history_id = config.get(history_key)

    # First notification — store baseline and exit; nothing to diff yet
    if not last_history_id:
        config[history_key] = new_history_id
        config['last_watch_established'] = datetime.now(timezone.utc).isoformat()
        write_json('saucer-config.json', config)
        print(f"[email-trigger] initialized {history_key}={new_history_id}")
        return jsonify({'ok': True})

    # Proactive re-watch if the Gmail watch is older than 7 days (watches expire after 7 days)
    last_watch_str = config.get('last_watch_established')
    if last_watch_str:
        try:
            last_watch_dt = datetime.fromisoformat(last_watch_str)
            if last_watch_dt.tzinfo is None:
                last_watch_dt = last_watch_dt.replace(tzinfo=timezone.utc)
            watch_age_days = (datetime.now(timezone.utc) - last_watch_dt).days
            if watch_age_days >= 7:
                print(f"[email-trigger] watch is {watch_age_days} days old — proactively re-watching")
                from gmail_scanner import _build_service, setup_gmail_watch
                _svc = _build_service(refresh_token_key)
                if _svc:
                    try:
                        _resp = setup_gmail_watch(_svc, _PUBSUB_TOPIC)
                        fresh_id = str(_resp.get('historyId', ''))
                        if fresh_id:
                            config[history_key] = fresh_id
                        config['last_watch_established'] = datetime.now(timezone.utc).isoformat()
                        write_json('saucer-config.json', config)
                        print(f"[email-trigger] proactive re-watch done historyId={fresh_id}")
                        return jsonify({'ok': True})
                    except Exception as _e:
                        print(f"[email-trigger] proactive re-watch error: {_e}")
        except Exception as _pe:
            print(f"[email-trigger] could not parse last_watch_established: {_pe}")

    # Advance the stored historyId immediately for idempotency on Pub/Sub retries
    config[history_key] = new_history_id
    write_json('saucer-config.json', config)

    from gmail_scanner import _build_service, fetch_new_messages_since, setup_gmail_watch
    service = _build_service(refresh_token_key)
    if not service:
        print(f"[email-trigger] no Gmail service for {email_address}")
        return jsonify({'ok': True})

    new_emails, latest_history_id = fetch_new_messages_since(service, last_history_id)

    if latest_history_id is None:
        # History is stale — re-watch to reset baseline; process nothing this round
        print(f"[email-trigger] stale historyId for {email_address}, re-watching")
        try:
            resp = setup_gmail_watch(service, _PUBSUB_TOPIC)
            fresh_id = str(resp.get('historyId', ''))
            if fresh_id:
                config[history_key] = fresh_id
                write_json('saucer-config.json', config)
        except Exception as e:
            print(f"[email-trigger] re-watch error: {e}")
        return jsonify({'ok': True})

    if latest_history_id and latest_history_id != new_history_id:
        config[history_key] = latest_history_id
        write_json('saucer-config.json', config)

    print(f"[email-trigger] {len(new_emails)} new message(s) for {email_address}")
    if not new_emails:
        return jsonify({'ok': True})

    # Load filters from Firestore
    db = get_db()
    sender_doc = db.collection('settings').document('email_filters').get()
    sender_filters = [s.lower() for s in (sender_doc.to_dict().get('addresses', []) if sender_doc.exists else [])]

    kw_doc = db.collection('settings').document('keyword_filters').get()
    keyword_filters = kw_doc.to_dict().get('keywords', []) if kw_doc.exists else []

    blocked_doc = db.collection('settings').document('blocked_senders').get()
    blocked_senders = set(blocked_doc.to_dict().get('addresses', []) if blocked_doc.exists else [])

    excl_doc = db.collection('settings').document('exclude_keyword_filters').get()
    exclude_keywords = excl_doc.to_dict().get('keywords', []) if excl_doc.exists else []

    email_intent = _get_email_intent(db)
    blocked_set_trigger = {b.lower() for b in blocked_senders}
    permitted_set_trigger = set(sender_filters)

    # Run intent eval on new emails before merging
    if new_emails:
        from email_scanner import evaluate_email_intent
        for e in new_emails:
            if 'verdict' not in e:
                result = evaluate_email_intent(e, email_intent, blocked_set_trigger, permitted_set_trigger, excluded_keywords=exclude_keywords)
                e['verdict'] = result['verdict']
                e['verdict_confidence'] = result['confidence']
                e['verdict_reason'] = result['reason']
                if result['verdict'] == 'blocked':
                    e['dismissed_by'] = 'hana'

    # Auto-save PDFs from permitted emails before stripping bytes
    _auto_save_pdf_attachments(new_emails, db)
    _strip_raw_bytes(new_emails)

    # Merge new emails into email store so they appear in the app immediately
    fresh = [e for e in new_emails if not email_store.email_exists(e['id'])]
    if fresh:
        email_store.upsert_emails_batch(fresh)
    print(f"[email-trigger] upserted {len(fresh)} new emails into Firestore")

    def _sender_matches(sender_str):
        raw = sender_str.lower()
        addr = _extract_sender_addr(sender_str)
        matched = any(f in raw or f in addr for f in sender_filters)
        print(f"[email-trigger] sender_match check: raw={raw!r} extracted={addr!r} filters={sender_filters} match={matched}")
        return matched

    def _keyword_matches(email_dict):
        haystack = ' '.join([
            email_dict.get('subject', ''),
            (email_dict.get('body', '') or email_dict.get('snippet', ''))[:2000],
        ]).lower()
        return any(kw in haystack for kw in keyword_filters)

    def _is_excluded(email_dict):
        sender_str = email_dict.get('sender', '')
        addr = _extract_sender_addr(sender_str)
        raw = sender_str.lower()
        print(f"[email-trigger] _is_excluded check addr={addr!r} blocked_set={blocked_set_trigger}")
        if any(b in raw or b in addr for b in blocked_set_trigger):
            return True
        if email_dict.get('verdict') == 'blocked':
            return True
        if exclude_keywords:
            haystack = ' '.join([
                email_dict.get('subject', ''),
                email_dict.get('sender', ''),
                (email_dict.get('body', '') or email_dict.get('snippet', ''))[:500],
            ]).lower()
            if any(kw in haystack for kw in exclude_keywords):
                return True
        return False

    for email in new_emails:
        subj = email.get('subject', '(no subject)')
        if _is_excluded(email):
            print(f"[email-trigger] excluded (verdict={email.get('verdict')}): {subj}")
            continue
        if not (_sender_matches(email.get('sender', '')) or _keyword_matches(email)):
            print(f"[email-trigger] no filter match, skipping: {subj}")
            continue

        print(f"[email-trigger] qualifying (verdict={email.get('verdict')}) — enqueuing Cloud Task for: {subj}")

        # Replace in-process threading with Cloud Tasks.
        # The task handler at /tasks/process-email runs process_single_email
        # inside Cloud Tasks, giving us retries and observability.
        _enqueue_email_processing_task(email_id=email.get('id', ''), email_address=email_address)

    return jsonify({'ok': True})


def _enqueue_email_processing_task(email_id: str, email_address: str) -> None:
    """Enqueue a Cloud Task to process a single qualifying email through the agent.

    Target: POST /tasks/process-email on this Cloud Run service.
    Uses OIDC authentication — same service account as the handle-action handler.
    Fires-and-forgets; errors are logged but do not fail the Pub/Sub response.
    """
    import json as _json
    from google.cloud import tasks_v2 as _tasks

    handler_url = _CLOUD_RUN_URL.rstrip('/') + '/tasks/process-email'
    payload = {'email_id': email_id, 'email_address': email_address}

    task = {
        'http_request': {
            'http_method': _tasks.HttpMethod.POST,
            'url': handler_url,
            'headers': {'Content-Type': 'application/json'},
            'body': _json.dumps(payload).encode('utf-8'),
            'oidc_token': {
                'service_account_email': _SA_EMAIL,
                'audience': _CLOUD_RUN_URL,
            },
        }
    }

    try:
        client = _tasks.CloudTasksClient()
        queue_path = client.queue_path(_PROJECT, _LOCATION, _QUEUE)
        response = client.create_task(request={'parent': queue_path, 'task': task})
        print(f'[email-trigger] enqueued task for email_id={email_id} task_name={response.name}')
    except Exception as e:
        print(f'[email-trigger] ERROR enqueuing task for email_id={email_id}: {e}')


@agent_bp.route('/agent/renew-gmail-watch', methods=['POST'])
def renew_gmail_watch():
    """Renew Gmail push watch for all configured accounts. Called by Cloud Scheduler every 6 days."""
    agent_key = os.environ.get('AGENT_KEY', '')
    provided_key = request.headers.get('X-Agent-Key', '')
    if not agent_key or provided_key != agent_key:
        return jsonify({'error': 'Unauthorized'}), 401

    topic = _PUBSUB_TOPIC
    results = {}

    from gmail_scanner import _build_service, setup_gmail_watch
    from gcs import read_json, write_json

    for token_key, history_key, label in [
        ('GMAIL_REFRESH_TOKEN', 'last_history_id_dan', 'dan'),
        ('GMAIL_REFRESH_TOKEN_2', 'last_history_id_emily', 'emily'),
    ]:
        svc = _build_service(token_key)
        if not svc:
            results[label] = 'no_service'
            continue
        try:
            resp = setup_gmail_watch(svc, topic)
            history_id = str(resp.get('historyId', ''))
            if history_id:
                from datetime import datetime, timezone
                config = read_json('saucer-config.json', {})
                config[history_key] = history_id
                config['last_watch_established'] = datetime.now(timezone.utc).isoformat()
                write_json('saucer-config.json', config)
            results[label] = {'historyId': history_id, 'expiration': resp.get('expiration')}
            print(f"[renew-watch] {label}: historyId={history_id} expiration={resp.get('expiration')}")
        except Exception as e:
            results[label] = {'error': str(e)}
            print(f"[renew-watch] {label} error: {e}")

    return jsonify({'results': results})
