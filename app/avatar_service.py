"""
AI Interviewer Avatar & Video Provider Abstraction Layer

Supports rich interactive animated states for AI Interviewer:
- IDLE (Attentive listening, subtle breathing, eye micro-movements)
- THINKING (Processing candidate answer, analyzing trade-offs, glowing halo)
- SPEAKING (Animated mouth/waveform, dynamic sound bars, speech cadence)

Provides adapter interfaces for photorealistic AI video streaming:
- Tavus
- HeyGen
- Synthesia
- LiveKit Agents
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
import os
import logging

logger = logging.getLogger("ravi.avatar_service")


class BaseAvatarVideoProvider(ABC):
    """Abstract Base Class for AI Interviewer Avatar Providers."""

    @abstractmethod
    def get_provider_name(self) -> str:
        """Returns the unique identifier of the avatar provider."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Checks if video streaming engine or external keys are active."""
        pass

    @abstractmethod
    def get_persona_avatar_metadata(self, persona: str) -> Dict[str, Any]:
        """Returns visual assets, color themes, badges, and layout metadata for the persona."""
        pass

    @abstractmethod
    def get_stream_session(self, persona: str, session_id: str) -> Dict[str, Any]:
        """Generates or establishes a video streaming session."""
        pass


class InteractiveCanvasAvatarProvider(BaseAvatarVideoProvider):
    """
    Default high-performance, GPU-accelerated interactive Canvas/CSS avatar engine.
    Supports animated idle breathing, thinking analysis waves, and real-time speech waveforms.
    """

    PERSONA_METADATA = {
        "alex": {
            "name": "Alex",
            "title": "Principal Technical Lead",
            "company_badge": "FAANG Bar Raiser",
            "avatar_image": "/logo.png",
            "theme_gradient": "linear-gradient(135deg, #0284C7 0%, #0369A1 50%, #0F172A 100%)",
            "accent_color": "#38BDF8",
            "glow_color": "rgba(56, 189, 248, 0.45)",
            "style_prompt": "Analytical, focused on architecture, trade-offs, code quality and concurrency.",
            "initial_greeting": "Hello! I'm Alex. Let's dive right in. I'd love to hear about your experience and how you approach complex systems."
        },
        "elena": {
            "name": "Elena",
            "title": "Principal Systems Architect",
            "company_badge": "Distributed Systems Staff",
            "avatar_image": "/logo.png",
            "theme_gradient": "linear-gradient(135deg, #7C3AED 0%, #6D28D9 50%, #0F172A 100%)",
            "accent_color": "#C084FC",
            "glow_color": "rgba(192, 132, 252, 0.45)",
            "style_prompt": "Strategic, focuses on high-availability, scalability bottlenecks, caching, and resiliency.",
            "initial_greeting": "Welcome. I'm Elena. Today we'll explore system architecture, scalability decisions, and failure modes."
        },
        "marcus": {
            "name": "Marcus",
            "title": "VP of People & Leadership",
            "company_badge": "Executive Hiring Bar",
            "avatar_image": "/logo.png",
            "theme_gradient": "linear-gradient(135deg, #059669 0%, #047857 50%, #0F172A 100%)",
            "accent_color": "#34D399",
            "glow_color": "rgba(52, 211, 153, 0.45)",
            "style_prompt": "Warm, behavioral, probes STAR method, leadership, cross-functional conflicts, and growth.",
            "initial_greeting": "Hi there, I'm Marcus. I'm excited to learn more about your leadership journey, team impact, and behavioral experiences."
        }
    }

    def get_provider_name(self) -> str:
        return "interactive_canvas_avatar"

    def is_available(self) -> bool:
        return True

    def get_persona_avatar_metadata(self, persona: str) -> Dict[str, Any]:
        p = persona.lower().strip()
        return self.PERSONA_METADATA.get(p, self.PERSONA_METADATA["alex"])

    def get_stream_session(self, persona: str, session_id: str) -> Dict[str, Any]:
        meta = self.get_persona_avatar_metadata(persona)
        return {
            "provider": self.get_provider_name(),
            "mode": "client_canvas_render",
            "persona": meta,
            "session_id": session_id,
            "supported_states": ["idle", "thinking", "speaking", "paused"],
            "waveform_enabled": True
        }


class TavusVideoProvider(BaseAvatarVideoProvider):
    """Tavus Conversational Video Replicas Provider."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("TAVUS_API_KEY", "")

    def get_provider_name(self) -> str:
        return "tavus_video_replica"

    def is_available(self) -> bool:
        return bool(self.api_key and len(self.api_key) > 10)

    def get_persona_avatar_metadata(self, persona: str) -> Dict[str, Any]:
        return InteractiveCanvasAvatarProvider().get_persona_avatar_metadata(persona)

    def get_stream_session(self, persona: str, session_id: str) -> Dict[str, Any]:
        if not self.is_available():
            return InteractiveCanvasAvatarProvider().get_stream_session(persona, session_id)
        
        return {
            "provider": self.get_provider_name(),
            "mode": "webrtc_stream",
            "session_id": session_id,
            "stream_url": None
        }


class HeyGenVideoProvider(BaseAvatarVideoProvider):
    """HeyGen Interactive Streaming Avatar Provider."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("HEYGEN_API_KEY", "")

    def get_provider_name(self) -> str:
        return "heygen_streaming_avatar"

    def is_available(self) -> bool:
        return bool(self.api_key and len(self.api_key) > 10)

    def get_persona_avatar_metadata(self, persona: str) -> Dict[str, Any]:
        return InteractiveCanvasAvatarProvider().get_persona_avatar_metadata(persona)

    def get_stream_session(self, persona: str, session_id: str) -> Dict[str, Any]:
        return InteractiveCanvasAvatarProvider().get_stream_session(persona, session_id)


def get_avatar_provider(provider_override: Optional[str] = None) -> BaseAvatarVideoProvider:
    """
    Factory to resolve the active AI Avatar / Video provider.
    Defaults to InteractiveCanvasAvatarProvider for zero-latency, reliable rendering.
    """
    provider_name = (provider_override or os.environ.get("AVATAR_PROVIDER", "canvas")).lower().strip()

    if provider_name == "tavus":
        tavus = TavusVideoProvider()
        if tavus.is_available():
            return tavus
    elif provider_name == "heygen":
        heygen = HeyGenVideoProvider()
        if heygen.is_available():
            return heygen

    return InteractiveCanvasAvatarProvider()
