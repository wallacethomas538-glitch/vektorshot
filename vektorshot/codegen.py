"""HTML + Tailwind code generation for VektorShot Phase 1.

Stdlib only. Takes a LayoutDescription and writes one self-contained
HTML page in the VektorFlow design system (dark theme, cyan accent).

Safety rules, enforced here:
- All text from the layout is HTML-escaped.
- Images are never hotlinked: an image element becomes a styled local
  placeholder that names the asset file to supply. No external URL is
  ever written into generated code except the Tailwind CDN (allowlisted
  in verify.py).
- Any text that looks like a secret (API key, token, bearer value)
  refuses to generate: generated code must never embed credentials.
"""

from __future__ import annotations

import html
import re

from .models import BRAND, GeneratedPage, LayoutDescription

__all__ = ["generate_page", "SECRET_PATTERNS"]

# Patterns that must never appear in generated code. The same list is
# used by verify.py; keep them in sync.
SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{8,}"),
    re.compile(r"sk-proj-[A-Za-z0-9_-]{8,}"),
    re.compile(r"AIza[0-9A-Za-z_-]{10,}"),
    re.compile(r"ck_[A-Za-z0-9]{8,}"),
    re.compile(r"ghp_[A-Za-z0-9]{10,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{8,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/-]{10,}"),
)

TAILWIND_CDN = "https://cdn.tailwindcss.com"


def _check_no_secrets(text, where):
    for pattern in SECRET_PATTERNS:
        if pattern.search(text or ""):
            raise ValueError(
                f"refusing to generate: text for {where} looks like a "
                "secret (API key / token). Secrets live in environment "
                "variables, never in generated code.")


def _esc(text):
    return html.escape(text or "", quote=True)


def _render_element(element):
    """One layout element -> one HTML fragment."""
    _check_no_secrets(element.text, f"element {element.kind!r}")
    text = _esc(element.text)
    if element.kind == "heading":
        return (f'<h1 class="text-4xl md:text-5xl font-bold tracking-tight '
                f'text-[{BRAND["text"]}]">{text}</h1>')
    if element.kind == "text":
        return (f'<p class="text-lg text-[{BRAND["muted"]}]">{text}</p>')
    if element.kind == "button":
        return (f'<a href="#" class="inline-block rounded-lg px-6 py-3 '
                f'font-semibold text-[#0B1220] bg-[{BRAND["accent"]}] '
                f'hover:bg-[{BRAND["accent2"]}]">{text}</a>')
    if element.kind == "nav":
        links = " ".join(
            f'<a href="#" class="hover:text-[{BRAND["accent"]}]">{_esc(w)}</a>'
            for w in (element.text or "Home").split())
        return (f'<nav class="flex items-center gap-6 text-sm '
                f'text-[{BRAND["muted"]}]">{links}</nav>')
    if element.kind == "image":
        # Local placeholder only. Never an external URL: the real asset
        # is supplied as a local file at build time.
        label = text or "image asset"
        return (f'<div class="flex items-center justify-center rounded-xl '
                f'border border-dashed border-[{BRAND["accent"]}] '
                f'bg-[{BRAND["surface"]}] px-4 py-10 text-sm '
                f'text-[{BRAND["muted"]}]" data-asset="{label}">'
                f'[ image: {label} — supply as a local file ]</div>')
    if element.kind == "input":
        return (f'<input type="text" placeholder="{text}" '
                f'class="w-full rounded-lg border border-slate-700 '
                f'bg-[{BRAND["surface"]}] px-4 py-3 '
                f'text-[{BRAND["text"]}] placeholder:text-[{BRAND["muted"]}]" />')
    if element.kind == "card":
        return (f'<section class="rounded-xl border border-slate-800 '
                f'bg-[{BRAND["surface"]}] p-6">'
                f'<p class="text-[{BRAND["text"]}]">{text}</p></section>')
    if element.kind == "footer":
        return (f'<p class="text-sm text-[{BRAND["muted"]}]">{text}</p>')
    return f'<p class="text-[{BRAND["muted"]}]">{text}</p>'


def generate_page(layout, title=None, model="stub"):
    """Render a LayoutDescription as a complete HTML page.

    Returns a GeneratedPage with cost_usd 0.0: Phase 1 generation is
    local and free. Raises ValueError on secret-looking text.
    """
    if not isinstance(layout, LayoutDescription):
        raise ValueError("layout must be a LayoutDescription")
    page_title = title or layout.page_title or "Untitled page"
    _check_no_secrets(page_title, "page title")

    header = "".join(
        _render_element(e) for e in layout.elements if e.kind == "nav")
    hero = "".join(
        _render_element(e) for e in layout.elements
        if e.kind in ("heading", "text", "button"))
    cards = "".join(
        _render_element(e) for e in layout.elements if e.kind == "card")
    rest = "".join(
        _render_element(e) for e in layout.elements
        if e.kind in ("image", "input"))
    footer = "".join(
        _render_element(e) for e in layout.elements if e.kind == "footer")

    body_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{_esc(page_title)}</title>
<script src="{TAILWIND_CDN}"></script>
<style>body {{ background: {BRAND["bg"]}; }}</style>
</head>
<body class="min-h-screen text-[{BRAND["text"]}] antialiased">
<header class="mx-auto flex max-w-5xl items-center justify-between px-6 py-5">
<span class="text-xl font-bold"><span class="text-[{BRAND["accent"]}]">V</span> VektorFlow</span>
{header}
</header>
<main class="mx-auto max-w-5xl px-6 py-10">
<div class="space-y-5">{hero}</div>
<div class="mt-10 grid gap-6 md:grid-cols-2">{cards}</div>
<div class="mt-10 space-y-6">{rest}</div>
</main>
<footer class="mx-auto max-w-5xl px-6 py-8 border-t border-slate-800">{footer}</footer>
</body>
</html>
"""
    return GeneratedPage(html=body_html, title=page_title,
                         cost_usd=0.0, model=model, rounds=0)
