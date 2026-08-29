"""
Text-to-Speech (TTS) Provider Abstraction Layer

Provides modular AI voice synthesis for Interviewer personas.
Supports browser SpeechSynthesis API as default fallback,
with pluggable interfaces for:
- ElevenLabs (Ultra-realistic conversational voices)
- OpenAI TTS (alloy, echo, fable, onyx, nova, shimmer)
- Google Cloud Text-to-Speech
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
import os
import logging

logger = logging.getLogger("ravi.tts_service")


class BaseTextToSpeechProvider(ABC):
    """Abstract Base Class for Text-to-Speech Providers."""

    @abstractmethod
    def get_provider_name(self) -> str:
        """Returns the unique identifier of the TTS provider."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Checks if provider credentials and network dependencies are met."""
        pass

    @abstractmethod
    def synthesize_speech(self, text: str, persona: str = "alex") -> Dict[str, Any]:
        """Synthesizes text into speech or returns client-side synthesis metadata."""
        pass

    @abstractmethod
    def get_persona_voice_config(self, persona: str) -> Dict[str, Any]:
        """Returns voice parameters tailored for the specific AI interviewer persona."""
        pass


class BrowserSynthesisTTSProvider(BaseTextToSpeechProvider):
    """Default browser Web SpeechSynthesis API provider."""

    PERSONA_VOICE_MAP = {
        "alex": {
            "name": "Alex",
            "voice_name": "Google US English",
            "lang": "en-US",
            "pitch": 0.95,
            "rate": 1.02,
            "persona_tone": "Analytical & Direct Tech Lead"
        },
        "elena": {
            "name": "Elena",
            "voice_name": "Google UK English Female",
            "lang": "en-GB",
            "pitch": 1.1,
            "rate": 0.98,
            "persona_tone": "Strategic Principal Architect"
        },
        "marcus": {
            "name": "Marcus",
            "voice_name": "Google US English",
            "lang": "en-US",
            "pitch": 0.9,
            "rate": 0.95,
            "persona_tone": "Warm & Insightful HR Director"
        }
    }

    def get_provider_name(self) -> str:
        return "browser_speech_synthesis"

    def is_available(self) -> bool:
        return True

    def get_persona_voice_config(self, persona: str) -> Dict[str, Any]:
        p = persona.lower().strip()
        return self.PERSONA_VOICE_MAP.get(p, self.PERSONA_VOICE_MAP["alex"])

    def synthesize_speech(self, text: str, persona: str = "alex") -> Dict[str, Any]:
        voice_cfg = self.get_persona_voice_config(persona)
        return {
            "audio_url": None,
            "provider": self.get_provider_name(),
            "client_synthesis": True,
            "text": text,
            "voice_config": voice_cfg,
            "message": "Synthesized directly via browser window.speechSynthesis"
        }


class ElevenLabsTTSProvider(BaseTextToSpeechProvider):
    """ElevenLabs Conversational TTS Provider."""

    PERSONA_VOICE_IDS = {
        "alex": "pNInz6obpgDQGcFmaJgB",
        "elena": "EXAVITQu4vr4xnSDxMaL",
        "marcus": "ErXwobaYiN019PkySvjV"
    }

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("ELEVENLABS_API_KEY", "")

    def get_provider_name(self) -> str:
        return "elevenlabs"

    def is_available(self) -> bool:
        return bool(self.api_key and len(self.api_key) > 10)

    def get_persona_voice_config(self, persona: str) -> Dict[str, Any]:
        p = persona.lower().strip()
        voice_id = self.PERSONA_VOICE_IDS.get(p, self.PERSONA_VOICE_IDS["alex"])
        return {
            "voice_id": voice_id,
            "model_id": "eleven_turbo_v2_5",
            "stability": 0.65,
            "similarity_boost": 0.8
        }

    def synthesize_speech(self, text: str, persona: str = "alex") -> Dict[str, Any]:
        if not self.is_available():
            return BrowserSynthesisTTSProvider().synthesize_speech(text, persona)

        voice_cfg = self.get_persona_voice_config(persona)
        try:
            import requests
            headers = {
                "xi-api-key": self.api_key,
                "Content-Type": "application/json"
            }
            payload = {
                "text": text,
                "model_id": voice_cfg["model_id"],
                "voice_settings": {
                    "stability": voice_cfg["stability"],
                    "similarity_boost": voice_cfg["similarity_boost"]
                }
            }
            url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_cfg['voice_id']}"
            resp = requests.post(url, json=payload, headers=headers, timeout=12)
            if resp.ok:
                import base64
                audio_base64 = base64.b64encode(resp.content).decode("utf-8")
                return {
                    "audio_base64": f"data:audio/mp3;base64,{audio_base64}",
                    "provider": self.get_provider_name(),
                    "client_synthesis": False,
                    "text": text
                }
        except Exception as e:
            logger.warning(f"[ElevenLabs TTS Warning] {e}")

        return BrowserSynthesisTTSProvider().synthesize_speech(text, persona)


class OpenAITTSProvider(BaseTextToSpeechProvider):
    """OpenAI TTS Provider (tts-1 / tts-1-hd)."""

    PERSONA_VOICES = {
        "alex": "onyx",
        "elena": "nova",
        "marcus": "echo"
    }

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")

    def get_provider_name(self) -> str:
        return "openai_tts"

    def is_available(self) -> bool:
        return bool(self.api_key and len(self.api_key) > 10)

    def get_persona_voice_config(self, persona: str) -> Dict[str, Any]:
        p = persona.lower().strip()
        voice = self.PERSONA_VOICES.get(p, "onyx")
        return {"voice": voice, "model": "tts-1", "speed": 1.0}

    def synthesize_speech(self, text: str, persona: str = "alex") -> Dict[str, Any]:
        if not self.is_available():
            return BrowserSynthesisTTSProvider().synthesize_speech(text, persona)

        voice_cfg = self.get_persona_voice_config(persona)
        try:
            import requests
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": voice_cfg["model"],
                "input": text,
                "voice": voice_cfg["voice"]
            }
            url = "https://api.openai.com/v1/audio/speech"
            resp = requests.post(url, json=payload, headers=headers, timeout=12)
            if resp.ok:
                import base64
                audio_base64 = base64.b64encode(resp.content).decode("utf-8")
                return {
                    "audio_base64": f"data:audio/mp3;base64,{audio_base64}",
                    "provider": self.get_provider_name(),
                    "client_synthesis": False,
                    "text": text
                }
        except Exception as e:
            logger.warning(f"[OpenAI TTS Warning] {e}")

        return BrowserSynthesisTTSProvider().synthesize_speech(text, persona)


def get_tts_provider(provider_override: Optional[str] = None) -> BaseTextToSpeechProvider:
    """
    Factory to resolve the active Text-to-Speech provider.
    Defaults to BrowserSynthesisTTSProvider for instant zero-config usage.
    """
    provider_name = (provider_override or os.environ.get("TTS_PROVIDER", "browser")).lower().strip()

    if provider_name == "elevenlabs":
        eleven = ElevenLabsTTSProvider()
        if eleven.is_available():
            return eleven
    elif provider_name in ["openai", "openai_tts"]:
        openai_tts = OpenAITTSProvider()
        if openai_tts.is_available():
            return openai_tts

    return BrowserSynthesisTTSProvider()
