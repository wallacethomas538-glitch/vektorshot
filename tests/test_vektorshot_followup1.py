"""VektorShot follow-up 1 tests — Big Chat CHANGES REQUESTED review.

Fix 1 (HTML security gate): inline <script> blocks and non-allowlisted
resource URLs must be refused by BOTH generate_page_direct() and
check_html(). Fix 2 (free-tier provider fallback): a reachable-but-
unwired Ollama must never be selected — selection falls through to
Gemini, and all-failures raise an honest error naming every provider
tried. No live model calls, no keys, no network: every transport is
mocked at urllib.request.urlopen. PNG fixtures are built in-test with
struct+zlib (stdlib only).
"""

import json
import struct
import urllib.error
import zlib

import pytest

from vektorshot import check_html, generate_page_direct
from vektorshot.vision import (
    GeminiVisionProvider,
    GroqVisionProvider,
    OllamaVisionProvider,
    StubVisionProvider,
    VisionError,
    analyze_with_fallback,
    select_provider,
)

FIXTURE_KEY = "test-key-not-real-12345"

LAYOUT_REPLY = """TITLE: Test Page
nav | Home About Contact | 0,0,1000,60
heading | Hello World | 80,120,840,70
text | Build anything from a screenshot. | 80,210,600,40
button | Get started | 80,280,160,48
"""

BASE = ("<!DOCTYPE html><html><head><title>t</title></head>"
        "<body>{body}</body></html>")


def make_png(width=64, height=48, rgb=(11, 18, 32)):
    """A minimal valid PNG, built with stdlib only."""
    def chunk(kind, data):
        out = struct.pack(">I", len(data)) + kind + data
        return out + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    raw = b"".join(b"\x00" + bytes(rgb) * width for _ in range(height))
    return sig + ihdr + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


class FakeHttpResponse:
    """Stand-in for a urllib response: status + canned JSON payload."""

    def __init__(self, payload=None, status=200):
        self.status = status
        self._payload = (json.dumps(payload).encode("utf-8")
                         if payload is not None else b"{}")

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def dispatch_fake(tags=None, gemini_payload=None, gemini_error=None):
    """urlopen fake: Ollama /api/tags answers `tags`, Gemini answers
    `gemini_payload` or raises `gemini_error`. Anything else is a
    test bug, not a network call."""
    calls = []

    def fake_urlopen(request, timeout=None):
        url = getattr(request, "full_url", str(request))
        calls.append(url)
        if "api/tags" in url:
            if isinstance(tags, Exception):
                raise tags
            return FakeHttpResponse(status=tags if tags is not None else 200)
        if "generativelanguage.googleapis.com" in url:
            if gemini_error is not None:
                raise gemini_error
            return FakeHttpResponse(payload=gemini_payload)
        raise AssertionError(f"unexpected network call: {url}")

    fake_urlopen.calls = calls
    return fake_urlopen


def gemini_payload_for(reply):
    return {"candidates": [{"content": {"parts": [{"text": reply}]}}]}


def assert_refused(body, match, codes):
    """Both gates must refuse the same unsafe HTML."""
    html = BASE.format(body=body)
    with pytest.raises(ValueError, match=match):
        generate_page_direct(html)
    report = check_html(html)
    assert not report.passed
    found = {issue.code for issue in report.issues}
    assert codes & found, f"expected one of {codes}, got {found}"


# --- Fix 1: inline <script> blocks ---------------------------------------

def test_inline_script_pasted_snippet_refused():
    # The exact snippet from Big Chat's review: it passed both gates
    # before this follow-up (proven Nov 19).
    assert_refused("<script>/* arbitrary JavaScript */</script>",
                   "inline.*script", {"inline-script"})


def test_script_with_attributes_refused():
    assert_refused('<script type="text/javascript">alert(1)</script>',
                   "inline.*script", {"inline-script"})


def test_mixed_case_script_refused():
    assert_refused("<ScRiPt>alert(1)</ScRiPt>",
                   "inline.*script", {"inline-script"})


def test_script_code_inside_tailwind_tag_refused():
    assert_refused('<script src="https://cdn.tailwindcss.com">evil()'
                   "</script>", "inline.*script", {"inline-script"})


def test_unclosed_script_refused():
    assert_refused('<script src="https://cdn.tailwindcss.com">',
                   "script", {"inline-script"})


def test_script_external_src_refused():
    assert_refused('<script src="https://evil.example/x.js"></script>',
                   "not allowlisted", {"unauthorized-script-src"})


def test_script_src_tailwind_query_refused():
    # Only the exact Tailwind CDN URL is authorized — a query string
    # makes it a different source.
    assert_refused('<script src="https://cdn.tailwindcss.com?x=1">'
                   "</script>", "not allowlisted",
                   {"unauthorized-script-src"})


def test_tailwind_script_tag_allowed():
    html = BASE.format(
        body='<script src="https://cdn.tailwindcss.com"></script>')
    page = generate_page_direct(html)
    assert "cdn.tailwindcss.com" in page.html
    assert check_html(page.html).passed


# --- Fix 1: resource URLs (src/href/action/formaction/srcset) -------------

def test_resource_urls_validated():
    cases = [
        ('<form action="https://evil.example/submit">'
         '<input type="text"></form>', "not allowlisted",
         {"external-asset"}),
        ('<button formaction="https://evil.example/go">x</button>',
         "not allowlisted", {"external-asset"}),
        ('<img srcset="https://evil.example/a.png 1x, local.png 2x">',
         "not allowlisted", {"external-asset"}),
        ('<form action="javascript:alert(1)">x</form>',
         "unsafe URL scheme", {"unsafe-url-scheme"}),
        ('<iframe src="data:text/html;base64,SGVsbG8="></iframe>',
         "unsafe URL scheme", {"unsafe-url-scheme"}),
        ('<a href=javascript:alert(1)>x</a>',
         "javascript", {"javascript-href"}),
    ]
    for body, match, codes in cases:
        assert_refused(body, match, codes)


def test_local_resource_urls_allowed():
    html = BASE.format(body=(
        '<img src="local.png" srcset="local.png 1x, local-2x.png 2x">'
        '<a href="page.html">x</a>'
        '<form action="/submit"><input type="text"></form>'
        '<button formaction="/go">x</button>'))
    page = generate_page_direct(html)
    assert check_html(page.html).passed


# --- Fix 2: Ollama probe separates server-up from vision capability ------

def test_ollama_probe_server_up_but_unwired(monkeypatch):
    monkeypatch.setattr("vektorshot.vision.urllib.request.urlopen",
                        dispatch_fake(tags=200))
    probe = OllamaVisionProvider().probe()
    assert probe.reachable is False
    assert "server is up" in probe.reason
    assert "not wired" in probe.reason


def test_ollama_probe_server_down(monkeypatch):
    monkeypatch.setattr(
        "vektorshot.vision.urllib.request.urlopen",
        dispatch_fake(tags=urllib.error.URLError("refused")))
    probe = OllamaVisionProvider().probe()
    assert probe.reachable is False
    assert "not reachable" in probe.reason


# --- Fix 2: selection falls through to Gemini -----------------------------

def test_select_provider_skips_unwired_ollama_for_gemini(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", FIXTURE_KEY)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setattr(
        "vektorshot.vision.urllib.request.urlopen",
        dispatch_fake(tags=200,
                      gemini_payload=gemini_payload_for(LAYOUT_REPLY)))
    provider = select_provider()
    assert isinstance(provider, GeminiVisionProvider)
    layout = provider.analyze_screenshot(make_png())
    assert layout.page_title == "Test Page"
    assert len(layout.elements) == 4


def test_analyze_with_fallback_falls_through_to_gemini(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", FIXTURE_KEY)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setattr(
        "vektorshot.vision.urllib.request.urlopen",
        dispatch_fake(tags=200,
                      gemini_payload=gemini_payload_for(LAYOUT_REPLY)))
    name, layout = analyze_with_fallback(make_png())
    assert name == "gemini"
    assert layout.page_title == "Test Page"
    assert len(layout.elements) == 4


def test_groq_never_selected(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", FIXTURE_KEY)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(
        "vektorshot.vision.urllib.request.urlopen",
        dispatch_fake(tags=urllib.error.URLError("refused")))
    provider = select_provider()
    assert isinstance(provider, StubVisionProvider)
    assert not isinstance(provider, GroqVisionProvider)


def test_select_provider_stub_when_nothing_usable(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setattr(
        "vektorshot.vision.urllib.request.urlopen",
        dispatch_fake(tags=urllib.error.URLError("refused")))
    assert isinstance(select_provider(), StubVisionProvider)


# --- Fix 2: all-fail is an honest error, never a result --------------------

def test_analyze_with_fallback_all_fail_honest_error(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", FIXTURE_KEY)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    error = urllib.error.HTTPError(
        "https://generativelanguage.googleapis.com/x", 503,
        "Service Unavailable", {}, None)
    monkeypatch.setattr(
        "vektorshot.vision.urllib.request.urlopen",
        dispatch_fake(tags=urllib.error.URLError("refused"),
                      gemini_error=error))
    with pytest.raises(VisionError) as excinfo:
        analyze_with_fallback(make_png())
    message = str(excinfo.value)
    assert "gemini" in message
    assert "503" in message
    assert "ollama" in message
    assert "groq" in message
    assert "No live vision ran" in message


def test_analyze_with_fallback_no_keys_honest_error(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setattr("vektorshot.vision.urllib.request.urlopen",
                        dispatch_fake(tags=200))
    with pytest.raises(VisionError) as excinfo:
        analyze_with_fallback(make_png())
    message = str(excinfo.value)
    assert "ollama" in message and "not wired" in message
    assert "GEMINI_API_KEY" in message
    assert "groq" in message
    assert "No live vision ran" in message
