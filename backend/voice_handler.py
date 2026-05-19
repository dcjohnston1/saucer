"""
voice_handler.py — Google Cloud STT + TTS for in-app voice.

Flow:
  1. Receive raw audio bytes (WebM/Opus from frontend, via multipart POST)
  2. Send directly to Google Cloud Speech-to-Text using WEBM_OPUS encoding
     (no ffmpeg conversion needed — the STT API accepts WEBM_OPUS natively)
  3. Return transcript string; raises ValueError if confidence < 0.5
     (caller should prompt user to repeat)
  4. Caller passes transcript to the existing Hana agent
  5. Send Hana's text response to Google Cloud Text-to-Speech
  6. Return MP3 bytes to frontend

Credentials: Cloud Run service account (ADC — no key file needed).
"""

from google.cloud import speech
from google.cloud import texttospeech

_STT_CLIENT = None
_TTS_CLIENT = None


def _get_stt_client():
    global _STT_CLIENT
    if _STT_CLIENT is None:
        _STT_CLIENT = speech.SpeechClient()
    return _STT_CLIENT


def _get_tts_client():
    global _TTS_CLIENT
    if _TTS_CLIENT is None:
        _TTS_CLIENT = texttospeech.TextToSpeechClient()
    return _TTS_CLIENT


# Minimum confidence threshold for accepting a transcription.
# Below this, we ask the user to repeat rather than passing gibberish to Hana.
_MIN_CONFIDENCE = 0.5


def transcribe_audio(audio_bytes: bytes) -> str:
    """
    Send WebM/Opus audio bytes to Google Cloud STT.
    Returns the transcript string.
    Raises ValueError if confidence < _MIN_CONFIDENCE or no transcript is returned.
    """
    client = _get_stt_client()

    audio = speech.RecognitionAudio(content=audio_bytes)
    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.WEBM_OPUS,
        # sample_rate_hertz is not required when encoding is WEBM_OPUS
        # (the API reads it from the container header)
        language_code="en-US",
        enable_automatic_punctuation=True,
        model="latest_long",
    )

    response = client.recognize(config=config, audio=audio)

    if not response.results:
        raise ValueError("no_transcript")

    result = response.results[0]
    if not result.alternatives:
        raise ValueError("no_transcript")

    alt = result.alternatives[0]
    confidence = alt.confidence if alt.confidence else 0.0

    # Note: confidence is 0.0 for LINEAR16 short clips sometimes,
    # but WEBM_OPUS with latest_long model reliably returns confidence.
    # If confidence is exactly 0.0 we allow it through (API omitted it).
    if confidence > 0.0 and confidence < _MIN_CONFIDENCE:
        raise ValueError("low_confidence")

    transcript = alt.transcript.strip()
    if not transcript:
        raise ValueError("no_transcript")

    return transcript


def synthesize_speech(text: str) -> bytes:
    """
    Send text to Google Cloud TTS (Neural2 voice, en-US).
    Returns MP3 bytes.
    """
    client = _get_tts_client()

    synthesis_input = texttospeech.SynthesisInput(text=text)
    voice = texttospeech.VoiceSelectionParams(
        language_code="en-US",
        name="en-US-Neural2-F",  # Warm, clear female Neural2 voice
        ssml_gender=texttospeech.SsmlVoiceGender.FEMALE,
    )
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3,
        speaking_rate=1.0,
        pitch=0.0,
    )

    response = client.synthesize_speech(
        input=synthesis_input,
        voice=voice,
        audio_config=audio_config,
    )

    return response.audio_content
