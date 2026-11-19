"""Vision providers for VektorShot Phase 1.

The provider interface is small on purpose: one screenshot in, one
structured layout description out. Real providers read their keys from
environment variables only — never from arguments, files, or chat.

Phase 1 ships a deterministic stub provider so the whole pipeline can be
built and tested with no live model. Live calls are NOT wired in Phase 1:
the env-backed providers fail clearly when their key is missing, and the
probe helpers below report reachability without ever calling a model.
"""

from __future__ import annotations

import os
import struct
import urllib.request
from abc import ABC, abstractmethod

from .models import LayoutDescription, LayoutElement, ProbeResult

__all__ = [
    "VisionError",
    "VisionConfigError",
    "VisionProvider",
    "StubVisionProvider",
    "OllamaVisionProvider",
    "GeminiVisionProvider",
    "GroqVisionProvider",
    "available_providers",
    "select_provider",
]

# Free-tier-first order, matching VektorCode's routing.
PROVIDER_ORDER = ("ollama", "gemini", "groq")


class VisionError(Exception):
    """A vision call could not run."""


class VisionConfigError(VisionError):
    """A provider is not configured (missing key / missing service).

    The message always names the environment variable or service to fix.
    """


class VisionProvider(ABC):
    """One screenshot in, one structured layout out."""

    name = "vision"

    @abstractmethod
    def analyze_screenshot(self, image_bytes: bytes) -> LayoutDescription:
        """Describe the layout of a PNG screenshot."""

    @abstractmethod
    def probe(self) -> ProbeResult:
        """Report reachability without calling any model."""


def _png_dimensions(image_bytes: bytes) -> tuple:
    """Width/height from a PNG IHDR chunk. Raises ValueError if not a PNG."""
    if len(image_bytes) < 24 or not image_bytes.startswith(b"\x89PNG"):
        raise ValueError("image must be a PNG file")
    width, height = struct.unpack(">II", image_bytes[16:24])
    return width, height


class StubVisionProvider(VisionProvider):
    """Deterministic stand-in for tests and offline use.

    Derives a fixed, plausible layout from the image dimensions only.
    It never calls a model and never costs anything. It is NOT a live
    vision result — never present its output as one.
    """

    name = "stub"

    def analyze_screenshot(self, image_bytes: bytes) -> LayoutDescription:
        if not image_bytes:
            raise ValueError("screenshot is empty")
        width, height = _png_dimensions(image_bytes)
        return LayoutDescription(
            page_title="Stub layout",
            width=width,
            height=height,
            elements=[
                LayoutElement(kind="nav", text="Home Features Pricing",
                              x=0, y=0, width=1000, height=60),
                LayoutElement(kind="heading", text="Welcome to VektorFlow",
                              x=80, y=120, width=840, height=70),
                LayoutElement(kind="text",
                              text="Build anything from a screenshot.",
                              x=80, y=210, width=600, height=40),
                LayoutElement(kind="button", text="Get started",
                              x=80, y=280, width=160, height=48),
                LayoutElement(kind="card", text="Free-tier-first",
                              x=80, y=360, width=260, height=120),
                LayoutElement(kind="card", text="$0 cost ledger",
                              x=370, y=360, width=260, height=120),
                LayoutElement(kind="footer", text="VektorFlow AI Systems",
                              x=0, y=940, width=1000, height=60),
            ],
            notes="stub provider: layout derived from image size only",
        )

    def probe(self) -> ProbeResult:
        return ProbeResult(
            name=self.name, reachable=True,
            reason="stub is always available (no live model)")


class _EnvVisionProvider(VisionProvider):
    """Base for providers that need an API key from the environment."""

    env_var = ""
    provider_label = ""

    def _api_key(self) -> str:
        key = os.environ.get(self.env_var, "")
        if not key.strip():
            raise VisionConfigError(
                f"{self.provider_label} is not configured: set the "
                f"{self.env_var} environment variable. No key is stored "
                "in code, files, or chat.")
        return key

    def analyze_screenshot(self, image_bytes: bytes) -> LayoutDescription:
        # Phase 1 wires the interface, not live calls. A configured key
        # is checked first so a missing key fails with the config error
        # above instead of a confusing network error.
        self._api_key()
        if not image_bytes:
            raise ValueError("screenshot is empty")
        raise VisionError(
            f"{self.provider_label} live calls are not wired in Phase 1. "
            "Use the stub provider for tests, or wait for the live "
            "provider wiring in a later phase.")

    def probe(self) -> ProbeResult:
        configured = bool(os.environ.get(self.env_var, "").strip())
        return ProbeResult(
            name=self.name, reachable=False,
            reason=(f"{self.env_var} is set (live calls not wired in "
                    "Phase 1)" if configured else
                    f"{self.env_var} is not set"))


class GeminiVisionProvider(_EnvVisionProvider):
    """Gemini (Hydrogen) vision. Key from GEMINI_API_KEY only."""

    name = "gemini"
    env_var = "GEMINI_API_KEY"
    provider_label = "Gemini"


class GroqVisionProvider(_EnvVisionProvider):
    """Groq vision. Key from GROQ_API_KEY only."""

    name = "groq"
    env_var = "GROQ_API_KEY"
    provider_label = "Groq"


class OllamaVisionProvider(VisionProvider):
    """Local Ollama vision. No key — talks to a local server only."""

    name = "ollama"

    def __init__(self, host=None):
        self.host = (host or os.environ.get("OLLAMA_HOST")
                     or "http://127.0.0.1:11434").rstrip("/")

    def analyze_screenshot(self, image_bytes: bytes) -> LayoutDescription:
        if not image_bytes:
            raise ValueError("screenshot is empty")
        if not self.probe().reachable:
            raise VisionConfigError(
                "Ollama is not reachable at "
                f"{self.host}. Start Ollama and pull a vision model "
                "(e.g. llava) before using this provider.")
        raise VisionError(
            "Ollama live calls are not wired in Phase 1. Use the stub "
            "provider for tests.")

    def probe(self) -> ProbeResult:
        try:
            request = urllib.request.Request(self.host + "/api/tags")
            with urllib.request.urlopen(request, timeout=3) as response:
                ok = response.status == 200
        except Exception as exc:  # network down, no server, refused
            return ProbeResult(name=self.name, reachable=False,
                               reason=f"Ollama not reachable: {exc}")
        return ProbeResult(
            name=self.name, reachable=ok,
            reason="Ollama answered on /api/tags" if ok else
            "Ollama answered with a non-200 status")


def available_providers() -> list:
    """Reachability for each free-tier route. Makes no model calls.

    Ollama is probed over local HTTP (no key). Gemini/Groq report
    key presence only — presence is not proof the key works.
    """
    return [p.probe() for p in (
        OllamaVisionProvider(),
        GeminiVisionProvider(),
        GroqVisionProvider(),
    )]


def select_provider() -> VisionProvider:
    """First reachable provider, else the stub (tests/offline only).

    The stub is returned with its name so callers can say honestly that
    no live vision ran.
    """
    for probe in available_providers():
        if probe.reachable:
            return {"ollama": OllamaVisionProvider(),
                    "gemini": GeminiVisionProvider(),
                    "groq": GroqVisionProvider()}[probe.name]
    return StubVisionProvider()
