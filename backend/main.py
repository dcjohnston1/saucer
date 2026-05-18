import hashlib
import os
import uuid
from flask import Flask, request, jsonify
from flask_cors import CORS
from google.cloud import firestore
from mediator import process_message
from logger import log_action, get_recent_actions, get_action_summary, get_recent_decisions
import email_store
import pending_actions
from lib.firestore_client import get_db
from lib.email_helpers import (
    _extract_sender_addr,
    _get_email_intent,
    _auto_save_pdf_attachments,
    _strip_raw_bytes,
)

app = Flask(__name__)
CORS(app)

from routes.agent import agent_bp
from routes.tasks import tasks_bp
app.register_blueprint(agent_bp)
app.register_blueprint(tasks_bp)


def _parse_date_safe(date_str: str):
    """Parse an RFC 2822 date string to a timezone-aware datetime for sorting.

    Returns datetime.min (UTC) on any parse failure so malformed dates sort last.
    """
    from email.utils import parsedate_to_datetime
    from datetime import datetime, timezone
    if not date_str:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        return parsedate_to_datetime(date_str)
    except Exception:
        return datetime.min.replace(tzinfo=timezone.utc)


def _record_deleted_task(title: str):
    """Append a task title to saucer-deleted-tasks.json and expire entries older than 30 days."""
    from gcs import read_json, write_json
    from datetime import datetime, timedelta, timezone
    entries = read_json('saucer-deleted-tasks.json', [])
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    entries = [e for e in entries if datetime.fromisoformat(e['deleted_at']) > cutoff]
    norm = title.strip().lower()
    if not any(e['title'] == norm for e in entries):
        entries.append({'title': norm, 'deleted_at': datetime.now(timezone.utc).isoformat()})
    write_json('saucer-deleted-tasks.json', entries)


def _is_task_deleted(title: str) -> bool:
    """Return True if this title is in saucer-deleted-tasks.json (not yet expired)."""
    from gcs import read_json
    from datetime import datetime, timedelta, timezone
    entries = read_json('saucer-deleted-tasks.json', [])
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    norm = title.strip().lower()
    return any(
        e['title'] == norm and datetime.fromisoformat(e['deleted_at']) > cutoff
        for e in entries
    )


def _req_user(data=None):
    """Extract the acting user's email from request body or query param."""
    if data:
        v = data.get('user', '')
        if v:
            return v
    return request.args.get('user', 'unknown')


def _is_vague_summary(summary):
    """Return True if the summary is missing or too short/generic to be useful."""
    if not summary:
        return True
    if len(summary) < 60:
        return True
    lower = summary.lower().strip()
    if lower.startswith('email from') or lower.startswith('message from'):
        return True
    return False


def _get_blocked_senders_set(db) -> set:
    doc = db.collection('settings').document('blocked_senders').get()
    addresses = doc.to_dict().get('addresses', []) if doc.exists else []
    return {a.lower() for a in addresses}


def _get_permitted_senders_list(db) -> list:
    doc = db.collection('settings').document('email_filters').get()
    return [a.lower() for a in (doc.to_dict().get('addresses', []) if doc.exists else [])]


def _get_excluded_keywords(db) -> list:
    doc = db.collection('settings').document('exclude_keyword_filters').get()
    return [kw.lower() for kw in (doc.to_dict().get('keywords', []) if doc.exists else [])]


def _run_intent_eval_batch(emails, email_intent, blocked_set, permitted_list, limit=20, excluded_keywords=None):
    """Evaluate intent for emails missing a verdict. Mutates emails in place."""
    from email_scanner import evaluate_email_intent
    needs_eval = [e for e in emails if 'verdict' not in e][:limit]
    if not needs_eval:
        return
    permitted_set = set(permitted_list)
    for e in needs_eval:
        try:
            result = evaluate_email_intent(e, email_intent, blocked_set, permitted_set, excluded_keywords=excluded_keywords)
            e['verdict'] = result['verdict']
            e['verdict_confidence'] = result['confidence']
            e['verdict_reason'] = result['reason']
            if result['verdict'] == 'blocked':
                e['dismissed_by'] = 'hana'
        except Exception as ex:
            print(f"[intent_eval] error for {e.get('id')}: {ex}")
            e['verdict'] = 'uncertain'


def _force_reevaluate_all_emails(emails, email_intent, excluded_keywords, blocked_set, permitted_set):
    """Re-evaluate ALL emails (ignoring existing verdicts) using batched Gemini calls.

    Mutates emails in place. Returns counts dict: {total, permitted, uncertain, blocked}.
    """
    from email_scanner import batch_evaluate_emails_intent
    results = batch_evaluate_emails_intent(
        emails, email_intent,
        excluded_keywords=excluded_keywords,
        blocked_senders=blocked_set,
        permitted_senders=permitted_set,
    )
    counts = {'total': len(emails), 'permitted': 0, 'uncertain': 0, 'blocked': 0}
    for e in emails:
        email_id = e.get('id', '')
        r = results.get(email_id)
        if r:
            new_verdict = r['verdict']
            e['verdict'] = new_verdict
            e['verdict_reason'] = r['reason']
            e.pop('verdict_confidence', None)
            if new_verdict == 'blocked':
                e['dismissed_by'] = 'hana'
            elif e.get('dismissed_by') == 'hana':
                e.pop('dismissed_by', None)
            counts[new_verdict] = counts.get(new_verdict, 0) + 1
        else:
            counts[e.get('verdict', 'uncertain')] = counts.get(e.get('verdict', 'uncertain'), 0) + 1
    return counts


def _backfill(sender_filter=None, keyword_filter=None):
    """Scan the last 90 days for a newly added sender or keyword and merge into stored emails."""
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


@app.route('/chat', methods=['POST'])
def chat():
    data = request.get_json()
    user = data.get('user')
    user_email = data.get('user_email') or user
    message = data.get('message')
    conversation_id = data.get('conversation_id') or str(uuid.uuid4())
    voice_mode = bool(data.get('voice_mode', False))

    if not user or not message:
        return jsonify({'error': 'Missing user or message'}), 400

    history = data.get('history', [])
    reply, actions = process_message(user, message, history, user_email=user_email, conversation_id=conversation_id, voice_mode=voice_mode)
    return jsonify({
        'reply': reply,
        'actions': actions,
        'model': 'gemini-2.5-flash'
    })


@app.route('/doc', methods=['GET'])
def get_doc():
    from gdocs import read_doc
    raw_content = read_doc()

    tasks = []
    lines = raw_content.split('\n')
    for line in lines:
        if not line.strip() or not line.startswith('TODO'):
            continue

        parts = [p.strip() for p in line.split('|')]
        task = {
            'title': parts[1] if len(parts) > 1 else 'Untitled Task',
            'due': None,
            'added': None,
            'owner': None,
            'priority': None,
            'recurrence': None,
            'location': None,
            'urgency': None,
            'notes': None,
            'assignee': None,
            'source_email_id': None,
            'source': None,
        }

        for part in parts[2:]:
            if part.startswith('due:'):
                task['due'] = part[4:]
            elif part.startswith('added:'):
                task['added'] = part[6:]
            elif part.startswith('owner:'):
                task['owner'] = part[6:]
            elif part.startswith('priority:'):
                task['priority'] = part[9:]
            elif part.startswith('recurrence:'):
                task['recurrence'] = part[11:]
            elif part.startswith('location:'):
                task['location'] = part[9:]
            elif part.startswith('urgency:'):
                task['urgency'] = part[8:]
            elif part.startswith('notes:'):
                task['notes'] = part[6:]
            elif part.startswith('assignee:'):
                task['assignee'] = part[9:]
            elif part.startswith('source_email_id:'):
                task['source_email_id'] = part[16:]
            elif part.startswith('source:'):
                task['source'] = part[7:]

        tasks.append(task)

    return jsonify({'tasks': tasks})


@app.route('/emails', methods=['GET'])
def get_emails():
    from gmail_scanner import scan_emails
    from gcs import read_json, write_json
    from datetime import datetime, timedelta, timezone

    db = get_db()
    doc = db.collection('settings').document('email_filters').get()
    filters = doc.to_dict().get('addresses', []) if doc.exists else []
    print(f"[/emails] sender_filters from Firestore: {filters}")

    config = read_json('saucer-config.json', {})
    last_sync = config.get('last_sync_timestamp')

    if last_sync is None:
        after_ts = (datetime.now(timezone.utc) - timedelta(days=90)).timestamp()
    else:
        after_ts = last_sync

    kw_doc = db.collection('settings').document('keyword_filters').get()
    keywords = kw_doc.to_dict().get('keywords', []) if kw_doc.exists else []

    effective_filters = (filters + ['me']) if filters else None
    new_emails = scan_emails(
        sender_filter=effective_filters,
        keyword_filter=keywords if keywords else None,
        after_timestamp=after_ts
    )

    config['last_sync_timestamp'] = datetime.now(timezone.utc).timestamp()
    write_json('saucer-config.json', config)

    email_intent = _get_email_intent(db)
    blocked_set = _get_blocked_senders_set(db)
    permitted_list = _get_permitted_senders_list(db)
    excluded_keywords = _get_excluded_keywords(db)

    # Intent eval, PDF auto-save, and byte-strip run on new emails before upserting
    _run_intent_eval_batch(new_emails, email_intent, blocked_set, permitted_list, excluded_keywords=excluded_keywords)
    _auto_save_pdf_attachments(new_emails, db)
    _strip_raw_bytes(new_emails)
    for e in new_emails:
        email_store.upsert_email(e)

    # Generate summaries for visible emails that lack one (cap at 10 per request)
    visible_meta = email_store.list_emails(
        exclude_dismissed=True,
        exclude_reviewed=True,
        exclude_blocked_verdict=True,
        include_body=False,
    )
    to_summarize_ids = [e['id'] for e in visible_meta if _is_vague_summary(e.get('summary'))][:10]
    if to_summarize_ids:
        from email_scanner import summarize_emails
        to_summarize_with_body = email_store.get_emails_by_ids(to_summarize_ids)
        summaries = summarize_emails(to_summarize_with_body)
        if summaries:
            for eid, summary in summaries.items():
                email_store.update_email_fields(eid, {'summary': summary})

    excl_doc = db.collection('settings').document('exclude_keyword_filters').get()
    exclude_keywords = excl_doc.to_dict().get('keywords', []) if excl_doc.exists else []
    print(f"[/emails] exclude_keywords: {exclude_keywords}")

    visible = email_store.list_emails(
        exclude_dismissed=True,
        exclude_reviewed=True,
        exclude_blocked_verdict=True,
        include_body=True,
    )

    # Re-apply summaries updated above (in-memory refresh)
    if to_summarize_ids and summaries:
        for e in visible:
            if e['id'] in summaries:
                e['summary'] = summaries[e['id']]

    if exclude_keywords:
        before_count = len(visible)
        def _matches_exclude(e):
            haystack = ' '.join([
                e.get('subject', ''),
                e.get('sender', ''),
                (e.get('body', '') or e.get('snippet', ''))[:500],
            ]).lower()
            return any(kw in haystack for kw in exclude_keywords)
        visible = [e for e in visible if not _matches_exclude(e)]
        print(f"[/emails] exclude filter: {before_count} -> {len(visible)} emails")

    if blocked_set:
        visible = [e for e in visible if _extract_sender_addr(e.get('sender', '')) not in blocked_set
                   and e.get('sender', '').lower() not in blocked_set]

    return jsonify({'emails': visible})


@app.route('/emails/cached', methods=['GET'])
def get_cached_emails():
    """Return stored emails from Firestore/GCS without triggering a Gmail scan."""
    db = get_db()

    excl_doc = db.collection('settings').document('exclude_keyword_filters').get()
    exclude_keywords = excl_doc.to_dict().get('keywords', []) if excl_doc.exists else []

    blocked_set = _get_blocked_senders_set(db)

    visible = email_store.list_emails(
        exclude_dismissed=True,
        exclude_reviewed=True,
        exclude_blocked_verdict=True,
        include_body=True,
    )

    if exclude_keywords:
        def _matches_exclude_cached(e):
            haystack = ' '.join([
                e.get('subject', ''),
                e.get('sender', ''),
                (e.get('body', '') or e.get('snippet', ''))[:500],
            ]).lower()
            return any(kw in haystack for kw in exclude_keywords)
        visible = [e for e in visible if not _matches_exclude_cached(e)]

    if blocked_set:
        visible = [e for e in visible if _extract_sender_addr(e.get('sender', '')) not in blocked_set
                   and e.get('sender', '').lower() not in blocked_set]

    return jsonify({'emails': visible})


@app.route('/emails/resync', methods=['POST'])
def resync_emails():
    """Force a 90-day re-scan and re-evaluate all emails."""
    from gmail_scanner import scan_emails
    from gcs import read_json, write_json
    from datetime import datetime, timedelta, timezone

    db = get_db()
    doc = db.collection('settings').document('email_filters').get()
    filters = doc.to_dict().get('addresses', []) if doc.exists else []
    kw_doc = db.collection('settings').document('keyword_filters').get()
    keywords = kw_doc.to_dict().get('keywords', []) if kw_doc.exists else []

    after_ts = (datetime.now(timezone.utc) - timedelta(days=90)).timestamp()
    effective_filters = (filters + ['me']) if filters else None
    new_emails = scan_emails(
        sender_filter=effective_filters,
        keyword_filter=keywords if keywords else None,
        after_timestamp=after_ts
    )

    config = read_json('saucer-config.json', {})
    config['last_sync_timestamp'] = datetime.now(timezone.utc).timestamp()
    write_json('saucer-config.json', config)

    email_intent = _get_email_intent(db)
    blocked_set = _get_blocked_senders_set(db)
    permitted_list = _get_permitted_senders_list(db)
    excluded_keywords = _get_excluded_keywords(db)

    # Force re-evaluate all stored emails
    all_stored = email_store.list_emails(
        limit=2000,
        exclude_dismissed=False,
        exclude_reviewed=False,
        exclude_blocked_verdict=False,
        include_body=False,
    )
    # Merge new emails in-memory for batch re-eval
    stored_ids = {e['id'] for e in all_stored}
    merged_for_eval = new_emails + [e for e in all_stored if e['id'] not in {e2['id'] for e2 in new_emails}]
    eval_counts = _force_reevaluate_all_emails(merged_for_eval, email_intent, excluded_keywords, blocked_set, set(permitted_list))
    print(f"[resync] re-eval complete: {eval_counts}")

    _auto_save_pdf_attachments(merged_for_eval, db)
    _strip_raw_bytes(merged_for_eval)

    for e in merged_for_eval:
        email_store.upsert_email(e)

    visible = email_store.list_emails(
        exclude_dismissed=True,
        exclude_reviewed=True,
        exclude_blocked_verdict=True,
        include_body=True,
    )

    if blocked_set:
        visible = [e for e in visible if _extract_sender_addr(e.get('sender', '')) not in blocked_set
                   and e.get('sender', '').lower() not in blocked_set]

    return jsonify({'emails': visible, 'synced': len(new_emails), 'eval_counts': eval_counts})


@app.route('/emails/<email_id>/dismiss', methods=['DELETE'])
def dismiss_email(email_id):
    from gcs import read_json, write_json
    dismissed = read_json('saucer-dismissed.json', [])
    if email_id not in dismissed:
        dismissed.append(email_id)
        write_json('saucer-dismissed.json', dismissed)
    email_store.update_email_fields(email_id, {'dismissed_by': 'user'})
    user = _req_user()
    log_action(user, 'email_dismissed', {'email_id': email_id}, actor='user')
    return jsonify({'ok': True})


@app.route('/emails/<email_id>/review', methods=['POST'])
def review_email(email_id):
    from gcs import read_json, write_json
    reviewed = read_json('saucer-reviewed.json', [])
    if email_id in reviewed:
        reviewed.remove(email_id)
    reviewed.insert(0, email_id)
    write_json('saucer-reviewed.json', reviewed)
    user = _req_user()
    log_action(user, 'email_reviewed', {'email_id': email_id}, actor='user')
    return jsonify({'ok': True})


@app.route('/reviewed-emails', methods=['GET'])
def get_reviewed_emails():
    from datetime import datetime, timedelta, timezone

    since_30 = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    actions = get_recent_actions(action_type=None, limit=200, since=since_30)

    ACTION_LABEL_MAP = {
        'email_dismissed': 'Dismissed by you',
        'email_reviewed': 'Marked reviewed',
        'email_restored': 'Restored from dismissed',
    }
    email_action_map = {}
    for a in reversed(actions):
        eid = a.get('metadata', {}).get('email_id') or a.get('email_id')
        if not eid:
            continue
        atype = a.get('action_type', '')
        if atype in ACTION_LABEL_MAP:
            email_action_map[eid] = {
                'label': ACTION_LABEL_MAP[atype],
                'timestamp': a.get('timestamp', ''),
                'actor': a.get('actor', 'user'),
            }

    action_email_ids = list(email_action_map.keys())
    fetched_emails = email_store.get_emails_by_ids(action_email_ids)
    email_map = {e['id']: e for e in fetched_emails}

    result = []
    for eid, action_info in email_action_map.items():
        if eid in email_map:
            entry = dict(email_map[eid])
            entry['_action_label'] = action_info['label']
            entry['_action_timestamp'] = action_info['timestamp']
            result.append(entry)

    result.sort(key=lambda x: x.get('_action_timestamp', ''), reverse=True)
    return jsonify({'emails': result[:60], 'window_days': 30})


@app.route('/doc/task', methods=['DELETE'])
def complete_task():
    data = request.get_json()
    title = data.get('title')
    if not title:
        return jsonify({'error': 'Missing title'}), 400
    from gdocs import complete_task as gdocs_complete_task
    gdocs_complete_task(title)
    _record_deleted_task(title)
    user = _req_user(data)
    log_action(user, 'task_completed', {'title': title}, actor='user')
    return jsonify({'ok': True})


@app.route('/doc/dedup', methods=['POST'])
def dedup_tasks():
    from gdocs import dedup_tasks as gdocs_dedup
    removed = gdocs_dedup()
    return jsonify({'removed': removed})


@app.route('/email-filters', methods=['GET'])
def get_email_filters():
    db = get_db()
    doc = db.collection('settings').document('email_filters').get()
    filters = doc.to_dict().get('addresses', []) if doc.exists else []
    return jsonify({'filters': filters})


@app.route('/email-filters', methods=['POST'])
def add_email_filter():
    data = request.get_json()
    email = data.get('email', '').strip().lower()
    if not email:
        return jsonify({'error': 'Missing email'}), 400
    db = get_db()
    db.collection('settings').document('email_filters').set(
        {'addresses': firestore.ArrayUnion([email])}, merge=True
    )
    _backfill(sender_filter=[email])
    user = _req_user(data)
    log_action(user, 'sender_filter_added', {'sender': email}, actor='user')
    return jsonify({'ok': True})


@app.route('/email-filters/<path:email>', methods=['DELETE'])
def remove_email_filter(email):
    db = get_db()
    db.collection('settings').document('email_filters').set(
        {'addresses': firestore.ArrayRemove([email])}, merge=True
    )
    user = _req_user()
    log_action(user, 'sender_filter_removed', {'sender': email}, actor='user')
    return jsonify({'ok': True})


@app.route('/emails/search', methods=['GET'])
def search_emails():
    from gmail_scanner import scan_emails
    from gcs import read_json
    q = request.args.get('q', '').strip()
    if not q or len(q) < 2:
        return jsonify({'emails': []})
    emails = scan_emails(keyword_filter=[q])
    dismissed = set(read_json('saucer-dismissed.json', []))
    visible = [e for e in emails if e['id'] not in dismissed]
    return jsonify({'emails': visible[:20]})


@app.route('/keyword-filters', methods=['GET'])
def get_keyword_filters():
    db = get_db()
    doc = db.collection('settings').document('keyword_filters').get()
    keywords = doc.to_dict().get('keywords', []) if doc.exists else []
    return jsonify({'keywords': keywords})


@app.route('/keyword-filters', methods=['POST'])
def add_keyword_filter():
    data = request.get_json()
    keyword = data.get('keyword', '').strip().lower()
    if not keyword:
        return jsonify({'error': 'Missing keyword'}), 400
    db = get_db()
    db.collection('settings').document('keyword_filters').set(
        {'keywords': firestore.ArrayUnion([keyword])}, merge=True
    )
    _backfill(keyword_filter=[keyword])
    user = _req_user(data)
    log_action(user, 'keyword_filter_added', {'keyword': keyword}, actor='user')
    return jsonify({'ok': True})


@app.route('/keyword-filters/<path:keyword>', methods=['DELETE'])
def remove_keyword_filter(keyword):
    db = get_db()
    db.collection('settings').document('keyword_filters').set(
        {'keywords': firestore.ArrayRemove([keyword])}, merge=True
    )
    user = _req_user()
    log_action(user, 'keyword_filter_removed', {'keyword': keyword}, actor='user')
    return jsonify({'ok': True})


@app.route('/blocked-senders', methods=['GET'])
def get_blocked_senders():
    db = get_db()
    doc = db.collection('settings').document('blocked_senders').get()
    addresses = doc.to_dict().get('addresses', []) if doc.exists else []
    return jsonify({'addresses': addresses})


@app.route('/blocked-senders', methods=['POST'])
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


@app.route('/blocked-senders/<path:email>', methods=['DELETE'])
def remove_blocked_sender(email):
    db = get_db()
    db.collection('settings').document('blocked_senders').set(
        {'addresses': firestore.ArrayRemove([email])}, merge=True
    )
    user = _req_user()
    log_action(user, 'sender_unblocked', {'sender': email}, actor='user')
    return jsonify({'ok': True})


# ── Email Intent ─────────────────────────────────────────────────────────────

@app.route('/email-intent', methods=['GET'])
def get_email_intent():
    db = get_db()
    return jsonify({'intent': _get_email_intent(db)})


@app.route('/email-intent', methods=['POST'])
def save_email_intent():
    from datetime import datetime, timezone
    data = request.get_json() or {}
    intent = (data.get('intent') or '').strip()
    db = get_db()
    db.collection('settings').document('email_intent').set({
        'intent': intent,
        'last_updated': datetime.now(timezone.utc).isoformat(),
    })
    user = _req_user(data)
    log_action(user, 'email_intent_saved', {'intent_length': len(intent)}, actor='user')
    return jsonify({'ok': True})


# ── Uncertain email dismiss feedback ──────────────────────────────────────────

@app.route('/emails/<path:email_id>/dismiss-feedback', methods=['POST'])
def dismiss_email_with_feedback(email_id):
    from gcs import read_json, write_json
    from datetime import datetime, timezone
    data = request.get_json() or {}
    reason_type = data.get('reason_type', 'free_text')
    reason_text = data.get('reason_text', '')

    # Dismiss the email
    dismissed = read_json('saucer-dismissed.json', [])
    if email_id not in dismissed:
        dismissed.append(email_id)
        write_json('saucer-dismissed.json', dismissed)

    # Fetch metadata and mark dismissed_by='user' in Firestore
    email_meta = email_store.get_email(email_id) or {}
    if email_meta:
        email_store.update_email_fields(email_id, {'dismissed_by': 'user'})

    # Store feedback in Firestore
    db = get_db()
    db.collection('hana_filter_feedback').add({
        'email_id': email_id,
        'sender': email_meta.get('sender', ''),
        'subject': email_meta.get('subject', ''),
        'verdict_was': email_meta.get('verdict', 'uncertain'),
        'reason_type': reason_type,
        'reason_text': reason_text,
        'timestamp': datetime.now(timezone.utc).isoformat(),
    })

    # Save memory note
    try:
        from memory import save_note
        sender_display = email_meta.get('sender', 'unknown sender')
        subject_display = email_meta.get('subject', 'unknown subject')
        note_content = (
            f"Dismissed email from {sender_display} — subject: '{subject_display}'. "
            f"Reason ({reason_type}): {reason_text}"
        )
        save_note('email filtering feedback', note_content)
    except Exception as e:
        print(f"[dismiss_feedback] save_note error: {e}")

    user = _req_user(data)
    log_action(user, 'email_dismissed_with_feedback', {'email_id': email_id, 'reason_type': reason_type}, actor='user')
    return jsonify({'ok': True})


# ── Emails Hana dismissed ────────────────────────────────────────────────────

@app.route('/emails/hana-dismissed', methods=['GET'])
def get_hana_dismissed_emails():
    """Return emails Hana dismissed (dismissed_by=hana AND verdict=blocked), last 90 days, sorted by date desc."""
    from datetime import datetime, timedelta, timezone
    cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    hana_dismissed = email_store.list_emails_filtered(
        verdict='blocked',
        dismissed_by='hana',
        after_date_iso=cutoff,
        limit=500,
        include_body=False,
    )
    return jsonify({'emails': [{
        'id': e['id'],
        'sender': e.get('sender', ''),
        'subject': e.get('subject', ''),
        'date': e.get('date', ''),
        'reason': e.get('verdict_reason', ''),
    } for e in hana_dismissed]})


# ── Dismissed email review (90-day refresh) ───────────────────────────────────

_dismissed_review_cache = {}


@app.route('/emails/dismissed-review', methods=['GET'])
def get_dismissed_review():
    """Re-evaluate user-dismissed emails from last 90 days against current intent.

    Only shows emails the user explicitly dismissed (dismissed_by='user' or legacy entries
    in saucer-dismissed.json without dismissed_by='hana'). Hana-dismissed emails have their
    own endpoint: GET /emails/hana-dismissed.
    """
    from gcs import read_json
    from email_scanner import evaluate_email_intent
    from datetime import datetime, timedelta, timezone

    db = get_db()
    email_intent = _get_email_intent(db)
    blocked_set = _get_blocked_senders_set(db)
    permitted_list = _get_permitted_senders_list(db)
    excluded_keywords = _get_excluded_keywords(db)

    if not email_intent:
        return jsonify({'emails': [], 'message': 'No intent description set — add one in Email Filters to use this feature.'})

    dismissed_ids = set(read_json('saucer-dismissed.json', []))

    cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    # User-dismissed only (not Hana's verdict=blocked ones); must also be in dismissed list
    candidate_metas = email_store.list_emails_filtered(
        after_date_iso=cutoff,
        dismissed_by_not='hana',
        limit=500,
        include_body=True,
    )
    candidates = [e for e in candidate_metas if e['id'] in dismissed_ids]

    results = []
    permitted_set = set(permitted_list)
    for e in candidates:
        cache_key = f"{e['id']}:{email_intent[:50]}"
        if cache_key in _dismissed_review_cache:
            verdict_info = _dismissed_review_cache[cache_key]
        else:
            verdict_info = evaluate_email_intent(e, email_intent, blocked_set, permitted_set, excluded_keywords=excluded_keywords)
            _dismissed_review_cache[cache_key] = verdict_info

        if verdict_info['verdict'] in ('permitted', 'uncertain'):
            results.append({
                'id': e['id'],
                'sender': e.get('sender', ''),
                'subject': e.get('subject', ''),
                'date': e.get('date', ''),
                'review_verdict': verdict_info['verdict'],
                'review_reason': verdict_info['reason'],
            })

    results.sort(key=lambda x: _parse_date_safe(x.get('date', '')), reverse=True)
    return jsonify({'emails': results[:50]})


@app.route('/emails/<path:email_id>/topic-phrase', methods=['GET'])
def get_email_topic_phrase(email_id):
    """Return a short noun phrase describing the main topic of an email (for dismissal UI)."""
    from email_scanner import extract_topic_noun_phrase
    email = email_store.get_email(email_id)
    if not email:
        return jsonify({'phrase': None})
    try:
        phrase = extract_topic_noun_phrase(email)
        return jsonify({'phrase': phrase})
    except Exception as e:
        print(f"[topic-phrase] error: {e}")
        return jsonify({'phrase': None})


@app.route('/emails/<path:email_id>/highlights', methods=['POST'])
def get_email_highlights(email_id):
    """Return up to 3 short phrases from the email body worth highlighting, given Hana's notes as context."""
    body_text = (request.json or {}).get('body_text', '')
    if not body_text:
        return jsonify({'highlights': []})
    try:
        from gcs import read_json
        import google.generativeai as genai
        notes_data = read_json('hana-notes.json', {})
        notes_text = notes_data.get('notes', '') if isinstance(notes_data, dict) else ''
        context_block = f"Hana's notes about this household:\n{notes_text}\n\n" if notes_text else ''
        prompt = (
            f"{context_block}"
            f"Email body:\n{body_text}\n\n"
            "Identify up to 3 short phrases (2–6 words each) in this email body that are most relevant "
            "to the household context above. Return only a JSON array of exact substrings from the email body. "
            "Example: [\"dentist appointment Thursday\", \"pick up kids\"]. "
            "Return [] if nothing stands out."
        )
        model = genai.GenerativeModel('gemini-2.0-flash')
        response = model.generate_content(prompt)
        import json as _json
        text = response.text.strip()
        if text.startswith('```'):
            text = text.split('```')[1]
            if text.startswith('json'):
                text = text[4:]
        highlights = _json.loads(text)
        if not isinstance(highlights, list):
            highlights = []
        return jsonify({'highlights': highlights[:3]})
    except Exception as ex:
        print(f"[highlights] error: {ex}")
        return jsonify({'highlights': []})


@app.route('/emails/<path:email_id>/restore', methods=['POST'])
def restore_dismissed_email(email_id):
    """Remove an email from the dismissed list to restore it to the inbox."""
    from gcs import read_json, write_json
    from google.cloud.firestore import DELETE_FIELD
    dismissed = read_json('saucer-dismissed.json', [])
    if email_id in dismissed:
        dismissed.remove(email_id)
        write_json('saucer-dismissed.json', dismissed)
    # Clear dismissed_by; reset blocked verdict to uncertain so email reappears
    existing = email_store.get_email(email_id)
    if existing:
        fields = {'dismissed_by': DELETE_FIELD}
        if existing.get('verdict') == 'blocked':
            fields['verdict'] = 'uncertain'
        email_store.update_email_fields(email_id, fields)
    user = _req_user()
    log_action(user, 'email_restored', {'email_id': email_id}, actor='user')
    return jsonify({'ok': True})


@app.route('/emails/<path:email_id>/attachment-file-id', methods=['GET'])
def get_attachment_file_id(email_id):
    """Return file_id for an attachment — fetching from Gmail and saving to GCS if not yet stored."""
    import base64 as _b64
    from gcs import upload_file
    from datetime import datetime, timezone

    filename = request.args.get('filename', '')
    if not filename:
        return jsonify({'error': 'filename required'}), 400

    db = get_db()
    file_id = hashlib.md5(f"{email_id}:{filename}".encode()).hexdigest()
    doc = db.collection('hana_files').document(file_id).get()
    if doc.exists:
        return jsonify({'file_id': file_id})

    # Not in GCS yet — fetch from Gmail now.
    try:
        from gmail_scanner import _build_service, _extract_attachments
        _EXTRACTABLE_MIMES = {'application/pdf', 'image/jpeg', 'image/png', 'image/gif', 'image/webp'}

        service = None
        msg = None
        for token_key in ('GMAIL_REFRESH_TOKEN', 'GMAIL_REFRESH_TOKEN_2'):
            svc = _build_service(token_key)
            if not svc:
                continue
            try:
                msg = svc.users().messages().get(userId='me', messageId=email_id, format='full').execute()
                service = svc
                break
            except Exception:
                continue

        if not msg or not service:
            return jsonify({'error': 'Could not fetch message from Gmail'}), 404

        attachments = _extract_attachments(msg.get('payload', {}), service, 'me', email_id)
        target = next((a for a in attachments if a.get('filename') == filename), None)
        if not target or not target.get('_pdf_bytes_b64'):
            return jsonify({'error': 'Attachment not found in message'}), 404

        mime = target.get('mime', 'application/pdf')
        file_bytes = _b64.b64decode(target['_pdf_bytes_b64'])
        gcs_path = f"files/{file_id}_{filename}"
        if not upload_file(file_bytes, gcs_path, mime):
            return jsonify({'error': 'GCS upload failed'}), 500

        db.collection('hana_files').document(file_id).set({
            'file_id': file_id,
            'filename': filename,
            'source': 'email',
            'email_id': email_id,
            'uploaded_at': datetime.now(timezone.utc).isoformat(),
            'size_bytes': len(file_bytes),
            'gcs_path': gcs_path,
            'content_text': target.get('extracted_text', '')[:8000],
        })
        return jsonify({'file_id': file_id})
    except Exception as ex:
        print(f"[attachment-file-id] on-demand fetch error: {ex}")
        return jsonify({'error': str(ex)}), 500


# ── Relevant Files ────────────────────────────────────────────────────────────

_ALLOWED_FILE_TYPES = {
    'application/pdf': '.pdf',
    'image/jpeg': '.jpg',
    'image/png': '.png',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': '.docx',
}
_MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB


@app.route('/avatar', methods=['POST'])
def upload_avatar_route():
    from gcs import upload_avatar as gcs_upload_avatar
    from flask import Response
    user_email = request.form.get('user') or _req_user()
    f = request.files.get('file')
    if not f:
        return jsonify({'error': 'No file'}), 400
    content_type = f.content_type or 'image/jpeg'
    if content_type not in ('image/jpeg', 'image/png'):
        return jsonify({'error': 'Only JPEG or PNG accepted'}), 400
    image_bytes = f.read()
    if len(image_bytes) > 5_000_000:
        return jsonify({'error': 'Image exceeds 5 MB'}), 400
    path = gcs_upload_avatar(user_email, image_bytes, content_type)
    if not path:
        return jsonify({'error': 'Upload failed'}), 500
    return jsonify({'ok': True})


@app.route('/avatar', methods=['GET'])
def get_avatar_route():
    from gcs import get_avatar as gcs_get_avatar
    from flask import Response
    user_email = request.args.get('user', '')
    if not user_email:
        return jsonify({'error': 'Missing user'}), 400
    image_bytes, content_type = gcs_get_avatar(user_email)
    if image_bytes is None:
        return jsonify({'error': 'No avatar'}), 404
    return Response(image_bytes, status=200, mimetype=content_type or 'image/jpeg')


@app.route('/files', methods=['GET'])
def list_files():
    db = get_db()
    docs = db.collection('hana_files').order_by('uploaded_at', direction=firestore.Query.DESCENDING).stream()
    files = []
    for doc in docs:
        d = doc.to_dict()
        d['file_id'] = doc.id
        d.pop('content_text', None)  # don't send full text in list view
        files.append(d)
    return jsonify({'files': files})


@app.route('/files/upload', methods=['POST'])
def upload_file_endpoint():
    from gcs import upload_file
    from datetime import datetime, timezone
    import uuid as _uuid

    f = request.files.get('file')
    if not f:
        return jsonify({'error': 'No file provided'}), 400

    content_type = f.content_type or 'application/octet-stream'
    if content_type not in _ALLOWED_FILE_TYPES:
        # Try to guess from filename
        fname = f.filename or ''
        ext = fname.rsplit('.', 1)[-1].lower() if '.' in fname else ''
        type_map = {'pdf': 'application/pdf', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg',
                    'png': 'image/png', 'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'}
        content_type = type_map.get(ext, content_type)
        if content_type not in _ALLOWED_FILE_TYPES:
            return jsonify({'error': f'File type not allowed. Supported: PDF, JPG, PNG, DOCX'}), 400

    file_bytes = f.read()
    if len(file_bytes) > _MAX_FILE_BYTES:
        return jsonify({'error': 'File exceeds 10 MB limit'}), 400

    file_id = str(_uuid.uuid4())
    filename = f.filename or f'upload_{file_id}'
    gcs_path = f"files/{file_id}_{filename}"

    if not upload_file(file_bytes, gcs_path, content_type):
        return jsonify({'error': 'Upload failed'}), 500

    # Extract text for PDFs
    content_text = ''
    if content_type == 'application/pdf':
        try:
            import pdfplumber, io as _io
            with pdfplumber.open(_io.BytesIO(file_bytes)) as pdf:
                for page in pdf.pages:
                    content_text += (page.extract_text() or '') + '\n'
            content_text = content_text[:8000]
        except Exception as e:
            print(f"[files] PDF text extraction error: {e}")

    db = get_db()
    db.collection('hana_files').document(file_id).set({
        'file_id': file_id,
        'filename': filename,
        'source': 'upload',
        'uploaded_at': datetime.now(timezone.utc).isoformat(),
        'size_bytes': len(file_bytes),
        'gcs_path': gcs_path,
        'content_text': content_text,
    })

    user = _req_user()
    log_action(user, 'file_uploaded', {'filename': filename, 'size': len(file_bytes)}, actor='user')
    return jsonify({'ok': True, 'file_id': file_id, 'filename': filename})


@app.route('/files/<file_id>/download', methods=['GET'])
def download_file_endpoint(file_id):
    """Proxy file bytes from GCS directly to the browser."""
    from gcs import download_file
    from flask import Response
    db = get_db()
    doc = db.collection('hana_files').document(file_id).get()
    if not doc.exists:
        return jsonify({'error': 'File not found'}), 404
    d = doc.to_dict()
    gcs_path = d.get('gcs_path', '')
    filename = d.get('filename', 'file')
    file_bytes, content_type = download_file(gcs_path)
    if file_bytes is None:
        return jsonify({'error': 'Could not retrieve file'}), 500
    return Response(
        file_bytes,
        status=200,
        mimetype=content_type,
        headers={
            'Content-Disposition': f'inline; filename="{filename}"',
            'Content-Length': str(len(file_bytes)),
        }
    )


@app.route('/files/<file_id>', methods=['DELETE'])
def delete_file_endpoint(file_id):
    from gcs import delete_file
    db = get_db()
    doc = db.collection('hana_files').document(file_id).get()
    if not doc.exists:
        return jsonify({'error': 'File not found'}), 404
    gcs_path = doc.to_dict().get('gcs_path', '')
    delete_file(gcs_path)
    db.collection('hana_files').document(file_id).delete()
    user = _req_user()
    log_action(user, 'file_deleted', {'file_id': file_id}, actor='user')
    return jsonify({'ok': True})


# ── Topic blocking ────────────────────────────────────────────────────────────

def _gemini_text(prompt: str) -> str:
    import google.generativeai as genai
    genai.configure(api_key=os.environ.get("GOOGLE_API_KEY"))
    model = genai.GenerativeModel('gemini-2.5-flash')
    return model.generate_content(prompt).text.strip()


@app.route('/generate-topic-label', methods=['POST'])
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


@app.route('/blocked-topics', methods=['GET'])
def get_blocked_topics():
    db = get_db()
    docs = db.collection('blocked_topics').stream()
    topics = []
    for doc in docs:
        d = doc.to_dict()
        d['id'] = doc.id
        topics.append(d)
    return jsonify({'topics': topics})


@app.route('/blocked-topics', methods=['POST'])
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


@app.route('/blocked-topics/<topic_id>', methods=['DELETE'])
def remove_blocked_topic(topic_id):
    db = get_db()
    db.collection('blocked_topics').document(topic_id).delete()
    user = _req_user()
    log_action(user, 'topic_unblocked', {'id': topic_id}, actor='user')
    return jsonify({'ok': True})




@app.route('/calendar/events', methods=['GET'])
def get_calendar_events():
    from gcalendar import get_events
    start = request.args.get('start')
    end = request.args.get('end')
    if not start or not end:
        return jsonify({'error': 'Missing start or end'}), 400
    try:
        events = get_events(start, end)
        return jsonify({'events': events})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/stats', methods=['GET'])
def get_stats():
    from gcs import read_json
    stats = read_json('saucer-stats.json', {})
    return jsonify({
        'lifetime_tokens': stats.get('lifetime_tokens', 0),
        'chat_messages': stats.get('chat_messages', 0),
    })



@app.route('/emails/<path:email_id>', methods=['GET'])
def get_email_by_id(email_id):
    e = email_store.get_email(email_id)
    if e:
        return jsonify({'email': e})
    return jsonify({'error': 'Not found'}), 404


@app.route('/exclude-keyword-filters', methods=['GET'])
def get_exclude_keyword_filters():
    db = get_db()
    doc = db.collection('settings').document('exclude_keyword_filters').get()
    keywords = doc.to_dict().get('keywords', []) if doc.exists else []
    return jsonify({'keywords': keywords})


@app.route('/exclude-keyword-filters', methods=['POST'])
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


@app.route('/exclude-keyword-filters/<path:keyword>', methods=['DELETE'])
def remove_exclude_keyword_filter(keyword):
    db = get_db()
    db.collection('settings').document('exclude_keyword_filters').set(
        {'keywords': firestore.ArrayRemove([keyword])}, merge=True
    )
    user = _req_user()
    log_action(user, 'exclude_keyword_filter_removed', {'keyword': keyword}, actor='user')
    return jsonify({'ok': True})


@app.route('/calendar/events', methods=['POST'])
def create_calendar_event():
    from gcalendar import create_event_direct
    data = request.get_json()
    title = (data.get('title') or '').strip()
    date_str = data.get('date')
    time_str = data.get('time') or None
    notes = data.get('notes') or None
    if not title or not date_str:
        return jsonify({'error': 'Missing title or date'}), 400
    try:
        event_id = create_event_direct(title, date_str, time_str, notes=notes)
        user = _req_user(data)
        log_action(user, 'calendar_event_added', {'title': title, 'date': date_str}, actor='user')
        return jsonify({'ok': True, 'id': event_id})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/calendar/events/<event_id>', methods=['PUT'])
def update_calendar_event(event_id):
    from gcalendar import update_event
    data = request.get_json()
    try:
        update_event(
            event_id,
            title=data.get('title') or None,
            start_date=data.get('start_date') or None,
            end_date=data.get('end_date') or None,
            time_str=data.get('time') or None,
            notes=data.get('notes'),
        )
        user = _req_user(data)
        log_action(user, 'calendar_event_edited', {'event_id': event_id, 'title': data.get('title')}, actor='user')
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/calendar/events/<event_id>/assignee', methods=['PATCH'])
def patch_calendar_event_assignee(event_id):
    """Update only the assignee of a calendar event without touching title/date/time."""
    from gcalendar import update_event_assignee
    data = request.get_json() or {}
    assignee_label = data.get('assignee_label')  # 'Daniel', 'Emily', 'Both', or None
    try:
        update_event_assignee(event_id, assignee_label)
        user = _req_user(data)
        log_action(user, 'calendar_event_edited',
                   {'event_id': event_id, 'assignee_label': assignee_label}, actor='user')
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/calendar/events/<event_id>', methods=['DELETE'])
def delete_calendar_event(event_id):
    from gcalendar import delete_event
    try:
        delete_event(event_id)
        user = _req_user()
        log_action(user, 'calendar_event_deleted', {'event_id': event_id}, actor='user')
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/user-settings/<user_id>', methods=['GET'])
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


@app.route('/user-settings/<user_id>', methods=['PUT'])
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


@app.route('/actions/recent', methods=['GET'])
def get_actions_recent():
    user = request.args.get('user') or None
    action_type = request.args.get('action_type') or None
    limit = min(int(request.args.get('limit', 20)), 100)
    since = request.args.get('since') or None
    actions = get_recent_actions(user=user, action_type=action_type, limit=limit, since=since)
    return jsonify({'actions': actions})


@app.route('/actions/summary', methods=['GET'])
def get_actions_summary():
    days = int(request.args.get('days', 7))
    summary = get_action_summary(days=days)
    return jsonify({'summary': summary})


@app.route('/decisions/recent', methods=['GET'])
def get_decisions_recent():
    user_email = request.args.get('user_email') or None
    action_type = request.args.get('action_type') or None
    limit = min(int(request.args.get('limit', 20)), 100)
    since = request.args.get('since') or None
    decisions = get_recent_decisions(user_email=user_email, action_type=action_type, limit=limit, since=since)
    return jsonify({'decisions': decisions})


# DEPRECATED — replaced by memory.py knowledge system (passive learning + save_note).
@app.route('/onboarding', methods=['POST'])
def onboarding():
    return jsonify({
        'error': 'This endpoint has been replaced by the Hana memory system. '
                 'Hana now learns about your household through natural conversation.'
    }), 410


@app.route('/conversation-history', methods=['GET'])
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


@app.route('/summarize-conversations', methods=['POST'])
def summarize_conversations():
    from conversation_history import summarize_old_conversations
    count = summarize_old_conversations()
    return jsonify({'summarized': count})



@app.route('/session/checkpoint', methods=['GET'])
def get_session_checkpoint():
    from gcs import read_json
    checkpoint = read_json('saucer-session-checkpoint.json', None)
    return jsonify({'checkpoint': checkpoint})


@app.route('/session/checkpoint', methods=['POST'])
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


@app.route('/email/<path:email_id>/excerpt', methods=['GET'])
def get_email_excerpt(email_id):
    from gcs import read_json
    e = email_store.get_email(email_id)
    if not e:
        return jsonify({'error': 'Not found'}), 404
    body = (e.get('body') or e.get('snippet') or '')[:2000]
    proposals_all = read_json('saucer-proposals.json', {})
    props = proposals_all.get(email_id, [])
    source_spans = list({
        span
        for p in props
        for span in (p.get('source_spans') or [])
        if span
    })
    return jsonify({
        'subject': e.get('subject', ''),
        'sender': e.get('sender', ''),
        'date': e.get('date', ''),
        'body': body,
        'source_spans': source_spans,
    })


@app.route('/debug/config', methods=['GET'])
def debug_config():
    agent_key = os.environ.get('AGENT_KEY', '')
    provided_key = request.headers.get('X-Agent-Key', '')
    if not agent_key or provided_key != agent_key:
        return jsonify({'error': 'Unauthorized'}), 401
    from gcs import read_json
    config = read_json('saucer-config.json', {})
    return jsonify({'config': config})


@app.route('/debug/filters', methods=['GET'])
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


@app.route('/emails/backfill-sender', methods=['POST'])
def backfill_sender():
    agent_key = os.environ.get('AGENT_KEY', '')
    provided_key = request.headers.get('X-Agent-Key', '')
    if not agent_key or provided_key != agent_key:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json() or {}
    sender = (data.get('sender') or '').strip().lower()
    if not sender:
        return jsonify({'error': 'Missing sender'}), 400

    print(f"[backfill-sender] starting 90-day backfill for sender={sender!r}")
    _backfill(sender_filter=[sender])
    print(f"[backfill-sender] done for sender={sender!r}")
    return jsonify({'ok': True, 'sender': sender})


@app.route('/hana/question', methods=['GET'])
def get_hana_question():
    """Return the current queued question if ready. Frontend polls this."""
    from memory import get_queued_question
    q = get_queued_question()
    if not q:
        return jsonify({"has_question": False})
    return jsonify({
        "has_question": True,
        "question": q["question"],
        "queued_at": q["queued_at"].isoformat() if hasattr(q["queued_at"], "isoformat") else str(q["queued_at"])
    })


@app.route('/hana/question/snooze', methods=['POST'])
def snooze_hana_question():
    """Called when user opens chat to talk about something else."""
    from memory import snooze_question
    return jsonify(snooze_question(days=3))


@app.route('/hana/question/clear', methods=['POST'])
def clear_hana_question():
    from memory import clear_question
    return jsonify(clear_question())


@app.route('/hana/notes', methods=['GET'])
def get_hana_notes():
    """Return all notes for display in the UI, excluding internal filtering-feedback entries."""
    from memory import list_notes
    notes = list_notes()
    filtered = [
        n for n in notes
        if 'email filtering' not in n.get('topic', '').lower()
        and 'filtering feedback' not in n.get('topic', '').lower()
    ]
    return jsonify({"notes": filtered})


@app.route('/hana/notes/<topic_slug>', methods=['DELETE'])
def delete_hana_note(topic_slug):
    from memory import delete_note
    return jsonify(delete_note(topic_slug))


@app.route('/hana/notes/<topic_slug>/revert', methods=['POST'])
def revert_hana_note(topic_slug):
    from memory import revert_note
    from logger import log_action
    result = revert_note(topic_slug)
    if result.get('status') == 'ok':
        log_action('system', 'note_reverted', {'topic_slug': topic_slug})
    return jsonify(result)


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
