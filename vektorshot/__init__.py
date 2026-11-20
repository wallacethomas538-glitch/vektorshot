"""VektorShot — screenshot to working code, VektorCode-native.

Phase 1: screenshot (PNG) -> vision layout -> HTML + Tailwind page in
the VektorFlow design system -> Playwright self-check -> static
verification. Free-tier-first, $0 cost ledger, secrets via environment
variables only. No live model calls are wired in Phase 1: the stub
vision provider stands in for tests.

Phase 2: live Gemini (Hydrogen) vision, model-written HTML through
the same safety gates, and a real render -> compare -> fix loop.
"""

from __future__ import annotations

from .codegen import extract_html, generate_page, generate_page_direct
from .models import (
    BRAND,
    CompareResult,
    CostLedger,
    GeneratedPage,
    LayoutDescription,
    LayoutElement,
    ProbeResult,
    ScreenshotInput,
    SelfCheckResult,
    SelfCheckRun,
    VerificationIssue,
    VerificationReport,
)
from .selfcheck import (
    SelfCheckError,
    SelfCheckLoop,
    build_screenshot_command,
    compare_images,
    compare_with_vision,
    render,
    run_self_check,
    validate_target,
)
from .verify import EXTERNAL_ALLOWLIST, check_html, scan_for_tokens
from .vision import (
    GEMINI_MODEL,
    GeminiVisionProvider,
    GroqVisionProvider,
    OllamaVisionProvider,
    StubVisionProvider,
    VisionConfigError,
    VisionError,
    analyze_with_fallback,
    available_providers,
    downscale_png,
    parse_layout_reply,
    select_provider,
)

__all__ = [
    "BRAND",
    "CompareResult",
    "CostLedger",
    "GeneratedPage",
    "LayoutDescription",
    "LayoutElement",
    "ProbeResult",
    "ScreenshotInput",
    "SelfCheckResult",
    "SelfCheckRun",
    "VerificationIssue",
    "VerificationReport",
    "SelfCheckError",
    "SelfCheckLoop",
    "build_screenshot_command",
    "compare_images",
    "compare_with_vision",
    "render",
    "run_self_check",
    "validate_target",
    "EXTERNAL_ALLOWLIST",
    "check_html",
    "scan_for_tokens",
    "GEMINI_MODEL",
    "GeminiVisionProvider",
    "GroqVisionProvider",
    "OllamaVisionProvider",
    "StubVisionProvider",
    "VisionConfigError",
    "VisionError",
    "analyze_with_fallback",
    "available_providers",
    "downscale_png",
    "generate_page",
    "generate_page_direct",
    "extract_html",
    "parse_layout_reply",
    "select_provider",
]
