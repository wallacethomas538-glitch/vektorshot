"""VektorShot Phase 2 tests — 21 tests, fake-only.

No live model calls, no keys, no network: the Gemini transport is
mocked at urllib.request.urlopen, Playwright is never launched, and
the self-check loop runs against injected fakes. PNG fixtures are
built in-test with struct+zlib (stdlib only).
"""

import json
import struct
import sys
import urllib.error
import zlib
from pathlib import Path

import pytest

from vektorshot import (
    CompareResult,
    GeminiVisionProvider,
    SelfCheckLoop,
    VisionError,
    check_html,
    compare_images,
    compare_with_vision,
    downscale_png,
    extract_html,
    generate_page_direct,
    parse_layout_reply,
    run_self_check,
)
from vektorshot.selfcheck import SelfCheckError

FIXTURE_KEY = "test-key-not-real-12345"

LAYOUT_REPLY = """TITLE: Test Page
nav | Home About Contact | 0,0,1000,60
heading | Hello World | 80,120,840,70
text | Build anything from a screenshot. | 80,210,600,40
button | Get started | 80,280,160,48
"""

CANNED_HTML = """<!DOCTYPE html>
<html><head><title>Fixed Page</title>
<script src="https://cdn.tailwindcss.com"></script>
</head><body>
<h1 class="text-4xl">Hello World</h1>
<p>Build anything from a screenshot.</p>
</body></html>
"""


def make_png(width=64, height=48, rgb=(11, 18, 32)):
    """A minimal valid PNG, built with stdlib only."""
    def chunk(kind, data):
        out = struct.pack(">I", len(data)) + kind + data
        return out + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    raw = b"".join(b"\x00" + bytes(rgb) * width for _ in range(height))
    return sig + ihdr + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def png_size(data: bytes):
    return struct.unpack(">II", data[16:24])


class FakeResponse:
    """Stand-in for a urllib response: canned JSON payload."""

    def __init__(self, payload):
        self._payload = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeVision:
    """Fake provider for the loop tests: canned differences + canned HTML."""

    def __init__(self, differences_per_round, html=CANNED_HTML):
        self._differences = list(differences_per_round)
        self._html = html
        self.fix_prompts = []

    def compare_screenshots(self, original_bytes, render_bytes):
        if self._differences:
            return self._differences.pop(0)
        return []

    def generate_html(self, image_bytes, prompt):
        self.fix_prompts.append(prompt)
        return self._html


# --- Vision: downscale (3) --------------------------------------------

def test_downscale_big_image():
    big = make_png(1024, 768)
    small = downscale_png(big)
    assert png_size(small) == (512, 384)


def test_downscale_small_image_unchanged():
    small = make_png(64, 48)
    assert downscale_png(small) == small


def test_downscale_rejects_non_png():
    with pytest.raises(ValueError, match="must be a PNG"):
        downscale_png(b"this is not a png")


# --- Vision: parse layout reply (3) ------------------------------------

def test_parse_layout_reply_ok():
    layout = parse_layout_reply(LAYOUT_REPLY, 800, 600)
    assert layout.page_title == "Test Page"
    assert layout.width == 800 and layout.height == 600
    assert [e.kind for e in layout.elements] == [
        "nav", "heading", "text", "button"]
    assert layout.elements[1].text == "Hello World"
    assert (layout.elements[1].x, layout.elements[1].y,
            layout.elements[1].width, layout.elements[1].height) == (
        80, 120, 840, 70)


def test_parse_layout_reply_clamps_and_skips():
    reply = (
        "TITLE: Clamp Test\n"
        "heading | Too Far | 900,900,1200,500\n"
        "bogus-kind | Nope | 0,0,10,10\n"
        "text | Bad Coords | 1,2,3\n"
        "text | Good One | 0,0,100,20\n"
    )
    layout = parse_layout_reply(reply, 100, 100)
    assert len(layout.elements) == 2
    assert layout.elements[0].x == 900
    assert layout.elements[0].width == 1000  # 1200 clamped to 1000
    assert layout.elements[0].height == 500
    assert layout.elements[1].text == "Good One"
    assert "2 malformed" in layout.notes


def test_parse_layout_reply_empty_raises():
    with pytest.raises(VisionError, match="could not parse"):
        parse_layout_reply("TITLE: Nothing Here\n\n", 100, 100)


# --- Vision: mocked live Gemini calls (2) -------------------------------

def test_gemini_live_call_mocked(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", FIXTURE_KEY)
    seen = {}

    def fake_urlopen(request, timeout=None):
        seen["url"] = request.full_url
        seen["body"] = request.data.decode("utf-8")
        payload = {"candidates": [{"content": {"parts": [
            {"text": LAYOUT_REPLY}]}}]}
        return FakeResponse(payload)

    monkeypatch.setattr(
        "vektorshot.vision.urllib.request.urlopen", fake_urlopen)
    layout = GeminiVisionProvider().analyze_screenshot(make_png())
    assert layout.page_title == "Test Page"
    assert len(layout.elements) == 4
    assert "gemini-4-hydrogen:generateContent" in seen["url"]
    # The key travels only as the ?key= query parameter, never in the body.
    assert FIXTURE_KEY not in seen["body"]
    assert "inline_data" in seen["body"]


def test_gemini_503_is_honest_error(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", FIXTURE_KEY)
    calls = []

    def fake_urlopen(request, timeout=None):
        calls.append(request)
        raise urllib.error.HTTPError(
            request.full_url, 503, "Service Unavailable", {}, None)

    monkeypatch.setattr(
        "vektorshot.vision.urllib.request.urlopen", fake_urlopen)
    with pytest.raises(VisionError, match="503"):
        GeminiVisionProvider().analyze_screenshot(make_png())
    assert len(calls) == 1  # no hammering retries


# --- Codegen: direct path (5) -------------------------------------------

def test_extract_html_strips_fences_and_adds_doctype():
    fenced = ("Here is the page:\n```html\n<html><head><title>t</title>"
              "</head><body><p>hi</p></body></html>\n```\nDone.")
    doc = extract_html(fenced)
    assert doc.startswith("<!DOCTYPE html>")
    assert doc.endswith("</html>")
    assert "```" not in doc
    assert "Here is the page" not in doc


def test_extract_html_no_html_raises():
    with pytest.raises(ValueError, match="no HTML document"):
        extract_html("Just some prose, no tags at all.")


def test_direct_secret_refused():
    reply = ("<!DOCTYPE html><html><head><title>t</title></head><body>"
             "<p>key sk-testtoken-abcdef12345678</p></body></html>")
    with pytest.raises(ValueError, match="secret"):
        generate_page_direct(reply)


def test_direct_unsafe_replies_refused():
    base = ("<!DOCTYPE html><html><head><title>t</title></head>"
            "<body>{body}</body></html>")
    with pytest.raises(ValueError, match="javascript"):
        generate_page_direct(base.format(
            body='<a href="javascript:alert(1)">x</a>'))
    with pytest.raises(ValueError, match="inline event handler"):
        generate_page_direct(base.format(
            body='<button onclick="steal()">x</button>'))
    with pytest.raises(ValueError, match="not allowlisted"):
        generate_page_direct(base.format(
            body='<img src="https://evil.example/x.png">'))
    # The Tailwind CDN is the one allowlisted external.
    ok = generate_page_direct(base.format(
        body='<script src="https://cdn.tailwindcss.com"></script>'))
    assert "cdn.tailwindcss.com" in ok.html


def test_direct_injects_tailwind_and_title():
    reply = ("<!DOCTYPE html><html><head></head><body>"
             "<h1>Hi</h1></body></html>")
    page = generate_page_direct(reply, title="My Page")
    assert "https://cdn.tailwindcss.com" in page.html
    assert "<title>My Page</title>" in page.html
    assert page.title == "My Page"
    assert check_html(page.html).passed


# --- Self-check: compare (4) ---------------------------------------------

def test_compare_identical_images():
    png = make_png()
    result = compare_images(png, png)
    assert isinstance(result, CompareResult)
    assert result.similarity == 1.0
    assert result.method == "pil-pixel-diff"
    assert result.weak is False


def test_compare_different_images():
    dark = make_png(rgb=(11, 18, 32))
    light = make_png(rgb=(240, 240, 240))
    result = compare_images(dark, light)
    assert result.similarity < 0.5
    assert result.weak is False


def test_compare_weak_fallback_without_pil(monkeypatch):
    monkeypatch.setitem(sys.modules, "PIL", None)
    png = make_png()
    result = compare_images(png, png)
    assert result.weak is True
    assert result.method == "byte-length"
    assert result.similarity == 1.0  # same bytes, same length
    bigger = make_png(128, 96)
    weaker = compare_images(png, bigger)
    assert weaker.weak is True
    assert weaker.similarity < 1.0


def test_compare_with_vision_fake_and_missing_method():
    vision = FakeVision([["heading too small", "button missing"]])
    differences = compare_with_vision(make_png(), make_png(), vision)
    assert differences == ["heading too small", "button missing"]

    class NoCompare:
        pass

    with pytest.raises(SelfCheckError, match="cannot compare"):
        compare_with_vision(make_png(), make_png(), NoCompare())


# --- Self-check: wired loop (3) ------------------------------------------

def _fake_render_factory(png_bytes):
    def fake_render(target, output_png, width, height):
        Path(output_png).write_bytes(png_bytes)
        return Path(output_png)
    return fake_render


def test_run_accepts_first_round(tmp_path):
    original = make_png()
    vision = FakeVision([[]])
    run = run_self_check(
        original, CANNED_HTML, vision, tmp_path,
        render_fn=_fake_render_factory(original),
        compare_fn=lambda a, b: CompareResult(similarity=0.95))
    assert run.accepted is True
    assert len(run.history) == 1
    assert run.history[0].verdict == "accept"
    assert run.html == CANNED_HTML


def test_run_fixes_then_accepts(tmp_path):
    original = make_png()
    scores = iter([0.5, 0.95])
    vision = FakeVision([["heading too small"], []])
    run = run_self_check(
        original, CANNED_HTML, vision, tmp_path,
        render_fn=_fake_render_factory(original),
        compare_fn=lambda a, b: CompareResult(
            similarity=next(scores)))
    assert run.accepted is True
    assert len(run.history) == 2
    assert run.history[0].verdict == "fix"
    assert run.history[1].verdict == "accept"
    assert run.history[0].issues == ["heading too small"]
    assert "heading too small" in vision.fix_prompts[0]
    assert "Fixed Page" in run.html


def test_run_gives_up_after_max_rounds(tmp_path):
    original = make_png()
    vision = FakeVision([["x off"], ["x off"], ["x off"]])
    run = run_self_check(
        original, CANNED_HTML, vision, tmp_path,
        loop=SelfCheckLoop(max_rounds=3, accept_threshold=0.85),
        render_fn=_fake_render_factory(original),
        compare_fn=lambda a, b: CompareResult(similarity=0.5))
    assert run.accepted is False
    assert len(run.history) == 3
    assert run.history[-1].verdict == "give_up"
    assert "gave up" in SelfCheckLoop().summarize(run.history).lower()


def test_prompts_forbid_external_fonts():
    # Live run Nov 19: the model added a Google Fonts link and the
    # safety gate correctly refused the page. The prompts must tell
    # the model system fonts only, so the gate never has to refuse
    # for this reason again.
    from vektorshot.vision import FIX_PROMPT, HTML_PROMPT

    for prompt in (HTML_PROMPT, FIX_PROMPT):
        assert "system fonts only" in prompt
        assert "Google Fonts" in prompt
        assert "no external font links" in prompt
