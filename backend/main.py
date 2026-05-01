import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from google.cloud import firestore
from mediator import process_message

app = Flask(__name__)
CORS(app)

def get_db():
    return firestore.Client(project='mediationmate')


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
            'notes': None
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

    config = read_json('saucer-config.json', {})
    last_sync = config.get('last_sync_timestamp')

    if last_sync is None:
        after_ts = (datetime.now(timezone.utc) - timedelta(days=30)).timestamp()
    else:
        after_ts = last_sync

    new_emails = scan_emails(
        sender_filter=filters if filters else None,
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

    return jsonify({'emails': visible})


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
    return jsonify({'ok': True})


@app.route('/email-filters/<path:email>', methods=['DELETE'])
def remove_email_filter(email):
    db = get_db()
    db.collection('settings').document('email_filters').set(
        {'addresses': firestore.ArrayRemove([email])}, merge=True
    )
    return jsonify({'ok': True})


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
