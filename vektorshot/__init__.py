"""VektorShot — screenshot to working code, VektorCode-native.

Phase 1: screenshot (PNG) -> vision layout -> HTML + Tailwind page in
the VektorFlow design system -> Playwright self-check -> static
verification. Free-tier-first, $0 cost ledger, secrets via environment
variables only. No live model calls are wired in Phase 1: the stub
vision provider stands in for tests.
"""

from __future__ import annotations

from .codegen import generate_page
from .models import (
    BRAND,
    CostLedger,
    GeneratedPage,
    LayoutDescription,
    LayoutElement,
    ProbeResult,
    ScreenshotInput,
    SelfCheckResult,
    VerificationIssue,
    VerificationReport,
)
from .selfcheck import (
    SelfCheckError,
    SelfCheckLoop,
    build_screenshot_command,
    render,
    validate_target,
)
from .verify import EXTERNAL_ALLOWLIST, check_html, scan_for_tokens
from .vision import (
    GeminiVisionProvider,
    GroqVisionProvider,
    OllamaVisionProvider,
    StubVisionProvider,
    VisionConfigError,
    VisionError,
    available_providers,
    select_provider,
)

__all__ = [
    "BRAND",
    "CostLedger",
    "GeneratedPage",
    "LayoutDescription",
    "LayoutElement",
    "ProbeResult",
    "ScreenshotInput",
    "SelfCheckResult",
    "VerificationIssue",
    "VerificationReport",
    "SelfCheckError",
    "SelfCheckLoop",
    "build_screenshot_command",
    "render",
    "validate_target",
    "EXTERNAL_ALLOWLIST",
    "check_html",
    "scan_for_tokens",
    "GeminiVisionProvider",
    "GroqVisionProvider",
    "OllamaVisionProvider",
    "StubVisionProvider",
    "VisionConfigError",
    "VisionError",
    "available_providers",
    "generate_page",
    "select_provider",
]
