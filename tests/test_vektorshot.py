"""VektorShot Phase 1 tests — 20 tests, stdlib pytest only.

PNG fixtures are built in-test with struct+zlib (no real photos, no
network, no keys). Live model calls are never made: the stub provider
stands in for vision, and the Playwright render path is exercised
only as a command builder.
"""

import struct
import sys
import zlib
from pathlib import Path

import pytest

from vektorshot import (
    CostLedger,
    GeminiVisionProvider,
    LayoutDescription,
    LayoutElement,
    SelfCheckLoop,
    StubVisionProvider,
    VisionConfigError,
    build_screenshot_command,
    check_html,
    generate_page,
)

VEKTORSHOT_ROOT = Path(__file__).resolve().parents[1]

# Fixture tokens: look like real secrets, are not. Used only to prove
# generated code never embeds credentials.
FIXTURE_TOKENS = (
    "sk-testtoken-abcdef12345678",
    "AIzaTestToken0123456789abcdef",
    "ck_testtoken1234567890abcdef",
    "ghp_testtoken1234567890abcd",
)


def make_png(width=64, height=48, rgb=(11, 18, 32)):
    """A minimal valid PNG, built with stdlib only."""
    def chunk(kind, data):
        out = struct.pack(">I", len(data)) + kind + data
        return out + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    raw = b"".join(b"\x00" + bytes(rgb) * width for _ in range(height))
    return sig + ihdr + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def stub_layout():
    return StubVisionProvider().analyze_screenshot(make_png())


# --- Vision (4) -------------------------------------------------------

def test_stub_returns_layout():
    layout = stub_layout()
    assert isinstance(layout, LayoutDescription)
    assert layout.width == 64 and layout.height == 48
    assert layout.page_title
    assert layout.elements
    assert layout.palette["bg"] == "#0B1220"
    assert layout.palette["accent"] == "#22D3EE"


def test_stub_deterministic():
    png = make_png()
    first = StubVisionProvider().analyze_screenshot(png)
    second = StubVisionProvider().analyze_screenshot(png)
    assert first == second


def test_stub_rejects_empty_bytes():
    with pytest.raises(ValueError, match="empty"):
        StubVisionProvider().analyze_screenshot(b"")


def test_env_provider_missing_key_names_var(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(VisionConfigError, match="GEMINI_API_KEY"):
        GeminiVisionProvider().analyze_screenshot(make_png())


# --- Models (2) -------------------------------------------------------

def test_layout_defaults():
    layout = LayoutDescription()
    assert layout.page_title == "Untitled page"
    assert layout.elements == []
    assert layout.palette["accent"] == "#22D3EE"
    assert layout.headings() == []
    assert layout.buttons() == []


def test_ledger_totals_zero_for_free():
    ledger = CostLedger()
    ledger.record_free("stub")
    ledger.record_free("stub")
    assert len(ledger.entries) == 2
    assert ledger.total_usd == 0.0


# --- Codegen (6) ------------------------------------------------------

def test_generated_page_is_full_document():
    html = generate_page(stub_layout()).html
    lowered = html.lower()
    assert lowered.startswith("<!doctype html>")
    for tag in ("<html", "<head", "<body", "<title"):
        assert tag in lowered
    assert "</html>" in lowered


def test_tailwind_cdn_present():
    html = generate_page(stub_layout()).html
    assert "https://cdn.tailwindcss.com" in html


def test_brand_colors_present():
    html = generate_page(stub_layout()).html
    assert "#0B1220" in html  # dark background
    assert "#22D3EE" in html  # cyan accent


def test_elements_rendered():
    html = generate_page(stub_layout()).html
    assert "Welcome to VektorFlow" in html
    assert "Get started" in html


def test_text_is_escaped():
    layout = LayoutDescription(elements=[
        LayoutElement(kind="heading", text="<script>alert(1)</script>")])
    html = generate_page(layout).html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<script>alert(1)</script>" not in html


def test_secret_text_refuses_to_generate():
    layout = LayoutDescription(elements=[
        LayoutElement(kind="button", text="Use sk-testtoken-abcdef12345678")])
    with pytest.raises(ValueError, match="secret"):
        generate_page(layout)


# --- Self-check (4) ---------------------------------------------------

def test_screenshot_command_shape(tmp_path):
    target = tmp_path / "page.html"
    target.write_text("<html></html>", encoding="utf-8")
    out = tmp_path / "render.png"
    command = build_screenshot_command(str(target), str(out))
    assert "playwright" in command
    assert "screenshot" in command
    assert str(target) in command
    assert str(out) in command
    assert "--viewport-size=1280,800" in command


def test_loop_accepts_above_threshold():
    loop = SelfCheckLoop(max_rounds=3, accept_threshold=0.85)
    assert loop.decide(0.9, 1) == "accept"
    assert loop.record(1, 0.9).verdict == "accept"


def test_loop_requests_fix_below_threshold():
    loop = SelfCheckLoop(max_rounds=3, accept_threshold=0.85)
    assert loop.decide(0.5, 1) == "fix"
    assert loop.decide(0.5, 2) == "fix"


def test_loop_gives_up_at_max_rounds():
    loop = SelfCheckLoop(max_rounds=3, accept_threshold=0.85)
    result = loop.record(3, 0.5, issues=["heading misaligned"])
    assert result.verdict == "give_up"
    assert "gave up" in loop.summarize([result]).lower()


# --- Verify (3) -------------------------------------------------------

def test_clean_page_passes():
    report = check_html(generate_page(stub_layout()).html)
    assert report.passed
    assert report.issues == []
    # Static checks alone never claim a page renders fine.
    assert report.requires_live_render is True


def test_external_asset_flagged():
    html = ("<!DOCTYPE html><html><head><title>t</title></head><body>"
            '<img src="https://evil.example/x.png"></body></html>')
    report = check_html(html)
    assert not report.passed
    assert any(i.code == "external-asset" for i in report.issues)


def test_secret_in_html_flagged():
    html = ("<!DOCTYPE html><html><head><title>t</title></head><body>"
            "<p>key sk-testtoken-abcdef12345678</p></body></html>")
    report = check_html(html)
    assert not report.passed
    assert any(i.code == "possible-secret" for i in report.issues)


# --- Skill loads in VektorCode's loader (1) ---------------------------

def test_skill_loads_in_vektorcode_loader():
    candidates = sorted(Path.home().glob(
        "workspace/vektorkode-*/vektor_cloud/skills.py"))
    assert candidates, "no VektorCode skills.py found to check against"
    loader_dir = candidates[0].parent.parent
    sys.path.insert(0, str(loader_dir))
    from vektor_cloud import skills as loader

    found = [s for s in loader.discover_skills(repo_root=str(VEKTORSHOT_ROOT))
             if s["slug"] == "vektorshot"]
    assert found, "skills/vektorshot was not discovered by the loader"
    loaded = loader.load_skill(repo_root=str(VEKTORSHOT_ROOT),
                               slug="vektorshot")
    assert loaded is not None
    assert loaded["name"] == "vektorshot"
    assert "VektorShot" in loaded["body"]
    assert len(loaded["body"]) <= loader.SKILL_BODY_CAP
