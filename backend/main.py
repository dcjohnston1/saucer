import os
import re
import uuid
from flask import Flask, request, jsonify
from flask_cors import CORS
from google.cloud import firestore
from mediator import process_message
from logger import log_action, get_recent_actions, get_action_summary, get_recent_decisions
from prompts import ONBOARDING_SYSTEM_PROMPT

app = Flask(__name__)
CORS(app)

def get_db():
    return firestore.Client(project='mediationmate')


def _extract_sender_addr(sender_str: str) -> str:
    """Return the bare email address from a From: header, lowercased."""
    m = re.search(r'<([^>]+)>', sender_str)
    return m.group(1).lower() if m else sender_str.lower()


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


def _backfill(sender_filter=None, keyword_filter=None):
    """Scan the last 90 days for a newly added sender or keyword and merge into stored emails."""
    try:
        from gmail_scanner import scan_emails
        from gcs import read_json, write_json
        from datetime import datetime, timedelta, timezone
        after_ts = (datetime.now(timezone.utc) - timedelta(days=90)).timestamp()
        new_emails = scan_emails(
            sender_filter=sender_filter,
            keyword_filter=keyword_filter,
            after_timestamp=after_ts
        )
        if new_emails:
            stored = read_json('saucer-emails.json', [])
            new_ids = {e['id'] for e in new_emails}
            merged = new_emails + [e for e in stored if e['id'] not in new_ids]
            write_json('saucer-emails.json', merged)
    except Exception as e:
        print(f"Backfill error: {e}")


@app.route('/chat', methods=['POST'])
def chat():
    data = request.get_json()
    user = data.get('user')
    user_email = data.get('user_email') or user
    message = data.get('message')
    conversation_id = data.get('conversation_id') or str(uuid.uuid4())

    if not user or not message:
        return jsonify({'error': 'Missing user or message'}), 400

    history = data.get('history', [])
    reply = process_message(user, message, history, user_email=user_email, conversation_id=conversation_id)
    return jsonify({
        'reply': reply,
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
    from email_scanner import scan_emails_for_todos
    from gcs import read_json, write_json
    from datetime import datetime, timedelta, timezone

    db = get_db()
    doc = db.collection('settings').document('email_filters').get()
    filters = doc.to_dict().get('addresses', []) if doc.exists else []

    config = read_json('saucer-config.json', {})
    last_sync = config.get('last_sync_timestamp')

    if last_sync is None:
        after_ts = (datetime.now(timezone.utc) - timedelta(days=90)).timestamp()
    else:
        after_ts = last_sync

    kw_doc = db.collection('settings').document('keyword_filters').get()
    keywords = kw_doc.to_dict().get('keywords', []) if kw_doc.exists else []

    # Always include self-sent emails (from:me = from the authenticated account)
    effective_filters = (filters + ['me']) if filters else None
    new_emails = scan_emails(
        sender_filter=effective_filters,
        keyword_filter=keywords if keywords else None,
        after_timestamp=after_ts
    )

    stored = read_json('saucer-emails.json', [])
    new_ids = {e['id'] for e in new_emails}
    merged = new_emails + [e for e in stored if e['id'] not in new_ids]

    # Apply 60-day TTL: drop dismissed emails older than 60 days
    dismissed_set = set(read_json('saucer-dismissed.json', []))
    ttl_cutoff = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
    merged = [
        e for e in merged
        if e['id'] not in dismissed_set or (e.get('date') or '') >= ttl_cutoff
    ]

    write_json('saucer-emails.json', merged)

    config['last_sync_timestamp'] = datetime.now(timezone.utc).timestamp()
    write_json('saucer-config.json', config)

    # Generate summaries for emails that lack one or have a vague/short one (cap at 5 per request)
    to_summarize = [e for e in merged if _is_vague_summary(e.get('summary'))][:5]
    if to_summarize:
        from email_scanner import summarize_emails
        summaries = summarize_emails(to_summarize)
        if summaries:
            for e in merged:
                if e['id'] in summaries:
                    e['summary'] = summaries[e['id']]
            write_json('saucer-emails.json', merged)

    # Apply exclude keywords
    excl_doc = db.collection('settings').document('exclude_keyword_filters').get()
    exclude_keywords = excl_doc.to_dict().get('keywords', []) if excl_doc.exists else []
    print(f"[/emails] exclude_keywords: {exclude_keywords}")

    dismissed = set(read_json('saucer-dismissed.json', []))
    reviewed = set(read_json('saucer-reviewed.json', []))
    visible = [e for e in merged if e['id'] not in dismissed and e['id'] not in reviewed]

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

    blocked_doc = db.collection('settings').document('blocked_senders').get()
    blocked_senders = {a.lower() for a in blocked_doc.to_dict().get('addresses', [])} if blocked_doc.exists else set()
    if blocked_senders:
        visible = [e for e in visible if _extract_sender_addr(e.get('sender', '')) not in blocked_senders
                   and e.get('sender', '').lower() not in blocked_senders]

    blocked_topics_by_sender = _load_blocked_topics_by_sender(db)
    if blocked_topics_by_sender:
        visible = [e for e in visible if not _topic_blocked(e, blocked_topics_by_sender)]

    # Scan unscanned emails for to-do proposals (cap at 10 per request)
    scanned = set(read_json('saucer-scanned.json', []))
    proposals = read_json('saucer-proposals.json', {})
    to_scan = [e for e in visible if e['id'] not in scanned][:10]
    if to_scan:
        new_proposals = scan_emails_for_todos(to_scan)
        # Deduplicate: skip proposals whose title already exists in proposals or the Google Doc
        from gdocs import read_doc as _read_doc
        doc_content = _read_doc()
        doc_titles = set()
        for _line in doc_content.split('\n'):
            _parts = [x.strip() for x in _line.split('|')]
            if len(_parts) > 1 and _line.strip():
                doc_titles.add(_parts[1].strip().lower())
        existing_titles = {p['title'].strip().lower() for plist in proposals.values() for p in plist} | doc_titles
        for email_id, plist in new_proposals.items():
            deduped = []
            for p in plist:
                norm = p['title'].strip().lower()
                if norm not in existing_titles:
                    deduped.append(p)
                    existing_titles.add(norm)
            proposals.setdefault(email_id, []).extend(deduped)
        for e in to_scan:
            scanned.add(e['id'])
            proposals.setdefault(e['id'], [])
        write_json('saucer-proposals.json', proposals)
        write_json('saucer-scanned.json', list(scanned))

    for e in visible:
        all_props = proposals.get(e['id'])
        if all_props is not None:
            e['proposals'] = [p for p in all_props if not p.get('dismissed') and not p.get('accepted')]

    return jsonify({'emails': visible})


@app.route('/emails/cached', methods=['GET'])
def get_cached_emails():
    """Return stored emails from GCS without triggering a Gmail scan."""
    from gcs import read_json

    stored = read_json('saucer-emails.json', [])
    dismissed = set(read_json('saucer-dismissed.json', []))
    reviewed = set(read_json('saucer-reviewed.json', []))
    visible = [e for e in stored if e['id'] not in dismissed and e['id'] not in reviewed]

    db = get_db()

    excl_doc = db.collection('settings').document('exclude_keyword_filters').get()
    exclude_keywords = excl_doc.to_dict().get('keywords', []) if excl_doc.exists else []
    if exclude_keywords:
        def _matches_exclude_cached(e):
            haystack = ' '.join([
                e.get('subject', ''),
                e.get('sender', ''),
                (e.get('body', '') or e.get('snippet', ''))[:500],
            ]).lower()
            return any(kw in haystack for kw in exclude_keywords)
        visible = [e for e in visible if not _matches_exclude_cached(e)]

    blocked_doc = db.collection('settings').document('blocked_senders').get()
    blocked_senders = {a.lower() for a in blocked_doc.to_dict().get('addresses', [])} if blocked_doc.exists else set()
    if blocked_senders:
        visible = [e for e in visible if _extract_sender_addr(e.get('sender', '')) not in blocked_senders
                   and e.get('sender', '').lower() not in blocked_senders]

    proposals = read_json('saucer-proposals.json', {})
    for e in visible:
        all_props = proposals.get(e['id'])
        if all_props is not None:
            e['proposals'] = [p for p in all_props if not p.get('dismissed') and not p.get('accepted')]

    return jsonify({'emails': visible})


@app.route('/emails/resync', methods=['POST'])
def resync_emails():
    """Force a 90-day re-scan regardless of last_sync_timestamp."""
    from gmail_scanner import scan_emails
    from email_scanner import scan_emails_for_todos
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

    stored = read_json('saucer-emails.json', [])
    new_ids = {e['id'] for e in new_emails}
    merged = new_emails + [e for e in stored if e['id'] not in new_ids]
    write_json('saucer-emails.json', merged)

    config = read_json('saucer-config.json', {})
    config['last_sync_timestamp'] = datetime.now(timezone.utc).timestamp()
    write_json('saucer-config.json', config)

    dismissed = set(read_json('saucer-dismissed.json', []))
    reviewed = set(read_json('saucer-reviewed.json', []))
    visible = [e for e in merged if e['id'] not in dismissed and e['id'] not in reviewed]

    excl_doc = db.collection('settings').document('exclude_keyword_filters').get()
    exclude_keywords = excl_doc.to_dict().get('keywords', []) if excl_doc.exists else []
    if exclude_keywords:
        def _matches_exclude_resync(e):
            haystack = ' '.join([
                e.get('subject', ''),
                e.get('sender', ''),
                (e.get('body', '') or e.get('snippet', ''))[:500],
            ]).lower()
            return any(kw in haystack for kw in exclude_keywords)
        visible = [e for e in visible if not _matches_exclude_resync(e)]

    blocked_doc = db.collection('settings').document('blocked_senders').get()
    blocked_senders = {a.lower() for a in blocked_doc.to_dict().get('addresses', [])} if blocked_doc.exists else set()
    if blocked_senders:
        visible = [e for e in visible if _extract_sender_addr(e.get('sender', '')) not in blocked_senders
                   and e.get('sender', '').lower() not in blocked_senders]

    proposals_data = read_json('saucer-proposals.json', {})
    for e in visible:
        all_props = proposals_data.get(e['id'])
        if all_props is not None:
            e['proposals'] = [p for p in all_props if not p.get('dismissed') and not p.get('accepted')]
    return jsonify({'emails': visible, 'synced': len(new_emails)})


# DEPRECATED: proposals flow replaced by direct Google Doc writes with source:ai-suggested
# TODO: remove in next sprint once inline email proposals are also removed from frontend
@app.route('/proposals', methods=['GET'])
def get_proposals():
    from gcs import read_json

    proposals = read_json('saucer-proposals.json', {})
    emails = read_json('saucer-emails.json', [])
    email_meta = {e['id']: {'subject': e.get('subject', ''), 'sender': e.get('sender', '')} for e in emails}

    active = []
    for email_id, plist in proposals.items():
        meta = email_meta.get(email_id, {})
        for p in plist:
            if not p.get('dismissed') and not p.get('accepted'):
                active.append({
                    'id': p['id'],
                    'title': p['title'],
                    'notes': p.get('notes', ''),
                    'date_expression': p.get('date_expression', ''),
                    'email_subject': meta.get('subject', ''),
                    'email_sender': meta.get('sender', ''),
                })

    return jsonify({'proposals': active})


# DEPRECATED: see /proposals GET above
@app.route('/proposals/<proposal_id>/accept', methods=['POST'])
def accept_proposal(proposal_id):
    from gcs import read_json, write_json
    from mediator import add_todo
    from gdocs import read_doc

    data = request.get_json() or {}
    assignee = data.get('assignee') or None

    proposals = read_json('saucer-proposals.json', {})
    for email_id, plist in proposals.items():
        for p in plist:
            if p['id'] == proposal_id:
                # Check for duplicate in Google Doc before appending
                doc = read_doc()
                title_norm = p['title'].strip().lower()
                already_exists = any(
                    len(parts) > 1 and parts[1].strip().lower() == title_norm
                    for parts in ([x.strip() for x in line.split('|')] for line in doc.split('\n') if line.strip())
                )
                if not already_exists:
                    add_todo(
                        title=p['title'],
                        date_expression=p.get('date_expression') or None,
                        notes=p.get('notes') or None,
                        assignee=assignee,
                        source_email_id=email_id,
                    )
                if p.get('date_expression'):
                    try:
                        from gcalendar import create_event
                        label_map = {
                            'dcjohnston1@gmail.com': 'Daniel',
                            'emily.osteen.johnston@gmail.com': 'Emily',
                            'both': 'Both',
                        }
                        assignee_label = label_map.get(assignee, assignee)
                        create_event(
                            title=p['title'],
                            date_expression=p['date_expression'],
                            notes=p.get('notes'),
                            assignee_label=assignee_label
                        )
                    except Exception as e:
                        print(f"Calendar event creation failed: {e}")
                p['accepted'] = True
                write_json('saucer-proposals.json', proposals)
                user = _req_user(data)
                log_action(user, 'proposal_accepted', {'proposal_id': proposal_id, 'title': p['title'], 'assignee': assignee}, actor='user')
                return jsonify({'ok': True})

    return jsonify({'error': 'Proposal not found'}), 404


# DEPRECATED: see /proposals GET above
@app.route('/proposals/<proposal_id>', methods=['DELETE'])
def dismiss_proposal(proposal_id):
    from gcs import read_json, write_json

    proposals = read_json('saucer-proposals.json', {})
    for email_id, plist in proposals.items():
        for p in plist:
            if p['id'] == proposal_id:
                p['dismissed'] = True
                write_json('saucer-proposals.json', proposals)
                user = _req_user()
                log_action(user, 'proposal_dismissed', {'proposal_id': proposal_id, 'title': p['title']}, actor='user')
                return jsonify({'ok': True})

    return jsonify({'error': 'Proposal not found'}), 404


@app.route('/emails/<email_id>/dismiss', methods=['DELETE'])
def dismiss_email(email_id):
    from gcs import read_json, write_json
    dismissed = read_json('saucer-dismissed.json', [])
    if email_id not in dismissed:
        dismissed.append(email_id)
        write_json('saucer-dismissed.json', dismissed)
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
    from gcs import read_json
    reviewed_ids = read_json('saucer-reviewed.json', [])
    all_emails = read_json('saucer-emails.json', [])
    email_map = {e['id']: e for e in all_emails}
    result = [email_map[rid] for rid in reviewed_ids if rid in email_map]
    return jsonify({'emails': result[:30]})


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


def _load_blocked_topics_by_sender(db):
    """Return dict mapping sender -> list of labels for topic-blocked senders."""
    docs = db.collection('blocked_topics').stream()
    by_sender = {}
    for doc in docs:
        d = doc.to_dict()
        sender = d.get('sender', '').lower()
        if sender:
            by_sender.setdefault(sender, []).append(d.get('label', ''))
    return by_sender


def _topic_blocked(email_dict, blocked_topics_by_sender) -> bool:
    """Return True if the email matches any blocked topic rule for its sender."""
    sender = email_dict.get('sender', '').lower()
    if not sender:
        return False
    labels = blocked_topics_by_sender.get(sender, [])
    if not labels:
        return False
    subject = email_dict.get('subject', '')
    preview = (email_dict.get('body') or email_dict.get('snippet') or '')[:300]
    for label in labels:
        prompt = (
            f"Does this email match the topic '{label}'? "
            f"Subject: '{subject}'. Preview: '{preview}'. "
            f"Answer only yes or no."
        )
        answer = _gemini_text(prompt).lower()
        if answer.startswith('yes'):
            return True
    return False


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
    from gcs import read_json
    emails = read_json('saucer-emails.json', [])
    for e in emails:
        if e['id'] == email_id:
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


@app.route('/onboarding', methods=['POST'])
def onboarding():
    import google.generativeai as genai
    from datetime import datetime, timezone
    data = request.get_json()
    user_email = data.get('user_email', '')
    message = data.get('message', '')
    history = data.get('history', [])

    db = get_db()
    saved_profile = {}

    def save_household_profile(
        family_members: str,
        shopping_habits: str,
        role_division: str,
        communication_preferences: str,
    ) -> dict:
        """Save the household profile gathered during the onboarding conversation.

        Args:
            family_members: Description of family members (names, ages, interests).
            shopping_habits: Shopping preferences and habits.
            role_division: Who handles what in the household.
            communication_preferences: How they prefer to communicate and be notified.
        """
        db.collection('household_profile').document(user_email).set({
            'family_members': family_members,
            'shopping_habits': shopping_habits,
            'role_division': role_division,
            'communication_preferences': communication_preferences,
            'updated_at': datetime.now(timezone.utc).isoformat(),
        })
        saved_profile['saved'] = True
        return {"message": "Profile saved!"}

    genai.configure(api_key=os.environ.get("GOOGLE_API_KEY"))

    chat_history = []
    for m in history:
        role = 'user' if m['role'] == 'user' else 'model'
        chat_history.append({'role': role, 'parts': [m['content']]})

    model = genai.GenerativeModel(
        model_name='gemini-2.5-flash',
        system_instruction=ONBOARDING_SYSTEM_PROMPT,
        tools=[save_household_profile],
    )
    chat = model.start_chat(history=chat_history, enable_automatic_function_calling=True)

    user_msg = message.strip() if message.strip() else "Let's get started."
    response = chat.send_message(user_msg)

    return jsonify({
        'reply': response.text,
        'complete': saved_profile.get('saved', False),
    })


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


@app.route('/agent/run', methods=['POST'])
def agent_run():
    agent_key = os.environ.get('AGENT_KEY', '')
    provided_key = request.headers.get('X-Agent-Key', '')
    if not agent_key or provided_key != agent_key:
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        from agent import run_morning_agent
        briefing_id = run_morning_agent()
        return jsonify({'status': 'ok', 'briefing_id': briefing_id})
    except Exception as e:
        import traceback
        print(f'[main] agent_run error: {traceback.format_exc()}')
        return jsonify({'error': str(e)}), 500


@app.route('/briefing/latest', methods=['GET'])
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

    is_dan = user_email == 'dcjohnston1@gmail.com'
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


@app.route('/briefing/<briefing_id>/feedback', methods=['POST'])
def briefing_feedback(briefing_id):
    from datetime import datetime, timezone
    data = request.get_json(force=True) or {}
    user_email = data.get('user_email', '')
    rating = data.get('rating', '')
    if not user_email or rating not in ('positive', 'negative'):
        return jsonify({'error': 'Missing or invalid user_email / rating'}), 400

    is_dan = user_email == 'dcjohnston1@gmail.com'
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


@app.route('/briefing/<briefing_id>/seen', methods=['POST'])
def mark_briefing_seen(briefing_id):
    data = request.get_json(force=True) or {}
    user_email = data.get('user_email', '')
    if not user_email:
        return jsonify({'error': 'Missing user_email'}), 400
    is_dan = user_email == 'dcjohnston1@gmail.com'
    seen_field = 'dan_seen' if is_dan else 'emily_seen'
    db = get_db()
    db.collection('morning_briefings').document(briefing_id).update({seen_field: True})
    return jsonify({'ok': True})


@app.route('/agent/email-trigger', methods=['POST'])
def agent_email_trigger():
    """Pub/Sub push webhook — fires when Gmail delivers a new message notification."""
    import base64 as _base64
    import json as _json
    import threading

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

    _DAN = 'dcjohnston1@gmail.com'
    _EMILY = 'emily.osteen.johnston@gmail.com'

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
                        _resp = setup_gmail_watch(_svc, 'projects/mediationmate/topics/saucer-gmail-push')
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
            resp = setup_gmail_watch(service, 'projects/mediationmate/topics/saucer-gmail-push')
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

    # Merge into stored emails so they appear in the app immediately
    stored = read_json('saucer-emails.json', [])
    existing_ids = {e['id'] for e in stored}
    fresh = [e for e in new_emails if e['id'] not in existing_ids]
    if fresh:
        write_json('saucer-emails.json', fresh + stored)
    print(f"[email-trigger] merged {len(fresh)} new emails into saucer-emails.json, total now {len(fresh) + len(stored)}")

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

    blocked_topics_by_sender = _load_blocked_topics_by_sender(db)

    def _sender_matches(sender_str):
        raw = sender_str.lower()
        addr = _extract_sender_addr(sender_str)
        matched = any(f in raw or f in addr for f in sender_filters)
        print(f"[email-trigger] _sender_matches raw={raw!r} addr={addr!r} filters={sender_filters} -> {matched}")
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
        blocked_lower = {b.lower() for b in blocked_senders}
        print(f"[email-trigger] _is_excluded check addr={addr!r} blocked_lower={blocked_lower}")
        if any(b in raw or b in addr for b in blocked_lower):
            return True
        if exclude_keywords:
            haystack = ' '.join([
                email_dict.get('subject', ''),
                email_dict.get('sender', ''),
                (email_dict.get('body', '') or email_dict.get('snippet', ''))[:500],
            ]).lower()
            if any(kw in haystack for kw in exclude_keywords):
                return True
        if _topic_blocked(email_dict, blocked_topics_by_sender):
            return True
        return False

    for email in new_emails:
        subj = email.get('subject', '(no subject)')
        if _is_excluded(email):
            print(f"[email-trigger] excluded: {subj}")
            continue
        if not (_sender_matches(email.get('sender', '')) or _keyword_matches(email)):
            print(f"[email-trigger] no filter match, skipping: {subj}")
            continue

        print(f"[email-trigger] qualifying — spawning agent for: {subj}")

        def _process(e=email):
            try:
                from agent import process_single_email
                process_single_email(e)
            except Exception as ex:
                print(f"[email-trigger] process_single_email error: {ex}")

        threading.Thread(target=_process, daemon=False).start()

    return jsonify({'ok': True})


@app.route('/agent/renew-gmail-watch', methods=['POST'])
def renew_gmail_watch():
    """Renew Gmail push watch for all configured accounts. Called by Cloud Scheduler every 6 days."""
    agent_key = os.environ.get('AGENT_KEY', '')
    provided_key = request.headers.get('X-Agent-Key', '')
    if not agent_key or provided_key != agent_key:
        return jsonify({'error': 'Unauthorized'}), 401

    topic = 'projects/mediationmate/topics/saucer-gmail-push'
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
    emails = read_json('saucer-emails.json', [])
    for e in emails:
        if e['id'] == email_id:
            body = (e.get('body') or e.get('snippet') or '')[:2000]
            return jsonify({
                'subject': e.get('subject', ''),
                'sender': e.get('sender', ''),
                'date': e.get('date', ''),
                'body': body,
            })
    return jsonify({'error': 'Not found'}), 404


@app.route('/debug/config', methods=['GET'])
def debug_config():
    agent_key = os.environ.get('AGENT_KEY', '')
    provided_key = request.headers.get('X-Agent-Key', '')
    if not agent_key or provided_key != agent_key:
        return jsonify({'error': 'Unauthorized'}), 401
    from gcs import read_json
    config = read_json('saucer-config.json', {})
    return jsonify({'config': config})


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
