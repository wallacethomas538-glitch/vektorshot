"""Static verification for generated pages.

Checks what can be checked without a browser: document structure,
external asset URLs, and secrets. Console errors and real rendering
can only be proven by a live browser run, so every report says so:
``requires_live_render`` is always True until a render proves otherwise.
"""

from __future__ import annotations

import re

from .codegen import SECRET_PATTERNS, TAILWIND_CDN
from .models import VerificationIssue, VerificationReport

__all__ = [
    "EXTERNAL_ALLOWLIST",
    "scan_for_tokens",
    "check_html",
]

# The only external URL a generated page may reference. Everything else
# (images, fonts, scripts) must be a local file, never a hotlink.
EXTERNAL_ALLOWLIST = {TAILWIND_CDN}

_URL_ATTRS = re.compile(
    r'''(?:src|href)\s*=\s*["']([^"']+)["']''', re.IGNORECASE)
_JS_HREF = re.compile(r'''href\s*=\s*["']\s*javascript:''', re.IGNORECASE)
_EVENT_ATTR = re.compile(r'''\son\w+\s*=''', re.IGNORECASE)


def scan_for_tokens(text, tokens):
    """Return the fixture tokens found in text (empty list = clean)."""
    return [t for t in tokens if t and t in (text or "")]


def check_html(html):
    """Static checks on a generated page. Returns a VerificationReport."""
    issues = []
    if not isinstance(html, str) or not html.strip():
        return VerificationReport(
            passed=False,
            issues=[VerificationIssue(
                code="empty",
                message="generated page is empty")])

    lowered = html.lower()
    for tag, code in (("<!doctype html", "no-doctype"),
                      ("<html", "no-html-tag"),
                      ("<head", "no-head-tag"),
                      ("<body", "no-body-tag"),
                      ("<title", "no-title-tag")):
        if tag not in lowered:
            issues.append(VerificationIssue(
                code=code,
                message=f"generated page is missing {tag}"))

    for url in _URL_ATTRS.findall(html):
        if url.startswith(("http://", "https://", "//")):
            base = url.split("?", 1)[0].rstrip("/")
            if base not in EXTERNAL_ALLOWLIST and url not in EXTERNAL_ALLOWLIST:
                issues.append(VerificationIssue(
                    code="external-asset",
                    message=f"external URL is not allowlisted: {url} — "
                            "assets must be local files, never hotlinks"))

    if _JS_HREF.search(html):
        issues.append(VerificationIssue(
            code="javascript-href",
            message="javascript: link found in generated page"))

    if _EVENT_ATTR.search(html):
        issues.append(VerificationIssue(
            code="inline-handler",
            message="inline event handler (onclick etc.) found — "
                    "generated pages must not run inline scripts"))

    for pattern in SECRET_PATTERNS:
        match = pattern.search(html)
        if match:
            issues.append(VerificationIssue(
                code="possible-secret",
                message="text that looks like a secret (API key / token) "
                        "found in generated page — secrets live in "
                        "environment variables, never in generated code"))
            break

    return VerificationReport(
        passed=not issues,
        issues=issues,
        requires_live_render=True)
