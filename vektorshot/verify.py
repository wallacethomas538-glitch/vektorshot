"""Static verification for generated pages.

Checks what can be checked without a browser: document structure,
<script> tags, inline event handlers, external asset URLs (src, href,
action, formaction, srcset), CSS url(), meta-refresh URLs, and
secrets. Console errors and real rendering can only be proven by a
live browser run, so every report says so:
``requires_live_render`` is always True until a render proves otherwise.
"""

from __future__ import annotations

import re

from .codegen import SECRET_PATTERNS, TAILWIND_CDN, scan_direct_violations
from .models import VerificationIssue, VerificationReport

__all__ = [
    "EXTERNAL_ALLOWLIST",
    "scan_for_tokens",
    "check_html",
]

# The only external URL a generated page may reference. Everything else
# (images, fonts, scripts) must be a local file, never a hotlink.
EXTERNAL_ALLOWLIST = {TAILWIND_CDN}


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

    # Script tags, event handlers, resource URLs, CSS url(), and
    # meta-refresh URLs: the same scan generate_page_direct refuses
    # on, so both gates reject the same unsafe HTML.
    for code, message in scan_direct_violations(html):
        issues.append(VerificationIssue(code=code, message=message))

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
