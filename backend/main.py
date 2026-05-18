import os
import uuid
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from google.cloud import firestore
from logger import log_action, get_recent_actions, get_action_summary, get_recent_decisions
from lib.firestore_client import get_db

app = Flask(__name__)
CORS(app)

from routes.agent import agent_bp
from routes.tasks import tasks_bp
from routes.emails import emails_bp
from routes.filters import filters_bp
app.register_blueprint(agent_bp)
app.register_blueprint(tasks_bp)
app.register_blueprint(emails_bp)
app.register_blueprint(filters_bp)


def _req_user(data=None):
    """Extract the acting user's email from request body or query param."""
    if data:
        v = data.get('user', '')
        if v:
            return v
    return request.args.get('user', 'unknown')


# ── Relevant Files ────────────────────────────────────────────────────────────

_ALLOWED_FILE_TYPES = {
    'application/pdf': '.pdf',
    'image/jpeg': '.jpg',
    'image/png': '.png',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': '.docx',
}
_MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB


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


# ── Calendar ──────────────────────────────────────────────────────────────────

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


# ── User Settings ─────────────────────────────────────────────────────────────

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


# ── Actions / Decisions history ───────────────────────────────────────────────

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


# ── Conversation history ──────────────────────────────────────────────────────

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


# ── Session checkpoint ────────────────────────────────────────────────────────

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


# ── Debug ─────────────────────────────────────────────────────────────────────

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


# ── Hana memory / questions ───────────────────────────────────────────────────

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


# ── Health ────────────────────────────────────────────────────────────────────

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
