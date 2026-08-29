"""
Speech-to-Text (STT) Provider Abstraction Layer

Provides a modular architecture for real-time speech recognition.
Supports client-side Browser Web Speech API as default fallback,
with pluggable interfaces for enterprise STT providers:
- Deepgram
- AssemblyAI
- Google Cloud Speech-to-Text
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
import os
import logging

logger = logging.getLogger("ravi.speech_service")


class BaseSpeechToTextProvider(ABC):
    """Abstract Base Class for Speech-to-Text Providers."""

    @abstractmethod
    def get_provider_name(self) -> str:
        """Returns the unique name identifier of the provider."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Checks if required API keys and dependencies are configured."""
        pass

    @abstractmethod
    def transcribe_audio_chunk(self, audio_bytes: bytes, mime_type: str = "audio/webm") -> Dict[str, Any]:
        """Transcribes raw audio bytes to text transcript."""
        pass

    @abstractmethod
    def get_client_config(self) -> Dict[str, Any]:
        """Returns client-side configuration parameters for the frontend."""
        pass


class BrowserSpeechProvider(BaseSpeechToTextProvider):
    """Default client-side Web Speech API provider (no external API keys required)."""

    def get_provider_name(self) -> str:
        return "browser_web_speech"

    def is_available(self) -> bool:
        return True

    def transcribe_audio_chunk(self, audio_bytes: bytes, mime_type: str = "audio/webm") -> Dict[str, Any]:
        return {
            "transcript": "",
            "confidence": 1.0,
            "provider": self.get_provider_name(),
            "mode": "client_side_streaming",
            "message": "Browser handles speech recognition directly via SpeechRecognition / webkitSpeechRecognition API"
        }

    def get_client_config(self) -> Dict[str, Any]:
        return {
            "provider": "browser_web_speech",
            "continuous": True,
            "interim_results": True,
            "language": "en-US"
        }


class DeepgramSpeechProvider(BaseSpeechToTextProvider):
    """Deepgram Nova-2 Real-time STT Provider interface."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("DEEPGRAM_API_KEY", "")

    def get_provider_name(self) -> str:
        return "deepgram_nova2"

    def is_available(self) -> bool:
        return bool(self.api_key and len(self.api_key) > 5)

    def transcribe_audio_chunk(self, audio_bytes: bytes, mime_type: str = "audio/webm") -> Dict[str, Any]:
        if not self.is_available():
            return BrowserSpeechProvider().transcribe_audio_chunk(audio_bytes, mime_type)
        
        try:
            import requests
            headers = {
                "Authorization": f"Token {self.api_key}",
                "Content-Type": mime_type
            }
            url = "https://api.deepgram.com/v1/listen?model=nova-2&smart_format=true&punctuate=true"
            resp = requests.post(url, headers=headers, data=audio_bytes, timeout=10)
            if resp.ok:
                data = resp.json()
                transcript = data.get("results", {}).get("channels", [{}])[0].get("alternatives", [{}])[0].get("transcript", "")
                confidence = data.get("results", {}).get("channels", [{}])[0].get("alternatives", [{}])[0].get("confidence", 0.95)
                return {
                    "transcript": transcript,
                    "confidence": confidence,
                    "provider": self.get_provider_name()
                }
        except Exception as e:
            logger.warning(f"[Deepgram STT Warning] {e}")

        return BrowserSpeechProvider().transcribe_audio_chunk(audio_bytes, mime_type)

    def get_client_config(self) -> Dict[str, Any]:
        return {
            "provider": "deepgram",
            "enabled": self.is_available(),
            "model": "nova-2",
            "language": "en"
        }


class AssemblyAISpeechProvider(BaseSpeechToTextProvider):
    """AssemblyAI Real-time STT Provider interface."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("ASSEMBLYAI_API_KEY", "")

    def get_provider_name(self) -> str:
        return "assemblyai_streaming"

    def is_available(self) -> bool:
        return bool(self.api_key and len(self.api_key) > 5)

    def transcribe_audio_chunk(self, audio_bytes: bytes, mime_type: str = "audio/webm") -> Dict[str, Any]:
        return BrowserSpeechProvider().transcribe_audio_chunk(audio_bytes, mime_type)

    def get_client_config(self) -> Dict[str, Any]:
        return {
            "provider": "assemblyai",
            "enabled": self.is_available()
        }


class GoogleCloudSpeechProvider(BaseSpeechToTextProvider):
    """Google Cloud Speech-to-Text v2 Provider interface."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("GOOGLE_SPEECH_API_KEY", "")

    def get_provider_name(self) -> str:
        return "google_cloud_stt"

    def is_available(self) -> bool:
        return bool(self.api_key and len(self.api_key) > 5)

    def transcribe_audio_chunk(self, audio_bytes: bytes, mime_type: str = "audio/webm") -> Dict[str, Any]:
        return BrowserSpeechProvider().transcribe_audio_chunk(audio_bytes, mime_type)

    def get_client_config(self) -> Dict[str, Any]:
        return {
            "provider": "google_stt",
            "enabled": self.is_available()
        }


def get_stt_provider(provider_override: Optional[str] = None) -> BaseSpeechToTextProvider:
    """
    Factory to resolve the active Speech-to-Text provider.
    Defaults to BrowserSpeechProvider for instant zero-config usage.
    """
    provider_name = (provider_override or os.environ.get("STT_PROVIDER", "browser")).lower().strip()

    if provider_name == "deepgram":
        deepgram = DeepgramSpeechProvider()
        if deepgram.is_available():
            return deepgram
    elif provider_name == "assemblyai":
        assembly = AssemblyAISpeechProvider()
        if assembly.is_available():
            return assembly
    elif provider_name in ["google", "google_cloud"]:
        google_stt = GoogleCloudSpeechProvider()
        if google_stt.is_available():
            return google_stt

    return BrowserSpeechProvider()
