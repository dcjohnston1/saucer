from flask import Blueprint, request, jsonify
from memory import get_queued_question, snooze_question, clear_question, list_notes, delete_note, revert_note
from logger import log_action

memory_bp = Blueprint('memory', __name__)


@memory_bp.route('/hana/question', methods=['GET'])
def get_hana_question():
    """Return the current queued question if ready. Frontend polls this."""
    q = get_queued_question()
    if not q:
        return jsonify({"has_question": False})
    return jsonify({
        "has_question": True,
        "question": q["question"],
        "queued_at": q["queued_at"].isoformat() if hasattr(q["queued_at"], "isoformat") else str(q["queued_at"])
    })


@memory_bp.route('/hana/question/snooze', methods=['POST'])
def snooze_hana_question():
    """Called when user opens chat to talk about something else."""
    return jsonify(snooze_question(days=3))


@memory_bp.route('/hana/question/clear', methods=['POST'])
def clear_hana_question():
    return jsonify(clear_question())


@memory_bp.route('/hana/notes', methods=['GET'])
def get_hana_notes():
    """Return all notes for display in the UI, excluding internal filtering-feedback entries."""
    notes = list_notes()
    filtered = [
        n for n in notes
        if 'email filtering' not in n.get('topic', '').lower()
        and 'filtering feedback' not in n.get('topic', '').lower()
    ]
    return jsonify({"notes": filtered})


@memory_bp.route('/hana/notes/<topic_slug>', methods=['DELETE'])
def delete_hana_note(topic_slug):
    return jsonify(delete_note(topic_slug))


@memory_bp.route('/hana/notes/<topic_slug>/revert', methods=['POST'])
def revert_hana_note(topic_slug):
    result = revert_note(topic_slug)
    if result.get('status') == 'ok':
        log_action('system', 'note_reverted', {'topic_slug': topic_slug})
    return jsonify(result)
