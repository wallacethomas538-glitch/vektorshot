"""VektorShot follow-up 3 tests — Big Chat CHANGES REQUESTED review
of follow-up 2.

Follow-up 2 did not decode CSS escape sequences and did not inspect
CSS @import statements, so a model-written page could smuggle a
dangerous or external URL past both gates with "url(\\6a
avascript:...)" or "@import url(https://evil.example/x.css)".
Every bypass below was verified ACCEPTED by both gates on the
follow-up-2 commit 34e572a (negative controls) before this fix.
Each test proves the same HTML is now refused by BOTH
generate_page_direct() and check_html(), with the same named
reason. No live model calls, no keys, no network.
"""

import pytest

from vektorshot import check_html, generate_page_direct

BASE = ("<!DOCTYPE html><html><head><title>t</title></head>"
        "<body>{body}</body></html>")


def assert_refused(body, match, codes):
    """Both gates must refuse the same unsafe HTML."""
    html = BASE.format(body=body)
    with pytest.raises(ValueError, match=match):
        generate_page_direct(html)
    report = check_html(html)
    assert not report.passed
    found = {issue.code for issue in report.issues}
    assert codes & found, f"expected one of {codes}, got {found}"


def assert_allowed(body):
    """Both gates must accept the same safe HTML."""
    html = BASE.format(body=body)
    page = generate_page_direct(html)
    assert check_html(page.html).passed


def style_block(css):
    return f"<style>{css}</style><div>x</div>"


# --- Fix 1: CSS escape sequences in url() --------------------------------

def test_css_escape_javascript_in_url_refused():
    # "\\6a" is the CSS escape for "j", so each of these is
    # javascript: by the time a browser tokenizes the CSS. Forms:
    # hex escape + whitespace terminator, hex escape with no
    # terminator (next char is not a hex digit), 6-digit hex,
    # several escapes spelling the scheme, and an escaped colon.
    cases = [
        "background:url(\\6a avascript:alert(1))",
        "background:url(\\6A avascript:alert(1))",
        "background:url(\\00006Aavascript:alert(1))",
        "background:url(\\6a\\61vascript:alert(1))",
        "background:url(java\\73 cript:alert(1))",
        "background:url(javascript\\3a alert(1))",
        'background:url("\\6a avascript:alert(1)")',
        "background:url(\\76 bscript:msgbox(1))",
    ]
    for style in cases:
        assert_refused(f'<div style="{style}">x</div>',
                       "unsafe URL scheme", {"unsafe-url-scheme"})


def test_css_escape_javascript_in_style_block_refused():
    assert_refused(
        style_block("div{background:url(\\6a avascript:alert(1))}"),
        "unsafe URL scheme", {"unsafe-url-scheme"})


def test_css_escape_line_continuation_refused():
    # Backslash + newline is a line continuation: both are dropped,
    # so the scheme is spelled out once the CSS is tokenized.
    assert_refused(
        '<div style="background:url(java\\\nscript:alert(1))">x</div>',
        "unsafe URL scheme", {"unsafe-url-scheme"})
    assert_refused(
        style_block("div{background:url(java\\\nscript:alert(1))}"),
        "unsafe URL scheme", {"unsafe-url-scheme"})


def test_css_escaped_url_function_name_refused():
    # Browsers decode escapes in identifiers too, so "u\\72l(" is
    # the url() function ("\\72" is "r", "\\75" is "u"). The
    # scanner must recognise the function name after decoding.
    cases = [
        "background:u\\72l(javascript:alert(1))",
        "background:\\75rl(javascript:alert(1))",
        "background:u\\72l(\\6a avascript:alert(1))",
    ]
    for style in cases:
        assert_refused(f'<div style="{style}">x</div>',
                       "unsafe URL scheme", {"unsafe-url-scheme"})


def test_css_escape_external_url_refused():
    # Escapes spelling an ordinary external URL must still hit the
    # allowlist, not just dangerous schemes.
    assert_refused(
        '<div style="background:url(\\68ttps://evil.example/bg.png)">'
        "x</div>", "not allowlisted", {"external-asset"})


# --- Fix 2: CSS @import ----------------------------------------------------

def test_css_import_dangerous_scheme_refused():
    cases = [
        "@import url(javascript:alert(1));",
        '@import url("javascript:alert(1)");',
        '@import "javascript:alert(1)";',
        "@import 'vbscript:msgbox(1)';",
        "@import url(data:text/css,body{});",
        "@import 'data:text/css,body{}';",
    ]
    for css in cases:
        assert_refused(style_block(css),
                       "unsafe URL scheme", {"unsafe-url-scheme"})


def test_css_import_external_refused():
    cases = [
        "@import url(https://evil.example/x.css);",
        '@import "https://evil.example/x.css";',
        "@import 'https://evil.example/x.css' layer;",
        "@import url(https://evil.example/x.css) layer;",
        "@import \"https://evil.example/x.css\" "
        "supports(display: grid) screen;",
        "@import url(//evil.example/x.css);",
    ]
    for css in cases:
        assert_refused(style_block(css),
                       "not allowlisted", {"external-asset"})


def test_css_import_escaped_bypass_refused():
    # Escaped scheme inside @import url(), escaped scheme inside an
    # @import string, an escape spelling an external URL, an
    # escape-encoded @import keyword, and a comment between the
    # keyword and its URL (comments are invisible to the CSS parser).
    cases = [
        "@import url(\\6a avascript:alert(1));",
        '@import "\\6a avascript:alert(1)";',
        "@import url(\\68ttps://evil.example/x.css);",
        "@\\69mport url(https://evil.example/x.css);",
        "@import/**/url(https://evil.example/x.css);",
        '@import /* comment */ "https://evil.example/x.css";',
        "@import url(\\6a avascript:alert(1)) layer;",
    ]
    for css in cases:
        assert_refused(style_block(css),
                       "unsafe URL scheme|not allowlisted",
                       {"unsafe-url-scheme", "external-asset"})


def test_css_import_in_style_attribute_refused():
    # @import is invalid inside a style attribute and inert to a
    # browser there, but the scanner checks every CSS segment the
    # same way — a dangerous import is refused wherever it appears.
    assert_refused(
        '<div style="@import url(javascript:alert(1))">x</div>',
        "unsafe URL scheme", {"unsafe-url-scheme"})


# --- Positive controls: safe CSS must still pass both gates ---------------

def test_css_import_local_allowed():
    # Local imports are permitted, matching the existing url()
    # policy: relative, root-relative, quoted, unquoted, with layer
    # / supports() / media queries after the URL.
    assert_allowed(style_block(
        '@import url(local.css);'
        '@import "local.css";'
        "@import 'themes/dark.css' layer;"
        "@import url(./fonts.css) screen;"
        '@import "/abs.css";'
        '@import url(local2.css) layer supports(display: grid);'))


def test_css_url_escape_decoding_to_local_allowed():
    # Escapes that decode to a SAFE local URL are allowed: the
    # normalizer decodes them, and the decoded value is local.
    assert_allowed(
        '<div style="background:url(\\69mages/bg.png)">x</div>'
        '<div style="background:url(\\62g.png)">y</div>'
        "<div style=\"background:url('ima\\67 e.png')\">z</div>")


# NOTE: the follow-up-2 whole-document url() backstop is kept, so a
# "url(...)" in visible text or in a non-style attribute is still
# refused (safe-direction false positive inherited from follow-up 2).
# Segment-scoped scanning alone would allow it, but the backstop
# exists for the malformed-attribute case above, and the two cannot
# be separated without weakening the follow-up-2 tests.


def test_css_double_escape_allowed():
    # Decoding happens exactly once, as in a browser: "\\5c" is a
    # backslash, so the value a browser sees is the literal text
    # "\\6a avascript:..." — a harmless relative URL, not a scheme.
    assert_allowed(
        '<div style="background:url(\\5c 6a avascript:alert(1))">x'
        "</div>")


def test_css_escape_hex_greedy_allowed():
    # A hex escape eats up to 6 hex digits greedily, so the letter
    # after it matters: "\\6Aavascript:" is NOT "j" + "avascript:"
    # — the "a" is a hex digit, so the escape is "\\6Aa" = U+06AA,
    # and the value is a harmless relative URL. Same for "\\76b".
    # (This is why the dangerous spellings need a whitespace
    # terminator, or an escape for the following letter.)
    assert_allowed(
        '<div style="background:url(\\6Aavascript:alert(1))">x</div>'
        '<div style="background:url(\\76bscript:msgbox(1))">y</div>')


# NOTE (pre-existing FU2 behaviour, not changed here): a value that
# decodes to "j avascript:..." (e.g. "\\6a" followed by TWO spaces)
# is still refused — _check_resource_url strips interior spaces
# before the scheme check, which joins it into "javascript:". That
# is safe-direction over-strictness from follow-up 2 (browsers treat
# the space as part of a relative URL), left untouched by FU3.


# (test_css_url_in_visible_text_allowed was removed: the
# follow-up-2 whole-document url() backstop refuses a "url(...)" in
# visible text, so that case is refused, not allowed — see the NOTE
# above test_css_url_escape_decoding_to_local_allowed.)
