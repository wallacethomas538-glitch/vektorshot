"""Typed inputs and outputs for VektorShot Phase 1.

All types are plain dataclasses with no third-party dependencies.
Coordinates are normalized 0-1000, origin top-left.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = [
    "LayoutElement",
    "LayoutDescription",
    "ScreenshotInput",
    "GeneratedPage",
    "SelfCheckResult",
    "VerificationIssue",
    "VerificationReport",
    "CostLedger",
    "ProbeResult",
]

ELEMENT_KINDS = {
    "heading", "text", "button", "nav", "image", "input", "card", "footer",
}

# VektorFlow brand tokens (the design system every generated page uses).
BRAND = {
    "bg": "#0B1220",
    "surface": "#111827",
    "accent": "#22D3EE",
    "accent2": "#06B6D4",
    "text": "#F1F5F9",
    "muted": "#94A3B8",
}


@dataclass
class LayoutElement:
    """One thing the vision pass saw on the screenshot."""

    kind: str = "text"
    text: str = ""
    x: int = 0
    y: int = 0
    width: int = 100
    height: int = 40

    def __post_init__(self):
        if self.kind not in ELEMENT_KINDS:
            raise ValueError(f"unknown element kind: {self.kind!r}")
        for name in ("x", "y", "width", "height"):
            value = getattr(self, name)
            if not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative int")


@dataclass
class LayoutDescription:
    """What the vision pass understood from a screenshot."""

    page_title: str = "Untitled page"
    width: int = 1280
    height: int = 800
    elements: list = field(default_factory=list)
    palette: dict = field(default_factory=lambda: dict(BRAND))
    notes: str = ""

    def headings(self):
        return [e for e in self.elements if e.kind == "heading"]

    def buttons(self):
        return [e for e in self.elements if e.kind == "button"]


@dataclass
class ScreenshotInput:
    """A screenshot handed to VektorShot, from a file or chat upload."""

    source: str = "chat-upload"
    image_bytes: bytes = b""
    width: int = 0
    height: int = 0

    def validate(self):
        if not self.image_bytes:
            raise ValueError("screenshot is empty")
        if not self.image_bytes.startswith(b"\x89PNG"):
            raise ValueError("screenshot must be a PNG image")
        return self


@dataclass
class GeneratedPage:
    """A page produced from a layout description."""

    html: str = ""
    title: str = ""
    cost_usd: float = 0.0
    model: str = ""
    rounds: int = 0


@dataclass
class SelfCheckResult:
    """One round of render -> screenshot -> compare."""

    round_no: int = 1
    similarity: float = 0.0
    issues: list = field(default_factory=list)
    verdict: str = "fix"  # "accept" | "fix" | "give_up"

    def __post_init__(self):
        if self.verdict not in ("accept", "fix", "give_up"):
            raise ValueError(f"unknown verdict: {self.verdict!r}")
        if not 0.0 <= self.similarity <= 1.0:
            raise ValueError("similarity must be between 0.0 and 1.0")


@dataclass
class VerificationIssue:
    code: str
    message: str
    severity: str = "error"  # "error" | "warning"


@dataclass
class VerificationReport:
    passed: bool
    issues: list = field(default_factory=list)
    requires_live_render: bool = True
    # Console errors and real rendering can only be proven by a live
    # browser run; static checks alone never claim a page is good.


@dataclass
class CostLedger:
    """Every generation is costed. Free-tier-first means $0.00, proven."""

    entries: list = field(default_factory=list)

    def record_free(self, model):
        self.entries.append({"model": model, "cost_usd": 0.0})

    def record(self, model, cost_usd):
        if cost_usd < 0:
            raise ValueError("cost cannot be negative")
        self.entries.append({"model": model, "cost_usd": cost_usd})

    @property
    def total_usd(self):
        return round(sum(e["cost_usd"] for e in self.entries), 4)


@dataclass
class ProbeResult:
    """Reachability check for one vision route. No model call is made."""

    name: str
    reachable: bool
    reason: str
