import os
import uuid

from flask import Blueprint, request, jsonify
from google.cloud import firestore

from lib.firestore_client import get_db
from logger import log_action

filters_bp = Blueprint('filters', __name__)


# ── Private helper shared by filter routes that call _backfill ────────────────

def _backfill_filters(sender_filter=None, keyword_filter=None):
    """Scan the last 90 days for a newly added sender or keyword and merge into stored emails."""
    import email_store
    from lib.email_helpers import _strip_raw_bytes
    try:
        from gmail_scanner import scan_emails
        from datetime import datetime, timedelta, timezone
        after_ts = (datetime.now(timezone.utc) - timedelta(days=90)).timestamp()
        new_emails = scan_emails(
            sender_filter=sender_filter,
            keyword_filter=keyword_filter,
            after_timestamp=after_ts
        )
        if new_emails:
            fresh = [e for e in new_emails if not email_store.email_exists(e['id'])]
            if fresh:
                _strip_raw_bytes(fresh)
                email_store.upsert_emails_batch(fresh)
    except Exception as e:
        print(f"Backfill error: {e}")


def _req_user(data=None):
    """Extract the acting user's email from request body or query param."""
    if data:
        v = data.get('user', '')
        if v:
            return v
    return request.args.get('user', 'unknown')


def _gemini_text(prompt: str) -> str:
    import google.generativeai as genai
    genai.configure(api_key=os.environ.get("GOOGLE_API_KEY"))
    model = genai.GenerativeModel('gemini-2.5-flash')
    return model.generate_content(prompt).text.strip()


# ── Routes ────────────────────────────────────────────────────────────────────

@filters_bp.route('/email-filters', methods=['GET'])
def get_email_filters():
    db = get_db()
    doc = db.collection('settings').document('email_filters').get()
    filters = doc.to_dict().get('addresses', []) if doc.exists else []
    return jsonify({'filters': filters})


@filters_bp.route('/email-filters', methods=['POST'])
def add_email_filter():
    data = request.get_json()
    email = data.get('email', '').strip().lower()
    if not email:
        return jsonify({'error': 'Missing email'}), 400
    db = get_db()
    db.collection('settings').document('email_filters').set(
        {'addresses': firestore.ArrayUnion([email])}, merge=True
    )
    _backfill_filters(sender_filter=[email])
    user = _req_user(data)
    log_action(user, 'sender_filter_added', {'sender': email}, actor='user')
    return jsonify({'ok': True})


@filters_bp.route('/email-filters/<path:email>', methods=['DELETE'])
def remove_email_filter(email):
    db = get_db()
    db.collection('settings').document('email_filters').set(
        {'addresses': firestore.ArrayRemove([email])}, merge=True
    )
    user = _req_user()
    log_action(user, 'sender_filter_removed', {'sender': email}, actor='user')
    return jsonify({'ok': True})


@filters_bp.route('/keyword-filters', methods=['GET'])
def get_keyword_filters():
    db = get_db()
    doc = db.collection('settings').document('keyword_filters').get()
    keywords = doc.to_dict().get('keywords', []) if doc.exists else []
    return jsonify({'keywords': keywords})


@filters_bp.route('/keyword-filters', methods=['POST'])
def add_keyword_filter():
    data = request.get_json()
    keyword = data.get('keyword', '').strip().lower()
    if not keyword:
        return jsonify({'error': 'Missing keyword'}), 400
    db = get_db()
    db.collection('settings').document('keyword_filters').set(
        {'keywords': firestore.ArrayUnion([keyword])}, merge=True
    )
    _backfill_filters(keyword_filter=[keyword])
    user = _req_user(data)
    log_action(user, 'keyword_filter_added', {'keyword': keyword}, actor='user')
    return jsonify({'ok': True})


@filters_bp.route('/keyword-filters/<path:keyword>', methods=['DELETE'])
def remove_keyword_filter(keyword):
    db = get_db()
    db.collection('settings').document('keyword_filters').set(
        {'keywords': firestore.ArrayRemove([keyword])}, merge=True
    )
    user = _req_user()
    log_action(user, 'keyword_filter_removed', {'keyword': keyword}, actor='user')
    return jsonify({'ok': True})


@filters_bp.route('/exclude-keyword-filters', methods=['GET'])
def get_exclude_keyword_filters():
    db = get_db()
    doc = db.collection('settings').document('exclude_keyword_filters').get()
    keywords = doc.to_dict().get('keywords', []) if doc.exists else []
    return jsonify({'keywords': keywords})


@filters_bp.route('/exclude-keyword-filters', methods=['POST'])
def add_exclude_keyword_filter():
    data = request.get_json()
    keyword = data.get('keyword', '').strip().lower()
    if not keyword:
        return jsonify({'error': 'Missing keyword'}), 400
    db = get_db()
    db.collection('settings').document('exclude_keyword_filters').set(
        {'keywords': firestore.ArrayUnion([keyword])}, merge=True
    )
    user = _req_user(data)
    log_action(user, 'exclude_keyword_filter_added', {'keyword': keyword}, actor='user')
    return jsonify({'ok': True})


@filters_bp.route('/exclude-keyword-filters/<path:keyword>', methods=['DELETE'])
def remove_exclude_keyword_filter(keyword):
    db = get_db()
    db.collection('settings').document('exclude_keyword_filters').set(
        {'keywords': firestore.ArrayRemove([keyword])}, merge=True
    )
    user = _req_user()
    log_action(user, 'exclude_keyword_filter_removed', {'keyword': keyword}, actor='user')
    return jsonify({'ok': True})


@filters_bp.route('/blocked-senders', methods=['GET'])
def get_blocked_senders():
    db = get_db()
    doc = db.collection('settings').document('blocked_senders').get()
    addresses = doc.to_dict().get('addresses', []) if doc.exists else []
    return jsonify({'addresses': addresses})


@filters_bp.route('/blocked-senders', methods=['POST'])
def add_blocked_sender():
    data = request.get_json()
    email = (data.get('email') or '').strip()
    if not email:
        return jsonify({'error': 'Missing email'}), 400
    db = get_db()
    db.collection('settings').document('blocked_senders').set(
        {'addresses': firestore.ArrayUnion([email])}, merge=True
    )
    user = _req_user(data)
    log_action(user, 'sender_blocked', {'sender': email}, actor='user')
    return jsonify({'ok': True})


@filters_bp.route('/blocked-senders/<path:email>', methods=['DELETE'])
def remove_blocked_sender(email):
    db = get_db()
    db.collection('settings').document('blocked_senders').set(
        {'addresses': firestore.ArrayRemove([email])}, merge=True
    )
    user = _req_user()
    log_action(user, 'sender_unblocked', {'sender': email}, actor='user')
    return jsonify({'ok': True})


@filters_bp.route('/blocked-topics', methods=['GET'])
def get_blocked_topics():
    db = get_db()
    docs = db.collection('blocked_topics').stream()
    topics = []
    for doc in docs:
        d = doc.to_dict()
        d['id'] = doc.id
        topics.append(d)
    return jsonify({'topics': topics})


@filters_bp.route('/blocked-topics', methods=['POST'])
def add_blocked_topic():
    from datetime import datetime, timezone
    data = request.get_json()
    sender = (data.get('sender') or '').strip()
    label = (data.get('label') or '').strip()
    description = (data.get('description') or label).strip()
    if not sender or not label:
        return jsonify({'error': 'Missing sender or label'}), 400
    db = get_db()
    doc_id = str(uuid.uuid4())
    db.collection('blocked_topics').document(doc_id).set({
        'sender': sender,
        'label': label,
        'description': description,
        'created_at': datetime.now(timezone.utc).isoformat(),
        'created_by': _req_user(data),
    })
    log_action(_req_user(data), 'topic_blocked', {'sender': sender, 'label': label}, actor='user')
    return jsonify({'ok': True, 'id': doc_id})


@filters_bp.route('/blocked-topics/<topic_id>', methods=['DELETE'])
def remove_blocked_topic(topic_id):
    db = get_db()
    db.collection('blocked_topics').document(topic_id).delete()
    user = _req_user()
    log_action(user, 'topic_unblocked', {'id': topic_id}, actor='user')
    return jsonify({'ok': True})


@filters_bp.route('/generate-topic-label', methods=['POST'])
def generate_topic_label():
    data = request.get_json()
    subject = (data.get('subject') or '').strip()
    body_preview = (data.get('body_preview') or '').strip()[:300]
    if not subject:
        return jsonify({'error': 'Missing subject'}), 400
    prompt = (
        f"In 4-6 words, what type of email is this? Be specific but general enough "
        f"to apply to future similar emails from the same sender. "
        f"Examples: 'Home Depot promotional offers', 'school newsletter updates', "
        f"'credit card marketing'. Return only the label, nothing else.\n\n"
        f"Subject: {subject}\nPreview: {body_preview}"
    )
    label = _gemini_text(prompt)
    return jsonify({'label': label})
