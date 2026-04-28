import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from mediator import process_message

app = Flask(__name__)
CORS(app)

@app.route('/chat', methods=['POST'])
def chat():
    data = request.get_json()
    user = data.get('user')  # 'husband' or 'wife'
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

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
