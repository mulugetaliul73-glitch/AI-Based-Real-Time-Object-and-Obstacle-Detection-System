"""Validation and normalization helpers for speech-recognition transcripts."""

from __future__ import annotations


def normalize_transcript(transcript: str, max_length: int = 500) -> str:
    """Trim and collapse whitespace in recognized text, rejecting invalid input."""
    if not isinstance(transcript, str):
        raise ValueError("Transcript must be a string.")
    if isinstance(max_length, bool) or not isinstance(max_length, int) or max_length < 1:
        raise ValueError("max_length must be a positive integer.")

    normalized = " ".join(transcript.split())
    if not normalized:
        raise ValueError("Transcript must not be empty.")
    if len(normalized) > max_length:
        raise ValueError(f"Transcript must not exceed {max_length} characters.")
    return normalized
"""
Speech Input — Browser-based voice recognition placeholder.
Actual voice recognition happens in the browser via Web Speech API.
"""
import logging

logger = logging.getLogger(__name__)


class VoiceInput:
    """Placeholder for voice input (browser handles actual recognition)."""

    def __init__(self, language: str = "en-US"):
        self.language = language
        logger.info(f"🎤 Voice input ready (browser-based), language: {language}")

    def set_language(self, language_code: str) -> None:
        self.language = language_code
        logger.info(f"🌍 Voice language set to: {language_code}")

    def listen_once(self) -> dict:
        return {
            "success": False,
            "text": "",
            "error": "Voice input happens in the browser. Use the 🎤 Listen button.",
        }


_voice_input: VoiceInput | None = None


def get_voice_input() -> VoiceInput:
    global _voice_input
    if _voice_input is None:
        _voice_input = VoiceInput()
    return _voice_input