"""ElevenLabs speech-to-text and text-to-speech. API keys stay on the server."""

import requests
from django.conf import settings

BASE_URL = 'https://api.elevenlabs.io/v1'

# Reusing one connection skips the TLS handshake, which is noticeable on every reply.
_session = requests.Session()


class SpeechError(Exception):
    pass


def _headers():
    if not settings.ELEVENLABS_API_KEY:
        raise SpeechError('ELEVENLABS_API_KEY is not set')
    return {'xi-api-key': settings.ELEVENLABS_API_KEY}


def _post(url, rewind=None, **kwargs):
    """POST, retrying once if the connection dropped. A reused connection can go stale between requests."""
    try:
        return _session.post(url, timeout=settings.SPEECH_TIMEOUT_SECONDS, **kwargs)
    except requests.ConnectionError:
        if rewind:
            rewind()
        return _session.post(url, timeout=settings.SPEECH_TIMEOUT_SECONDS, **kwargs)


def transcribe(audio_file):
    try:
        response = _post(
            f'{BASE_URL}/speech-to-text',
            rewind=lambda: audio_file.seek(0),
            headers=_headers(),
            data={
                'model_id': settings.ELEVENLABS_STT_MODEL,
                'language_code': settings.ELEVENLABS_STT_LANGUAGE,
            },
            files={'file': (audio_file.name, audio_file, audio_file.content_type)},
        )
        response.raise_for_status()
        return response.json()['text'].strip()
    except (requests.RequestException, KeyError, ValueError) as exc:
        raise SpeechError(_describe(exc)) from exc


def synthesize(text):
    if not settings.ELEVENLABS_VOICE_ID:
        raise SpeechError('ELEVENLABS_VOICE_ID is not set')
    try:
        response = _post(
            f'{BASE_URL}/text-to-speech/{settings.ELEVENLABS_VOICE_ID}',
            headers=_headers(),
            params={'output_format': 'mp3_44100_64'},
            json={'text': text, 'model_id': settings.ELEVENLABS_TTS_MODEL},
        )
        response.raise_for_status()
        return response.content
    except requests.RequestException as exc:
        raise SpeechError(_describe(exc)) from exc


def _describe(exc):
    """Enough to debug from the logs. Never includes the request headers, so no key leaks."""
    response = getattr(exc, 'response', None)
    if response is not None:
        return f'ElevenLabs returned {response.status_code}: {response.text[:300]}'
    return f'ElevenLabs request failed: {type(exc).__name__}'
