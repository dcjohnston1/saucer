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
    return jsonify({'reply': reply})

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
