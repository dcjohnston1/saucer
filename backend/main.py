import hashlib
import os
import re
import uuid
from flask import Flask, request, jsonify
from flask_cors import CORS
from google.cloud import firestore
from mediator import process_message
from logger import log_action, get_recent_actions, get_action_summary, get_recent_decisions

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


def _get_email_intent(db) -> str:
    """Load email_intent string from Firestore settings."""
    try:
        doc = db.collection('settings').document('email_intent').get()
        return (doc.to_dict() or {}).get('intent', '') if doc.exists else ''
    except Exception as e:
        print(f"[email_intent] load error: {e}")
        return ''


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


def _auto_save_pdf_attachments(emails, db):
    """For permitted emails with raw attachment bytes, save to GCS and write Firestore metadata.

    Uses a deterministic document ID (MD5 of email_id:filename) so reprocessing
    the same email is idempotent — no duplicate entries, no composite index needed.
    """
    from gcs import upload_file
    from datetime import datetime, timezone

    for e in emails:
        if e.get('verdict') != 'permitted':
            continue
        for att in e.get('attachments', []):
            b64 = att.pop('_pdf_bytes_b64', None)
            size = att.pop('_file_size', att.pop('_pdf_size', 0))
            if not b64:
                continue
            try:
                filename = att['filename']
                content_type = att.get('mime', 'application/pdf')
                file_id = hashlib.md5(f"{e['id']}:{filename}".encode()).hexdigest()
                gcs_path = f"files/{file_id}_{filename}"
                file_bytes = __import__('base64').b64decode(b64)
                if not upload_file(file_bytes, gcs_path, content_type):
                    continue
                db.collection('hana_files').document(file_id).set({
                    'file_id': file_id,
                    'filename': filename,
                    'source': 'email',
                    'email_id': e['id'],
                    'uploaded_at': datetime.now(timezone.utc).isoformat(),
                    'size_bytes': size,
                    'gcs_path': gcs_path,
                    'content_text': att.get('extracted_text', '')[:8000],
                })
                att['file_id'] = file_id
                print(f"[files] auto-saved {filename} from email {e['id']}")
            except Exception as ex:
                print(f"[files] auto-save error for {att.get('filename')}: {ex}")


def _strip_raw_bytes(emails):
    """Remove in-memory attachment bytes before writing emails to GCS."""
    for e in emails:
        for att in e.get('attachments', []):
            att.pop('_pdf_bytes_b64', None)
            att.pop('_file_size', None)
            att.pop('_pdf_size', None)


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
    from email_scanner import scan_emails_for_todos
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

    config['last_sync_timestamp'] = datetime.now(timezone.utc).timestamp()
    write_json('saucer-config.json', config)

    # Intent-based filtering: evaluate emails that don't have a verdict yet
    email_intent = _get_email_intent(db)
    blocked_set = _get_blocked_senders_set(db)
    permitted_list = _get_permitted_senders_list(db)
    excluded_keywords = _get_excluded_keywords(db)
    _run_intent_eval_batch(merged, email_intent, blocked_set, permitted_list, excluded_keywords=excluded_keywords)

    # Auto-save PDF attachments from newly permitted emails (needs raw bytes)
    _auto_save_pdf_attachments(merged, db)

    # Strip raw bytes and write to GCS
    _strip_raw_bytes(merged)
    write_json('saucer-emails.json', merged)

    # Generate summaries for emails that lack one or have a vague/short one (cap at 10 per request)
    to_summarize = [e for e in merged if _is_vague_summary(e.get('summary'))][:10]
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

    # Hard block: blocked senders always hidden
    if blocked_set:
        visible = [e for e in visible if _extract_sender_addr(e.get('sender', '')) not in blocked_set
                   and e.get('sender', '').lower() not in blocked_set]

    # Intent verdict: only show permitted and uncertain (hide blocked)
    visible = [e for e in visible if e.get('verdict', 'permitted') != 'blocked']

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

    blocked_set = _get_blocked_senders_set(db)
    if blocked_set:
        visible = [e for e in visible if _extract_sender_addr(e.get('sender', '')) not in blocked_set
                   and e.get('sender', '').lower() not in blocked_set]

    # Intent verdict: only show permitted and uncertain
    visible = [e for e in visible if e.get('verdict', 'permitted') != 'blocked']

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

    config = read_json('saucer-config.json', {})
    config['last_sync_timestamp'] = datetime.now(timezone.utc).timestamp()
    write_json('saucer-config.json', config)

    # Force re-evaluate ALL emails against current intent (not just new/unverdicted ones)
    email_intent = _get_email_intent(db)
    blocked_set = _get_blocked_senders_set(db)
    permitted_list = _get_permitted_senders_list(db)
    excluded_keywords = _get_excluded_keywords(db)
    eval_counts = _force_reevaluate_all_emails(merged, email_intent, excluded_keywords, blocked_set, set(permitted_list))
    print(f"[resync] re-eval complete: {eval_counts}")
    _auto_save_pdf_attachments(merged, db)
    _strip_raw_bytes(merged)
    write_json('saucer-emails.json', merged)

    dismissed = set(read_json('saucer-dismissed.json', []))
    reviewed = set(read_json('saucer-reviewed.json', []))
    visible = [e for e in merged if e['id'] not in dismissed and e['id'] not in reviewed]

    # excluded_keywords already applied during _force_reevaluate_all_emails; use verdict to filter
    if blocked_set:
        visible = [e for e in visible if _extract_sender_addr(e.get('sender', '')) not in blocked_set
                   and e.get('sender', '').lower() not in blocked_set]

    visible = [e for e in visible if e.get('verdict', 'permitted') != 'blocked']

    proposals_data = read_json('saucer-proposals.json', {})
    for e in visible:
        all_props = proposals_data.get(e['id'])
        if all_props is not None:
            e['proposals'] = [p for p in all_props if not p.get('dismissed') and not p.get('accepted')]
    return jsonify({'emails': visible, 'synced': len(new_emails), 'eval_counts': eval_counts})


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
                            assignee_label=assignee_label,
                            source_email_id=email_id,
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
    # Mark dismissed_by='user' on the email object
    emails = read_json('saucer-emails.json', [])
    for e in emails:
        if e['id'] == email_id:
            e['dismissed_by'] = 'user'
            write_json('saucer-emails.json', emails)
            break
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

    all_emails = read_json('saucer-emails.json', [])
    email_map = {e['id']: e for e in all_emails}

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

    # Find email metadata and mark dismissed_by='user'
    emails = read_json('saucer-emails.json', [])
    email_meta = {}
    for e in emails:
        if e['id'] == email_id:
            email_meta = e
            e['dismissed_by'] = 'user'
            break
    if email_meta:
        write_json('saucer-emails.json', emails)

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
    from gcs import read_json
    from datetime import datetime, timedelta, timezone
    emails = read_json('saucer-emails.json', [])
    cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    hana_dismissed = [
        e for e in emails
        if e.get('dismissed_by') == 'hana'
        and e.get('verdict') == 'blocked'
        and (e.get('date') or '') >= cutoff
    ]
    hana_dismissed.sort(key=lambda x: x.get('date', ''), reverse=True)
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
    all_emails = read_json('saucer-emails.json', [])

    cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    # Only user-dismissed emails (not Hana's verdict=blocked ones)
    candidates = [
        e for e in all_emails
        if e['id'] in dismissed_ids
        and e.get('dismissed_by') != 'hana'
        and (e.get('date') or '') >= cutoff
    ]

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

    results.sort(key=lambda x: x.get('date', ''), reverse=True)
    return jsonify({'emails': results[:50]})


@app.route('/emails/<path:email_id>/topic-phrase', methods=['GET'])
def get_email_topic_phrase(email_id):
    """Return a short noun phrase describing the main topic of an email (for dismissal UI)."""
    from gcs import read_json
    from email_scanner import extract_topic_noun_phrase
    emails = read_json('saucer-emails.json', [])
    email = next((e for e in emails if e['id'] == email_id), None)
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
    dismissed = read_json('saucer-dismissed.json', [])
    if email_id in dismissed:
        dismissed.remove(email_id)
        write_json('saucer-dismissed.json', dismissed)
    # Clear dismissed_by and reset blocked verdict so the email reappears in inbox
    emails = read_json('saucer-emails.json', [])
    for e in emails:
        if e['id'] == email_id:
            e.pop('dismissed_by', None)
            if e.get('verdict') == 'blocked':
                e['verdict'] = 'uncertain'
            write_json('saucer-emails.json', emails)
            break
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

    # Merge into stored emails so they appear in the app immediately
    stored = read_json('saucer-emails.json', [])
    existing_ids = {e['id'] for e in stored}
    fresh = [e for e in new_emails if e['id'] not in existing_ids]
    if fresh:
        write_json('saucer-emails.json', fresh + stored)
    print(f"[email-trigger] merged {len(fresh)} new emails into saucer-emails.json, total now {len(fresh) + len(stored)}")

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

        print(f"[email-trigger] qualifying (verdict={email.get('verdict')}) — spawning agent for: {subj}")

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


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
