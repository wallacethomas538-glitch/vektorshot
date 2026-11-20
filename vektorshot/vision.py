"""Vision providers for VektorShot.

Phase 2: the Gemini (Hydrogen) provider makes live calls on the native
Google endpoint, stdlib urllib only. The key comes from the
GEMINI_API_KEY environment variable only — it is never printed, logged,
or put into generated code. Screenshots are downscaled to ~512px on the
long edge before sending: big images 503/hang under current load
(proven Nov 19).

The provider interface is small on purpose: one screenshot in, one
structured layout description out. The Gemini provider additionally
writes HTML directly from a screenshot and compares two screenshots
for the self-check loop. Groq and Ollama live calls are NOT wired yet.
"""

from __future__ import annotations

import base64
import io
import json
import os
import re
import socket
import struct
import urllib.error
import urllib.request
from abc import ABC, abstractmethod

from .models import ELEMENT_KINDS, LayoutDescription, LayoutElement, ProbeResult

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
    "downscale_png",
    "parse_layout_reply",
    "GEMINI_MODEL",
    "GEMINI_ENDPOINT",
    "MAX_IMAGE_EDGE",
    "VISION_TIMEOUT_S",
]

# Free-tier-first order, matching VektorCode's routing.
PROVIDER_ORDER = ("ollama", "gemini", "groq")

# Live Gemini route (native endpoint, proven Nov 19). AQ. keys work here;
# they are rejected on OpenAI-compatible routes.
GEMINI_MODEL = "gemini-4-hydrogen"
GEMINI_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent"
)
# Big images 503/hang: downscale before sending, allow a long timeout.
MAX_IMAGE_EDGE = 512
VISION_TIMEOUT_S = 180

LAYOUT_PROMPT = (
    "You are describing a web page screenshot so it can be rebuilt "
    "exactly. Reply ONLY in this line format, one element per line, "
    "top to bottom. Coordinates are 0-1000, origin top-left.\n\n"
    "TITLE: <the page title>\n"
    "<kind> | <exact visible text> | <x,y,width,height>\n\n"
    "Kinds: nav, heading, text, button, card, image, input, footer. "
    "Include every visible block: headers, nav, headlines, paragraphs, "
    "buttons, cards, badges, images, inputs, footers. Copy text exactly "
    "as shown. No markdown, no bullet points, no extra prose."
)

HTML_PROMPT = (
    "Rebuild the web page in this screenshot as ONE complete "
    "self-contained HTML document. Use Tailwind CSS via "
    "https://cdn.tailwindcss.com. Use system fonts only — no Google "
    "Fonts and no external font links. The only external URL allowed "
    "is the Tailwind CDN script. Match the layout, text, colors, and "
    "spacing as closely as you can. Dark VektorFlow theme "
    "(background #0B1220, cyan accent #22D3EE) unless the screenshot "
    "is clearly light-themed — then match the screenshot. Images the "
    "screenshot shows become styled placeholders naming the asset, "
    "never external URLs. Reply with only the HTML document, no "
    "explanation."
)

COMPARE_PROMPT = (
    "You are comparing two screenshots of a web page. The FIRST image "
    "is the ORIGINAL design. The SECOND image is a REBUILD of it. "
    "List every visible difference, one per line, in this format:\n\n"
    "DIFFERENCE: <what differs — name the element and how: text, "
    "layout, color, spacing, size, or a missing or extra element>\n\n"
    "Be concrete and complete. If the two images match, reply with "
    "exactly: NO DIFFERENCES. No extra prose."
)

FIX_PROMPT = (
    "The HTML below is a rebuild of the attached screenshot, but it "
    "does not match yet. Fix exactly the visible differences listed "
    "here and nothing else:\n\n"
    "{differences}\n\n"
    "Current HTML:\n"
    "```html\n"
    "{current_html}\n"
    "```\n\n"
    "Keep system fonts only — no Google Fonts, no external font "
    "links, and no new external URLs except the Tailwind CDN script. "
    "Reply with only the complete rewritten HTML document, no "
    "explanation."
)


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


def downscale_png(image_bytes: bytes, max_edge: int = MAX_IMAGE_EDGE) -> bytes:
    """Downscale a PNG so its long edge is at most max_edge pixels.

    Small images come back unchanged. Big images 503/hang on the live
    endpoint, so this runs before every vision call. Requires Pillow;
    raises VisionError with a clear message when it is missing.
    """
    width, height = _png_dimensions(image_bytes)
    if max(width, height) <= max_edge:
        return image_bytes
    try:
        from PIL import Image
    except ImportError:
        raise VisionError(
            "cannot downscale this screenshot: Pillow (PIL) is not "
            "installed. Install it with 'pip install pillow', or send "
            "an image no larger than "
            f"{max_edge}px on its long edge.") from None
    with io.BytesIO(image_bytes) as source:
        image = Image.open(source)
        image.load()
    scale = max_edge / max(width, height)
    new_size = (max(1, round(width * scale)),
                max(1, round(height * scale)))
    resized = image.convert("RGB").resize(new_size, Image.LANCZOS)
    with io.BytesIO() as out:
        resized.save(out, format="PNG")
        return out.getvalue()


def _strip_fences(text: str) -> str:
    """Drop markdown fence lines (``` or ```lang) from a model reply."""
    lines = []
    for line in (text or "").splitlines():
        if line.strip().startswith("```"):
            continue
        lines.append(line)
    return "\n".join(lines)


def _clamp_1000(value: int) -> int:
    return max(0, min(1000, value))


def parse_layout_reply(text: str, width: int, height: int) -> LayoutDescription:
    """Parse a model's structured layout reply into a LayoutDescription.

    Expected line format (see LAYOUT_PROMPT)::

        TITLE: <page title>
        <kind> | <exact visible text> | <x,y,width,height>

    Coordinates are 0-1000, origin top-left; out-of-range values are
    clamped. Malformed lines are skipped and counted in ``notes`` —
    one bad line never kills the whole layout. A reply with no
    parseable elements raises VisionError.
    """
    cleaned = _strip_fences(text)
    title = "Untitled page"
    elements = []
    skipped = 0
    for raw_line in cleaned.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.upper().startswith("TITLE:"):
            candidate = line.split(":", 1)[1].strip()
            if candidate:
                title = candidate
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 3:
            skipped += 1
            continue
        kind = parts[0].strip().lower()
        if kind not in ELEMENT_KINDS:
            skipped += 1
            continue
        coords_text = parts[-1]
        text_value = "|".join(parts[1:-1]).strip()
        try:
            coords = [int(v.strip()) for v in coords_text.split(",")]
            if len(coords) != 4:
                raise ValueError("need exactly 4 coordinates")
        except ValueError:
            skipped += 1
            continue
        x, y, w, h = (_clamp_1000(v) for v in coords)
        elements.append(LayoutElement(
            kind=kind, text=text_value, x=x, y=y, width=w, height=h))
    if not elements:
        raise VisionError(
            "could not parse any layout elements from the model's reply. "
            "The model did not follow the 'kind | text | x,y,w,h' line "
            "format — re-prompt it, do not guess a layout.")
    notes = "live Gemini layout"
    if skipped:
        notes += f"; {skipped} malformed line(s) skipped"
    return LayoutDescription(
        page_title=title, width=width, height=height,
        elements=elements, notes=notes)


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
        # A configured key is checked first so a missing key fails with
        # the config error above instead of a confusing network error.
        self._api_key()
        if not image_bytes:
            raise ValueError("screenshot is empty")
        raise VisionError(
            f"{self.provider_label} live calls are not wired yet. "
            "Use the stub provider for tests.")

    def probe(self) -> ProbeResult:
        configured = bool(os.environ.get(self.env_var, "").strip())
        return ProbeResult(
            name=self.name, reachable=False,
            reason=(f"{self.env_var} is set (live calls not wired yet)"
                    if configured else
                    f"{self.env_var} is not set"))


class GeminiVisionProvider(_EnvVisionProvider):
    """Gemini (Hydrogen) vision — LIVE in Phase 2.

    Key from GEMINI_API_KEY only. Calls the native endpoint with
    stdlib urllib; the key travels as a ``?key=`` query parameter
    (the registered placement) and is never printed or logged.
    """

    name = "gemini"
    env_var = "GEMINI_API_KEY"
    provider_label = "Gemini"

    def __init__(self, model: str = GEMINI_MODEL,
                 timeout_s: int = VISION_TIMEOUT_S):
        self.model = model
        self.timeout_s = timeout_s

    def _endpoint(self) -> str:
        return (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent"
        )

    def _call_model(self, images, prompt: str) -> str:
        """One generateContent call with 1+ PNG images. Returns raw text.

        ``images`` is a list of (mime_type, bytes). Errors are honest
        and never include the key or the request URL.
        """
        key = self._api_key()
        parts = [{"text": prompt}]
        for mime_type, image_bytes in images:
            parts.append({"inline_data": {
                "mime_type": mime_type,
                "data": base64.b64encode(image_bytes).decode("ascii")}})
        body = json.dumps(
            {"contents": [{"parts": parts}]}).encode("utf-8")
        request = urllib.request.Request(
            self._endpoint() + "?key=" + key,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST")
        try:
            with urllib.request.urlopen(
                    request, timeout=self.timeout_s) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 503:
                raise VisionError(
                    "Gemini is overloaded (HTTP 503, high demand). "
                    "Wait and retry once later — do not hammer retries."
                ) from None
            if exc.code in (401, 403):
                raise VisionConfigError(
                    "Gemini rejected the key "
                    f"(HTTP {exc.code}). Check GEMINI_API_KEY — the "
                    "saved key may be revoked or for the wrong "
                    "project.") from None
            raise VisionError(
                f"Gemini call failed (HTTP {exc.code}).") from None
        except (urllib.error.URLError, TimeoutError,
                socket.timeout) as exc:
            raise VisionError(
                "Gemini call failed or timed out after "
                f"{self.timeout_s}s ({exc}). The model may be "
                "overloaded — wait and retry once later.") from None
        except json.JSONDecodeError:
            raise VisionError(
                "Gemini returned a response that is not JSON.") from None
        try:
            text_parts = []
            for candidate in payload.get("candidates", []):
                content = candidate.get("content", {})
                for part in content.get("parts", []):
                    if isinstance(part.get("text"), str):
                        text_parts.append(part["text"])
            text = "".join(text_parts).strip()
        except (AttributeError, TypeError):
            text = ""
        if not text:
            raise VisionError(
                "Gemini returned no text. The call may have been "
                "blocked — retry once, then report it as a failed "
                "vision call, not a layout.")
        return text

    def analyze_screenshot(self, image_bytes: bytes) -> LayoutDescription:
        """Live layout read: downscale, call Gemini, parse the reply."""
        self._api_key()
        if not image_bytes:
            raise ValueError("screenshot is empty")
        small = downscale_png(image_bytes)
        width, height = _png_dimensions(small)
        reply = self._call_model([("image/png", small)], LAYOUT_PROMPT)
        layout = parse_layout_reply(reply, width, height)
        layout.notes += f" (model {self.model})"
        return layout

    def generate_html(self, image_bytes: bytes,
                      prompt: str | None = None) -> str:
        """Ask Gemini to write the page's HTML directly from a screenshot.

        Returns the model's raw reply text (usually a full HTML
        document). Callers must pass it through
        ``generate_page_direct`` before trusting it.
        """
        self._api_key()
        if not image_bytes:
            raise ValueError("screenshot is empty")
        small = downscale_png(image_bytes)
        return self._call_model(
            [("image/png", small)], prompt or HTML_PROMPT)

    def compare_screenshots(self, original_bytes: bytes,
                           render_bytes: bytes) -> list:
        """Ask Gemini to list visible differences between two screenshots.

        First image is the original design, second is the rebuild.
        Returns a list of difference strings; an exact match is [].
        """
        self._api_key()
        if not original_bytes or not render_bytes:
            raise ValueError("both screenshots are required to compare")
        small_original = downscale_png(original_bytes)
        small_render = downscale_png(render_bytes)
        reply = self._call_model(
            [("image/png", small_original), ("image/png", small_render)],
            COMPARE_PROMPT)
        cleaned = _strip_fences(reply).strip()
        if cleaned.upper().startswith("NO DIFFERENCES"):
            return []
        differences = []
        for line in cleaned.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.upper().startswith("DIFFERENCE:"):
                line = line.split(":", 1)[1].strip()
            # Strip list markers only ("- ", "* ", "1. ", "2) ") — never
            # eat real content that happens to start with a digit.
            line = re.sub(r"^(\s*[-*•]\s+|\s*\d+[.)]\s+)", "", line).strip()
            if line:
                differences.append(line)
        return differences

    def probe(self) -> ProbeResult:
        configured = bool(os.environ.get(self.env_var, "").strip())
        return ProbeResult(
            name=self.name, reachable=configured,
            reason=(f"{self.env_var} is set; live calls wired "
                    "(Phase 2) — key presence is not proof it works"
                    if configured else
                    f"{self.env_var} is not set"))


class GroqVisionProvider(_EnvVisionProvider):
    """Groq vision. Key from GROQ_API_KEY only. Live calls not wired."""

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
            "Ollama live calls are not wired yet. Use the stub "
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

    Ollama is probed over local HTTP (no key). Gemini reports key
    presence only — presence is not proof the key works. Groq is
    never reachable: its live calls are not wired.
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
