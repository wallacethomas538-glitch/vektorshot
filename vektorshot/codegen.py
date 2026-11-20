"""HTML + Tailwind code generation for VektorShot.

Phase 1 (template path): a LayoutDescription becomes one self-contained
HTML page in the VektorFlow design system (dark theme, cyan accent).

Phase 2 (direct path): the vision model writes the HTML itself and
``generate_page_direct`` puts it through the same safety gates —
secret scan, no ``javascript:`` links, no inline event handlers, no
non-allowlisted external URLs (Tailwind CDN only), no inline
``<script>`` blocks (only the exact Tailwind CDN script tag is
allowed), and validated resource URLs in ``src``, ``href``,
``action``, ``formaction``, and ``srcset``. The template path is
unchanged; the direct path is what makes a rebuild look like the
original instead of a generic sketch.

Safety rules, enforced here:
- All text from the layout is HTML-escaped.
- Images are never hotlinked: an image element becomes a styled local
  placeholder that names the asset file to supply. No external URL is
  ever written into generated code except the Tailwind CDN (allowlisted
  in verify.py).
- Any text that looks like a secret (API key, token, bearer value)
  refuses to generate: generated code must never embed credentials.
- Model-written HTML is untrusted input: anything that fails a gate
  is refused with a named reason — never silently cleaned up.
"""

from __future__ import annotations

import html
import re

from .models import BRAND, GeneratedPage, LayoutDescription

__all__ = ["generate_page", "generate_page_direct", "extract_html",
           "scan_direct_violations", "SECRET_PATTERNS"]

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


# --- Phase 2: model-driven generation --------------------------------

# The direct path mirrors these checks from verify.py (which imports
# scan_direct_violations from here, so the two gates stay in sync by
# construction). A model-written page is untrusted input: it goes
# through the same gates the template path enforces, and anything
# that fails is refused — never silently cleaned up.
_DIRECT_EVENT_ATTR = re.compile(r'''\son\w+\s*=''', re.IGNORECASE)
_DIRECT_TITLE = re.compile(r"<title[^>]*>.*?</title>", re.IGNORECASE | re.DOTALL)

# Script tags: only the exact Tailwind CDN script the codegen itself
# injects is authorized. Any other <script> — inline code, another
# src, code inside the tag, or a missing close tag — is a refusal.
# The patterns are case-insensitive and cover whitespace tricks
# (<ScRiPt>, <script\tsrc=...>) and unquoted attribute values.
_SCRIPT_OPEN = re.compile(r"<script\b[^>]*>", re.IGNORECASE)
_SCRIPT_CLOSE = re.compile(r"</script\s*>", re.IGNORECASE)
_SCRIPT_SRC = re.compile(
    r"""src\s*=\s*(?:"(?P<dq>[^"]*)"|'(?P<sq>[^']*)'|(?P<bare>[^\s>]+))""",
    re.IGNORECASE)
# Resource URLs: src, href, action, formaction (quoted or unquoted)
# plus srcset (quoted; comma-separated "url [descriptor]" candidates).
_RESOURCE_URL_ATTRS = re.compile(
    r"""(?P<attr>src|href|action|formaction)\s*=\s*"""
    r"""(?:"(?P<dq>[^"]*)"|'(?P<sq>[^']*)'|(?P<bare>[^\s>]+))""",
    re.IGNORECASE)
_SRCSET_ATTR = re.compile(
    r"""srcset\s*=\s*(?:"(?P<dq>[^"]*)"|'(?P<sq>[^']*)')""",
    re.IGNORECASE)


def _attr_value(match):
    """The attribute value from a quoted-or-unquoted regex match.

    All attribute regexes below use the same named groups (dq / sq /
    bare), so this works for script src, resource URLs, and srcset.
    """
    for group in ("dq", "sq", "bare"):
        value = match.group(group)
        if value is not None:
            return value
    return ""


def _check_resource_url(attr, url, violations):
    """One resource URL against the gates. Appends (code, message)."""
    url = (url or "").strip()
    lowered = url.lower()
    if lowered.startswith(("javascript:", "vbscript:")):
        if attr == "href":
            violations.append(("javascript-href",
                               "javascript: link found in generated page"))
        else:
            violations.append(("unsafe-url-scheme",
                               f"unsafe URL scheme in {attr} attribute: "
                               f"{url}"))
        return
    if lowered.startswith("data:"):
        violations.append(("unsafe-url-scheme",
                           f"unsafe URL scheme in {attr} attribute: {url}"))
        return
    if url.startswith(("http://", "https://", "//")):
        base = url.split("?", 1)[0].rstrip("/")
        if base not in (TAILWIND_CDN,) and url != TAILWIND_CDN:
            violations.append(("external-asset",
                               "external URL is not allowlisted: "
                               f"{url} — assets must be local files, "
                               "never hotlinks"))


def scan_direct_violations(html_doc: str) -> list:
    """Static safety scan shared by generate_page_direct and check_html.

    Returns a list of (code, message) for every violation found; an
    empty list means the HTML passed the static gates. Covers inline
    <script> blocks (only the exact Tailwind CDN script tag is
    allowed), unsafe URL schemes (javascript:, vbscript:, data:), and
    non-allowlisted external URLs in src, href, action, formaction,
    and srcset. The scan never cleans anything: callers refuse on any
    violation, with the named reason.
    """
    violations = []
    text = html_doc or ""
    # --- <script> tags ---
    for open_match in _SCRIPT_OPEN.finditer(text):
        tag = open_match.group(0)
        src_match = _SCRIPT_SRC.search(tag)
        src = _attr_value(src_match) if src_match else None
        if src is None:
            violations.append(("inline-script",
                               "inline <script> block found — generated "
                               "pages must not run inline scripts"))
            continue
        if src != TAILWIND_CDN:
            violations.append(("unauthorized-script-src",
                               "script source is not allowlisted: "
                               f"{src} — only the Tailwind CDN script "
                               "is allowed"))
            continue
        # Authorized src: the tag must be empty and closed. Code
        # inside it, or a missing close tag, is still a refusal —
        # an unclosed <script> would swallow the rest of the page.
        close_match = _SCRIPT_CLOSE.search(text, open_match.end())
        if close_match is None:
            violations.append(("inline-script",
                               "unclosed <script> tag found — generated "
                               "pages must not run inline scripts"))
            continue
        if text[open_match.end():close_match.start()].strip():
            violations.append(("inline-script",
                               "inline code inside <script> tag found — "
                               "generated pages must not run inline "
                               "scripts"))
    # --- resource URLs ---
    for match in _RESOURCE_URL_ATTRS.finditer(text):
        _check_resource_url(match.group("attr").lower(),
                            _attr_value(match), violations)
    for match in _SRCSET_ATTR.finditer(text):
        for candidate in _attr_value(match).split(","):
            parts = candidate.strip().split()
            if parts:
                _check_resource_url("srcset", parts[0], violations)
    return violations


def _check_direct_html(html_doc: str) -> None:
    """Safety gates for model-written HTML. Raises ValueError on violation."""
    _check_no_secrets(html_doc, "model-written page")
    for _code, message in scan_direct_violations(html_doc):
        raise ValueError(f"refusing model-written page: {message}")
    if _DIRECT_EVENT_ATTR.search(html_doc):
        raise ValueError(
            "refusing model-written page: inline event handler "
            "(onclick etc.) found — generated pages must not run "
            "inline scripts")


def extract_html(model_reply: str) -> str:
    """Pull the HTML document out of a model's raw reply.

    Strips markdown fences and surrounding prose, keeps the slice from
    the first ``<!DOCTYPE html>`` (or ``<html``) to the last
    ``</html>``. A missing doctype is added; a reply with no ``<html``
    tag at all raises ValueError — there is nothing to build from.
    """
    if not isinstance(model_reply, str) or not model_reply.strip():
        raise ValueError("model reply is empty: no HTML to extract")
    text = model_reply
    lines = [line for line in text.splitlines()
             if not line.strip().startswith("```")]
    text = "\n".join(lines)
    lowered = text.lower()
    start = lowered.find("<!doctype html")
    if start < 0:
        start = lowered.find("<html")
    if start < 0:
        raise ValueError(
            "model reply contained no HTML document "
            "(no <html> tag found) — re-prompt the model, do not guess "
            "a page.")
    end = lowered.rfind("</html>")
    if end < 0:
        raise ValueError(
            "model reply has an opening <html> tag but no closing "
            "</html> — the reply looks truncated; re-prompt the model.")
    html_doc = text[start:end + len("</html>")].strip()
    if not html_doc.lower().startswith("<!doctype html"):
        html_doc = "<!DOCTYPE html>\n" + html_doc
    return html_doc


def generate_page_direct(model_reply: str, title: str | None = None,
                         model: str = "gemini-4-hydrogen") -> GeneratedPage:
    """Build a page from the model's own HTML reply.

    Extracts the document, runs the safety gates (secret scan, no
    inline <script> blocks, only the Tailwind CDN script source, no
    ``javascript:`` links, no inline handlers, no non-allowlisted
    external URLs in src/href/action/formaction/srcset), injects the
    Tailwind CDN script and a ``<title>`` when the model left them
    out, then runs the gates again on the final output so only the
    exact injected Tailwind tag survives. Returns a GeneratedPage.
    The result is still untrusted until ``check_html`` passes AND a
    live render proves it — this function only proves the gates passed.
    """
    html_doc = extract_html(model_reply)
    _check_direct_html(html_doc)
    if TAILWIND_CDN not in html_doc:
        script = f'<script src="{TAILWIND_CDN}"></script>'
        lowered = html_doc.lower()
        head_end = lowered.find("</head>")
        if head_end >= 0:
            html_doc = (html_doc[:head_end] + script + "\n"
                        + html_doc[head_end:])
        else:
            html_doc = script + "\n" + html_doc
    page_title = title or "VektorShot page"
    if not _DIRECT_TITLE.search(html_doc):
        title_tag = f"<title>{_esc(page_title)}</title>"
        lowered = html_doc.lower()
        head_start = lowered.find("<head")
        if head_start >= 0:
            head_close = html_doc.find(">", head_start)
            html_doc = (html_doc[:head_close + 1] + "\n" + title_tag
                        + html_doc[head_close + 1:])
        else:
            html_doc = title_tag + "\n" + html_doc
    else:
        match = _DIRECT_TITLE.search(html_doc)
        inner = re.sub(r"<[^>]+>", "", match.group(0)).strip()
        if inner:
            page_title = inner
    # Final-output check: the gates run again after injection so the
    # delivered page holds only the exact injected Tailwind tag.
    _check_direct_html(html_doc)
    return GeneratedPage(html=html_doc, title=page_title,
                         cost_usd=0.0, model=model, rounds=0)
