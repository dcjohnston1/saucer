import os
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
    blocked_senders = set(blocked_doc.to_dict().get('addresses', []) if blocked_doc.exists else [])
    if blocked_senders:
        visible = [e for e in visible if e.get('sender', '') not in blocked_senders]

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
    blocked_senders = set(blocked_doc.to_dict().get('addresses', []) if blocked_doc.exists else [])
    if blocked_senders:
        visible = [e for e in visible if e.get('sender', '') not in blocked_senders]

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
    blocked_senders = set(blocked_doc.to_dict().get('addresses', []) if blocked_doc.exists else [])
    if blocked_senders:
        visible = [e for e in visible if e.get('sender', '') not in blocked_senders]

    proposals_data = read_json('saucer-proposals.json', {})
    for e in visible:
        all_props = proposals_data.get(e['id'])
        if all_props is not None:
            e['proposals'] = [p for p in all_props if not p.get('dismissed') and not p.get('accepted')]
    return jsonify({'emails': visible, 'synced': len(new_emails)})


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


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
