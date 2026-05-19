"""
routes/voice.py — In-app voice: STT → Hana → TTS.

POST /voice/run
  Accepts: multipart/form-data with field 'audio' (WebM/Opus bytes)
           Optional form fields: 'user' (email), 'user_email' (email), 'conversation_id'
  Returns: MP3 audio bytes (Content-Type: audio/mpeg) on success
           JSON {"error": "low_confidence", "message": "..."} if STT confidence is too low
           JSON {"error": "..."} on other failures

Flow:
  1. Read audio bytes from request.files['audio']
  2. Transcribe via Google Cloud STT (WEBM_OPUS encoding — no ffmpeg needed)
  3. Pass transcript to mediator.process_message (same as /chat route)
  4. Synthesize Hana's text reply via Google Cloud TTS → MP3
  5. Return MP3 bytes
"""

import uuid
import traceback
from flask import Blueprint, request, jsonify, Response

from voice_handler import transcribe_audio, synthesize_speech
from lib.config import _DAN

voice_bp = Blueprint('voice', __name__)


@voice_bp.route('/voice/run', methods=['POST'])
def voice_run():
    """In-app voice endpoint: audio in, audio out."""
    # ── Validate input ──────────────────────────────────────────────────────
    if 'audio' not in request.files:
        return jsonify({'error': 'missing_audio', 'message': 'No audio file provided.'}), 400

    audio_file = request.files['audio']
    audio_bytes = audio_file.read()
    if not audio_bytes:
        return jsonify({'error': 'empty_audio', 'message': 'Audio file was empty.'}), 400

    # User identification — fall back to _DAN if not provided
    user = request.form.get('user') or request.form.get('user_email') or _DAN
    user_email = user
    conversation_id = request.form.get('conversation_id') or str(uuid.uuid4())

    # ── Step 1: Transcribe audio → text ────────────────────────────────────
    try:
        transcript = transcribe_audio(audio_bytes)
        print(f'[voice] transcribed: "{transcript[:80]}{"..." if len(transcript) > 80 else ""}"')
    except ValueError as ve:
        err = str(ve)
        if err == 'low_confidence':
            return jsonify({
                'error': 'low_confidence',
                'message': "I didn't quite catch that. Could you try again?",
            }), 200
        # no_transcript or other
        return jsonify({
            'error': 'no_transcript',
            'message': "I couldn't hear anything. Please hold the button and speak clearly.",
        }), 200
    except Exception as e:
        print(f'[voice] STT error: {traceback.format_exc()}')
        return jsonify({'error': 'stt_failed', 'message': 'Speech recognition failed.'}), 500

    # ── Step 2: Run Hana agent with transcript ──────────────────────────────
    try:
        from mediator import process_message
        reply, _actions = process_message(
            user=user,
            message=transcript,
            history=[],           # voice interactions are stateless for now
            user_email=user_email,
            conversation_id=conversation_id,
            voice_mode=True,      # hint to Hana to keep replies concise and conversational
        )
        print(f'[voice] Hana reply: "{reply[:80]}{"..." if len(reply) > 80 else ""}"')
    except Exception as e:
        print(f'[voice] agent error: {traceback.format_exc()}')
        return jsonify({'error': 'agent_failed', 'message': 'Hana could not process your request.'}), 500

    # ── Step 3: Synthesize reply → MP3 ─────────────────────────────────────
    try:
        mp3_bytes = synthesize_speech(reply)
    except Exception as e:
        print(f'[voice] TTS error: {traceback.format_exc()}')
        return jsonify({'error': 'tts_failed', 'message': 'Could not generate audio response.'}), 500

    # ── Step 4: Return MP3 ──────────────────────────────────────────────────
    return Response(
        mp3_bytes,
        mimetype='audio/mpeg',
        headers={
            'Content-Disposition': 'inline; filename="hana_response.mp3"',
            'X-Transcript': transcript[:200],   # useful for debugging; truncated for header safety
        },
    )
