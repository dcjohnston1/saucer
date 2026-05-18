import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from google.cloud import firestore
from logger import log_action
from lib.firestore_client import get_db

app = Flask(__name__)
CORS(app)

from routes.agent import agent_bp
from routes.tasks import tasks_bp
from routes.emails import emails_bp
from routes.filters import filters_bp
from routes.memory import memory_bp
from routes.files import files_bp
from routes.admin import admin_bp
from routes.calendar import calendar_bp
app.register_blueprint(agent_bp)
app.register_blueprint(tasks_bp)
app.register_blueprint(emails_bp)
app.register_blueprint(filters_bp)
app.register_blueprint(memory_bp)
app.register_blueprint(files_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(calendar_bp)


# ── Health ────────────────────────────────────────────────────────────────────

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
