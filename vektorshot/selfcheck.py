"""Self-check loop for VektorShot.

Render the generated page headless, screenshot it, compare it against
the original screenshot, and fix what does not match — up to N rounds,
then hand over what exists with an honest report.

Phase 1 provided the command builder and the pure decide logic.
Phase 2 wires the loop for real:

- ``render`` accepts an optional ``executable_path`` for Chromium
  (the pip-installed Playwright wants headless-shell 1255 while the
  cache holds Chromium 1248 — pass that binary's path when needed).
- ``compare_images`` scores two screenshots with a PIL pixel diff,
  or an honestly-labeled weak byte-length fallback when PIL is absent.
- ``compare_with_vision`` asks the vision model to list concrete
  visible differences between the original and the rebuild.
- ``run_self_check`` runs render -> compare -> fix (re-prompt the
  model with the difference list) for up to 3 rounds.
"""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import urlparse

from .codegen import generate_page_direct
from .models import CompareResult, SelfCheckResult, SelfCheckRun
from .vision import FIX_PROMPT, VisionError

__all__ = [
    "SelfCheckError",
    "validate_target",
    "build_screenshot_command",
    "SelfCheckLoop",
    "render",
    "compare_images",
    "compare_with_vision",
    "run_self_check",
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
           timeout_s=30, executable_path=None):
    """Screenshot a rendered page. Returns the output path.

    Raises SelfCheckError when Playwright is not installed or no
    browser can be launched — never a bare traceback. Pass
    ``executable_path`` when the Playwright-managed browser is not
    the one to use (e.g. the cache holds Chromium 1248 while the
    installed Playwright expects headless-shell 1255).
    """
    target = validate_target(target)
    out = Path(output_png)
    command = build_screenshot_command(target, out, width, height, full_page)
    # Playwright's goto needs a URL: a local file path becomes file://.
    # (The CLI command above takes a plain path; only goto needs this.)
    parsed = urlparse(target)
    if parsed.scheme in ("http", "https"):
        goto_target = target
    else:
        goto_target = Path(target).resolve().as_uri()
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
            launch_kwargs = {"headless": True}
            if executable_path:
                launch_kwargs["executable_path"] = str(executable_path)
            try:
                browser = playwright.chromium.launch(**launch_kwargs)
            except Exception as exc:
                hint = ""
                if "Executable doesn't exist" in str(exc):
                    hint = (" Pass executable_path to render() with the "
                            "Chromium binary to use.")
                raise SelfCheckError(
                    f"Could not launch Chromium: {exc}. Rendering needs "
                    "a working browser; run where one exists (local "
                    f"Termux or Daytona).{hint}") from None
            try:
                page = browser.new_page(viewport={"width": width,
                                                  "height": height})
                page.goto(goto_target, timeout=timeout_s * 1000)
                page.wait_for_timeout(1000)
                page.screenshot(path=str(out), full_page=full_page)
            finally:
                browser.close()
    except SelfCheckError:
        raise
    except Exception as exc:
        raise SelfCheckError(f"Render failed: {exc}") from None
    return out


def _read_png_bytes(source) -> bytes:
    """Accept PNG bytes or a path to a PNG file. Anything else errors."""
    if isinstance(source, (bytes, bytearray)):
        data = bytes(source)
    else:
        path = Path(source)
        if not path.is_file():
            raise ValueError(
                f"screenshot not found: {source!r}")
        data = path.read_bytes()
    if not data.startswith(b"\x89PNG"):
        raise ValueError("screenshot must be a PNG image")
    return data


def compare_images(original, render) -> CompareResult:
    """Score how alike two screenshots are, 0.0-1.0.

    With Pillow: both images are resized to 128x128 thumbnails and
    the mean per-channel pixel difference becomes the score. That is
    a guide, not proof — a page can score high and still read wrong.

    Without Pillow: the stdlib fallback compares byte lengths only.
    It is honestly labeled weak (``weak=True``): two different pages
    of similar size score high. Never present a weak score as a
    visual match.
    """
    original_bytes = _read_png_bytes(original)
    render_bytes = _read_png_bytes(render)
    try:
        from PIL import Image
    except ImportError:
        if not original_bytes or not render_bytes:
            return CompareResult(similarity=0.0, method="byte-length",
                                 weak=True)
        similarity = (min(len(original_bytes), len(render_bytes))
                      / max(len(original_bytes), len(render_bytes)))
        return CompareResult(similarity=round(similarity, 4),
                             method="byte-length", weak=True)
    import io
    with io.BytesIO(original_bytes) as buf:
        original_image = Image.open(buf).convert("RGB")
        original_image.load()
    with io.BytesIO(render_bytes) as buf:
        render_image = Image.open(buf).convert("RGB")
        render_image.load()
    size = (128, 128)
    original_small = original_image.resize(size, Image.LANCZOS)
    render_small = render_image.resize(size, Image.LANCZOS)
    original_pixels = list(original_small.getdata())
    render_pixels = list(render_small.getdata())
    total = 0
    for (r1, g1, b1), (r2, g2, b2) in zip(original_pixels, render_pixels):
        total += abs(r1 - r2) + abs(g1 - g2) + abs(b1 - b2)
    mean_diff = total / (len(original_pixels) * 3)
    similarity = max(0.0, min(1.0, 1.0 - mean_diff / 255.0))
    return CompareResult(similarity=round(similarity, 4),
                         method="pil-pixel-diff", weak=False)


def compare_with_vision(original, render, vision) -> list:
    """Ask the vision model to list visible differences (original vs rebuild).

    Returns a list of difference strings; an exact match is []. Raises
    SelfCheckError when the provider cannot compare images or the
    comparison call itself fails.
    """
    original_bytes = _read_png_bytes(original)
    render_bytes = _read_png_bytes(render)
    compare = getattr(vision, "compare_screenshots", None)
    if compare is None:
        raise SelfCheckError(
            "this vision provider cannot compare two screenshots: it "
            "has no compare_screenshots method")
    try:
        differences = compare(original_bytes, render_bytes)
    except VisionError as exc:
        raise SelfCheckError(f"vision comparison failed: {exc}") from None
    if not isinstance(differences, list):
        raise SelfCheckError(
            "vision comparison returned something that is not a list "
            "of differences")
    return [str(d) for d in differences if str(d).strip()]


def run_self_check(original_png, initial_html, vision, workdir,
                   loop=None, width=1280, height=800,
                   render_fn=None, compare_fn=None) -> SelfCheckRun:
    """Run render -> compare -> fix for up to ``loop.max_rounds`` rounds.

    - ``original_png``: the original screenshot (PNG bytes or path).
    - ``initial_html``: already-gated HTML (from ``generate_page`` or
      ``generate_page_direct``).
    - ``vision``: provider with ``generate_html(image_bytes, prompt)``
      and ``compare_screenshots(original, render)`` (Gemini in
      Phase 2; fakes in tests).
    - ``workdir``: directory for round-*.html / round-*.png files.
    - ``render_fn`` / ``compare_fn``: injectable seams for tests;
      default to ``render`` and ``compare_images``.

    Returns a SelfCheckRun: the round history, the final HTML, its
    path, and whether any round was accepted. A page is accepted only
    when a round's similarity reaches the threshold; anything else is
    handed over as-is with the history saying so.
    """
    loop = loop or SelfCheckLoop()
    original_bytes = _read_png_bytes(original_png)
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    render_fn = render_fn or render
    compare_fn = compare_fn or compare_images

    history = []
    notes = []
    current_html = initial_html
    html_path = workdir / "round-0.html"
    html_path.write_text(current_html, encoding="utf-8")
    accepted = False

    for round_no in range(1, loop.max_rounds + 1):
        html_path = workdir / f"round-{round_no}.html"
        html_path.write_text(current_html, encoding="utf-8")
        render_path = workdir / f"round-{round_no}.png"
        try:
            render_fn(str(html_path), str(render_path), width, height)
        except SelfCheckError as exc:
            notes.append(f"round {round_no}: render failed: {exc}")
            break
        render_bytes = render_path.read_bytes()
        compared = compare_fn(original_bytes, render_bytes)
        try:
            differences = compare_with_vision(
                original_bytes, render_bytes, vision)
        except SelfCheckError as exc:
            result = loop.record(round_no, compared.similarity,
                                 issues=[str(exc)])
            history.append(result)
            notes.append(f"round {round_no}: {exc}; cannot fix "
                         "without a difference list")
            break
        result = loop.record(round_no, compared.similarity,
                             issues=differences)
        history.append(result)
        if compared.weak:
            notes.append(
                f"round {round_no}: similarity {compared.similarity:.2f} "
                f"is a weak {compared.method} score, not a visual match")
        if result.verdict == "accept":
            accepted = True
            break
        if result.verdict == "give_up":
            break
        # verdict == "fix": re-prompt the model with the difference list.
        fix_prompt = FIX_PROMPT.format(
            differences="\n".join(f"- {d}" for d in differences)
            or "- (no specific differences listed)",
            current_html=current_html)
        try:
            reply = vision.generate_html(original_bytes, fix_prompt)
            fixed = generate_page_direct(reply, model="gemini-4-hydrogen")
        except (VisionError, ValueError) as exc:
            notes.append(f"round {round_no}: fix failed: {exc}")
            break
        current_html = fixed.html
        html_path = workdir / f"round-{round_no}-fixed.html"
        html_path.write_text(current_html, encoding="utf-8")

    return SelfCheckRun(history=history, html=current_html,
                        html_path=str(html_path), accepted=accepted,
                        notes=notes)
