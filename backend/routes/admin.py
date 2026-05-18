import os
from flask import Blueprint, request, jsonify
from lib.firestore_client import get_db
from logger import log_action, get_recent_actions, get_action_summary, get_recent_decisions

admin_bp = Blueprint('admin', __name__)


# ── User Settings ─────────────────────────────────────────────────────────────

@admin_bp.route('/user-settings/<user_id>', methods=['GET'])
def get_user_settings(user_id):
    db = get_db()
    doc = db.collection('user_settings').document(user_id).get()
    if doc.exists:
        data = doc.to_dict()
        return jsonify({
            'roles': data.get('roles', []),
            'preferences': data.get('preferences', []),
        })
    return jsonify({'roles': [], 'preferences': []})


@admin_bp.route('/user-settings/<user_id>', methods=['PUT'])
def save_user_settings(user_id):
    data = request.get_json()
    roles = data.get('roles', [])
    prefs = data.get('preferences', [])
    db = get_db()
    db.collection('user_settings').document(user_id).set({
        'roles': roles,
        'preferences': prefs,
    })
    log_action(user_id, 'profile_updated', {'roles': roles, 'preferences': prefs}, actor='user')
    return jsonify({'ok': True})


# ── Actions / Decisions history ───────────────────────────────────────────────

@admin_bp.route('/actions/recent', methods=['GET'])
def get_actions_recent():
    user = request.args.get('user') or None
    action_type = request.args.get('action_type') or None
    limit = min(int(request.args.get('limit', 20)), 100)
    since = request.args.get('since') or None
    actions = get_recent_actions(user=user, action_type=action_type, limit=limit, since=since)
    return jsonify({'actions': actions})


@admin_bp.route('/actions/summary', methods=['GET'])
def get_actions_summary():
    days = int(request.args.get('days', 7))
    summary = get_action_summary(days=days)
    return jsonify({'summary': summary})


@admin_bp.route('/decisions/recent', methods=['GET'])
def get_decisions_recent():
    user_email = request.args.get('user_email') or None
    action_type = request.args.get('action_type') or None
    limit = min(int(request.args.get('limit', 20)), 100)
    since = request.args.get('since') or None
    decisions = get_recent_decisions(user_email=user_email, action_type=action_type, limit=limit, since=since)
    return jsonify({'decisions': decisions})


# DEPRECATED — replaced by memory.py knowledge system (passive learning + save_note).
@admin_bp.route('/onboarding', methods=['POST'])
def onboarding():
    return jsonify({
        'error': 'This endpoint has been replaced by the Hana memory system. '
                 'Hana now learns about your household through natural conversation.'
    }), 410


# ── Conversation history ──────────────────────────────────────────────────────

@admin_bp.route('/conversation-history', methods=['GET'])
def get_conversation_history():
    from conversation_history import search_history, get_recent_history
    user_email = request.args.get('user_email', '')
    keyword = request.args.get('keyword', '').strip()
    limit = min(int(request.args.get('limit', 20)), 50)

    if keyword:
        results = search_history(user_email, keyword, days_back=90, limit=limit)
    else:
        results = get_recent_history(user_email, limit=limit)

    return jsonify({'conversations': results})


@admin_bp.route('/summarize-conversations', methods=['POST'])
def summarize_conversations():
    from conversation_history import summarize_old_conversations
    count = summarize_old_conversations()
    return jsonify({'summarized': count})


# ── Session checkpoint ────────────────────────────────────────────────────────

@admin_bp.route('/session/checkpoint', methods=['GET'])
def get_session_checkpoint():
    from gcs import read_json
    checkpoint = read_json('saucer-session-checkpoint.json', None)
    return jsonify({'checkpoint': checkpoint})


@admin_bp.route('/session/checkpoint', methods=['POST'])
def save_session_checkpoint():
    from gcs import write_json
    from datetime import datetime, timezone
    data = request.get_json() or {}
    content = data.get('content', '')
    if not content:
        return jsonify({'error': 'Missing content'}), 400
    checkpoint = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'content': content,
    }
    write_json('saucer-session-checkpoint.json', checkpoint)
    return jsonify({'ok': True, 'timestamp': checkpoint['timestamp']})


# ── Debug ─────────────────────────────────────────────────────────────────────

@admin_bp.route('/debug/config', methods=['GET'])
def debug_config():
    agent_key = os.environ.get('AGENT_KEY', '')
    provided_key = request.headers.get('X-Agent-Key', '')
    if not agent_key or provided_key != agent_key:
        return jsonify({'error': 'Unauthorized'}), 401
    from gcs import read_json
    config = read_json('saucer-config.json', {})
    return jsonify({'config': config})


@admin_bp.route('/debug/filters', methods=['GET'])
def debug_filters():
    agent_key = os.environ.get('AGENT_KEY', '')
    provided_key = request.headers.get('X-Agent-Key', '')
    if not agent_key or provided_key != agent_key:
        return jsonify({'error': 'Unauthorized'}), 401

    from gmail_scanner import build_gmail_query
    from gcs import read_json
    from datetime import datetime, timedelta, timezone

    db = get_db()

    sender_doc = db.collection('settings').document('email_filters').get()
    sender_filters = sender_doc.to_dict().get('addresses', []) if sender_doc.exists else []

    kw_doc = db.collection('settings').document('keyword_filters').get()
    keyword_filters = kw_doc.to_dict().get('keywords', []) if kw_doc.exists else []

    excl_doc = db.collection('settings').document('exclude_keyword_filters').get()
    exclude_keywords = excl_doc.to_dict().get('keywords', []) if excl_doc.exists else []

    blocked_doc = db.collection('settings').document('blocked_senders').get()
    blocked_senders = blocked_doc.to_dict().get('addresses', []) if blocked_doc.exists else []

    config = read_json('saucer-config.json', {})
    last_sync = config.get('last_sync_timestamp')
    if last_sync is None:
        after_ts = (datetime.now(timezone.utc) - timedelta(days=90)).timestamp()
    else:
        after_ts = last_sync

    effective_senders = (sender_filters + ['me']) if sender_filters else None
    query = build_gmail_query(
        sender_filter=effective_senders,
        keyword_filter=keyword_filters if keyword_filters else None,
        after_timestamp=after_ts,
    )

    print(f"[debug/filters] sender_filters={sender_filters}")
    print(f"[debug/filters] keyword_filters={keyword_filters}")
    print(f"[debug/filters] exclude_keywords={exclude_keywords}")
    print(f"[debug/filters] blocked_senders={blocked_senders}")
    print(f"[debug/filters] effective_gmail_query={query!r}")

    return jsonify({
        'sender_filters': sender_filters,
        'keyword_filters': keyword_filters,
        'exclude_keywords': exclude_keywords,
        'blocked_senders': blocked_senders,
        'effective_gmail_query': query,
    })
