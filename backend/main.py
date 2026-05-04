import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from google.cloud import firestore
from mediator import process_message

app = Flask(__name__)
CORS(app)

def get_db():
    return firestore.Client(project='mediationmate')


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
    message = data.get('message')

    if not user or not message:
        return jsonify({'error': 'Missing user or message'}), 400

    history = data.get('history', [])
    reply = process_message(user, message, history)
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

    new_emails = scan_emails(
        sender_filter=filters if filters else None,
        keyword_filter=keywords if keywords else None,
        after_timestamp=after_ts
    )

    stored = read_json('saucer-emails.json', [])
    new_ids = {e['id'] for e in new_emails}
    merged = new_emails + [e for e in stored if e['id'] not in new_ids]

    write_json('saucer-emails.json', merged)

    config['last_sync_timestamp'] = datetime.now(timezone.utc).timestamp()
    write_json('saucer-config.json', config)

    dismissed = set(read_json('saucer-dismissed.json', []))
    visible = [e for e in merged if e['id'] not in dismissed]

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
    new_emails = scan_emails(
        sender_filter=filters if filters else None,
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
    visible = [e for e in merged if e['id'] not in dismissed]
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
                        assignee=assignee
                    )
                p['accepted'] = True
                write_json('saucer-proposals.json', proposals)
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
                return jsonify({'ok': True})

    return jsonify({'error': 'Proposal not found'}), 404


@app.route('/emails/<email_id>/dismiss', methods=['DELETE'])
def dismiss_email(email_id):
    from gcs import read_json, write_json
    dismissed = read_json('saucer-dismissed.json', [])
    if email_id not in dismissed:
        dismissed.append(email_id)
        write_json('saucer-dismissed.json', dismissed)
    return jsonify({'ok': True})


@app.route('/doc/task', methods=['DELETE'])
def complete_task():
    data = request.get_json()
    title = data.get('title')
    if not title:
        return jsonify({'error': 'Missing title'}), 400
    from gdocs import complete_task as gdocs_complete_task
    gdocs_complete_task(title)
    return jsonify({'ok': True})


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
    return jsonify({'ok': True})


@app.route('/email-filters/<path:email>', methods=['DELETE'])
def remove_email_filter(email):
    db = get_db()
    db.collection('settings').document('email_filters').set(
        {'addresses': firestore.ArrayRemove([email])}, merge=True
    )
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
    return jsonify({'ok': True})


@app.route('/keyword-filters/<path:keyword>', methods=['DELETE'])
def remove_keyword_filter(keyword):
    db = get_db()
    db.collection('settings').document('keyword_filters').set(
        {'keywords': firestore.ArrayRemove([keyword])}, merge=True
    )
    return jsonify({'ok': True})


@app.route('/stats', methods=['GET'])
def get_stats():
    from gcs import read_json
    stats = read_json('saucer-stats.json', {})
    return jsonify({
        'lifetime_tokens': stats.get('lifetime_tokens', 0),
        'chat_messages': stats.get('chat_messages', 0),
    })


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
