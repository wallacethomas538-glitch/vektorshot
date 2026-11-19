"""Self-check loop for VektorShot Phase 1.

Render the generated page headless, screenshot it, compare it against
the original screenshot, and fix what does not match — up to N rounds,
then hand over what exists with an honest report.

Phase 1 provides the command builder and the pure loop logic. The
render step runs only when Playwright and a browser are actually
available; in this environment there is no live browser, so render()
fails cleanly with a clear error instead of pretending.
"""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import urlparse

from .models import SelfCheckResult

__all__ = [
    "SelfCheckError",
    "validate_target",
    "build_screenshot_command",
    "SelfCheckLoop",
    "render",
]

DEFAULT_MAX_ROUNDS = 3
DEFAULT_ACCEPT_THRESHOLD = 0.85


class SelfCheckError(Exception):
    """A self-check round could not run: bad input or missing browser."""


def validate_target(target):
    """A render target is an http(s) URL or an existing local HTML file."""
    if not isinstance(target, str) or not target.strip():
        raise ValueError("render target must be a non-empty string")
    target = target.strip()
    parsed = urlparse(target)
    if parsed.scheme in ("http", "https") and parsed.netloc:
        return target
    path = Path(target)
    if path.is_file():
        return str(path)
    raise ValueError(
        f"render target must be an http(s) URL or an existing HTML file, "
        f"got: {target!r}")


def build_screenshot_command(target, output_png, width=1280, height=800,
                             full_page=False):
    """Build the argv for screenshotting a rendered page.

    Uses the Playwright CLI (``playwright screenshot``). The command is
    built, not run: the caller runs it where a browser exists — local
    Termux or Daytona, never Render free tier (Chromium does not fit
    in 512 MB).
    """
    target = validate_target(target)
    if not isinstance(output_png, (str, Path)) or not str(output_png).strip():
        raise ValueError("output PNG path must be a non-empty string")
    if width <= 0 or height <= 0:
        raise ValueError("viewport width and height must be positive")
    command = [sys.executable, "-m", "playwright", "screenshot",
               f"--viewport-size={width},{height}"]
    if full_page:
        command.append("--full-page")
    command += [target, str(output_png)]
    return command


class SelfCheckLoop:
    """Pure decide logic for the render -> compare -> fix loop."""

    def __init__(self, max_rounds=DEFAULT_MAX_ROUNDS,
                 accept_threshold=DEFAULT_ACCEPT_THRESHOLD):
        if max_rounds < 1:
            raise ValueError("max_rounds must be at least 1")
        if not 0.0 < accept_threshold <= 1.0:
            raise ValueError("accept_threshold must be in (0.0, 1.0]")
        self.max_rounds = max_rounds
        self.accept_threshold = accept_threshold

    def decide(self, similarity, round_no):
        """Next step after a compare round: accept, fix, or give up."""
        if not 0.0 <= similarity <= 1.0:
            raise ValueError("similarity must be between 0.0 and 1.0")
        if round_no < 1:
            raise ValueError("round_no starts at 1")
        if similarity >= self.accept_threshold:
            return "accept"
        if round_no < self.max_rounds:
            return "fix"
        return "give_up"

    def record(self, round_no, similarity, issues=None):
        """Wrap one compare result with its verdict."""
        return SelfCheckResult(
            round_no=round_no, similarity=similarity,
            issues=list(issues or []),
            verdict=self.decide(similarity, round_no))

    def summarize(self, history):
        """Honest handover line for a finished loop."""
        if not history:
            return "self-check did not run: no rounds recorded"
        last = history[-1]
        if last.verdict == "accept":
            return (f"self-check passed on round {last.round_no} "
                    f"(similarity {last.similarity:.2f})")
        if last.verdict == "give_up":
            return (f"self-check gave up after {len(history)} rounds: "
                    f"best similarity {max(r.similarity for r in history):.2f}, "
                    f"still below {self.accept_threshold}. Handing over "
                    "as-is — do not call it a match.")
        return (f"self-check stopped mid-loop on round {last.round_no} "
                f"(similarity {last.similarity:.2f})")


def render(target, output_png, width=1280, height=800, full_page=False,
           timeout_s=30):
    """Screenshot a rendered page. Returns the output path.

    Raises SelfCheckError when Playwright is not installed or no
    browser can be launched — never a bare traceback.
    """
    target = validate_target(target)
    out = Path(output_png)
    command = build_screenshot_command(target, out, width, height, full_page)
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise SelfCheckError(
            "Playwright is not installed. Install it with "
            "'pip install playwright' and then 'playwright install "
            "chromium' before rendering.") from None
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        with sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch(headless=True)
            except Exception as exc:
                raise SelfCheckError(
                    f"Could not launch Chromium: {exc}. Rendering needs "
                    "a working browser; run where one exists (local "
                    "Termux or Daytona).") from None
            try:
                page = browser.new_page(viewport={"width": width,
                                                  "height": height})
                page.goto(target, timeout=timeout_s * 1000)
                page.wait_for_timeout(1000)
                page.screenshot(path=str(out), full_page=full_page)
            finally:
                browser.close()
    except SelfCheckError:
        raise
    except Exception as exc:
        raise SelfCheckError(f"Render failed: {exc}") from None
    return out
