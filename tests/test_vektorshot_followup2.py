"""VektorShot follow-up 2 tests — Big Chat CHANGES REQUESTED review
of follow-up 1.

The follow-up-1 scanner let dangerous HTML through both gates.
Every bypass below was verified ACCEPTED by both gates on the
follow-up-1 commit ebe13c62 before this fix. Each test proves the
same HTML is now refused by BOTH generate_page_direct() and
check_html(), with the same named reason. No live model calls, no
keys, no network.
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


# --- Fix 1: event handlers with non-whitespace separators -------------

def test_handler_quote_adjacent_refused():
    # The handler follows the previous attribute's closing quote with
    # no whitespace: browsers still parse it as an attribute.
    assert_refused('<img src="x.png"onerror="alert(1)">',
                   "inline event handler", {"inline-handler"})


def test_handler_slash_adjacent_refused():
    # The handler follows a self-closing slash with no whitespace.
    assert_refused('<img src="x.png"/onerror="alert(1)">',
                   "inline event handler", {"inline-handler"})


def test_handler_entity_separator_refused():
    # The separator before the handler is itself entity-encoded, so a
    # whitespace-only check never sees a space.
    for sep in ("&#32;", "&#9;", "&#x0c;", "&Tab;", "&NewLine;"):
        assert_refused(f'<img src="x.png"{sep}onerror="alert(1)">',
                       "inline event handler", {"inline-handler"})


def test_handler_other_events_refused():
    for attr in ('onload="x()"', "onmouseover='x()'",
                 'onfocus = "x()"', 'onerror=alert(1)'):
        assert_refused(f'<img src="x.png" {attr}>',
                       "inline event handler", {"inline-handler"})


def test_handler_in_svg_refused():
    assert_refused('<svg><animate onbegin="alert(1)"></animate></svg>',
                   "inline event handler", {"inline-handler"})


# --- Fix 2: encoded dangerous URL schemes -------------------------------

def test_encoded_javascript_scheme_in_href_refused():
    # Browsers decode character references in attribute values, so
    # each of these is javascript: by the time the URL is parsed.
    for value in ("jav&#x61;script:alert(1)",
                  "&#106;avascript:alert(1)",
                  "java&Tab;script:alert(1)",
                  "java&#115;cript:alert(1)",
                  "&#x6A;avascript:alert(1)",
                  "javascript&#58;alert(1)",
                  "&#x0A;javascript:alert(1)",
                  "JaVaScRiPt:alert(1)"):
        assert_refused(f'<a href="{value}">x</a>',
                       "javascript", {"javascript-href"})


def test_encoded_scheme_in_other_resource_attrs_refused():
    cases = [
        ('<img src="jav&#x61;script:alert(1)">',
         "unsafe URL scheme", {"unsafe-url-scheme"}),
        ('<form action="java&Tab;script:alert(1)">x</form>',
         "unsafe URL scheme", {"unsafe-url-scheme"}),
        ('<iframe src="&#106;avascript:alert(1)"></iframe>',
         "unsafe URL scheme", {"unsafe-url-scheme"}),
    ]
    for body, match, codes in cases:
        assert_refused(body, match, codes)


def test_double_encoded_scheme_allowed():
    # Decoding happens exactly once, as in a browser: the value a
    # browser sees here is the literal text "&#106;avascript:..." —
    # an invalid scheme, i.e. a harmless relative URL.
    assert_allowed('<a href="&amp;#106;avascript:alert(1)">x</a>')


# --- Fix 3: unquoted srcset ----------------------------------------------

def test_srcset_unquoted_refused():
    cases = [
        ('<img src="x.png" srcset=javascript:alert(1)>',
         "unsafe URL scheme", {"unsafe-url-scheme"}),
        ('<img src="x.png" srcset=https://evil.example/a.png>',
         "not allowlisted", {"external-asset"}),
        ('<img src="x.png" srcset=data:image/png;base64,AAAA>',
         "unsafe URL scheme", {"unsafe-url-scheme"}),
    ]
    for body, match, codes in cases:
        assert_refused(body, match, codes)


# --- Fix 4: CSS url() ------------------------------------------------------

def test_css_url_javascript_refused():
    for style in ("background:url(javascript:alert(1))",
                  'background:url("javascript:alert(1)")',
                  "background:url('javascript:alert(1)')",
                  "background:url( javascript:alert(1) )",
                  "background:url(vbscript:msgbox(1))"):
        assert_refused(f'<div style="{style}">x</div>',
                       "unsafe URL scheme", {"unsafe-url-scheme"})


def test_css_url_in_style_block_refused():
    assert_refused("<style>div{background:url(javascript:alert(1))}"
                   "</style><div>x</div>",
                   "unsafe URL scheme", {"unsafe-url-scheme"})


def test_css_url_external_and_data_refused():
    cases = [
        ('<div style="background:url(https://evil.example/bg.png)">x'
         "</div>", "not allowlisted", {"external-asset"}),
        ('<div style="background:url(data:image/png;base64,AAAA)">x'
         "</div>", "unsafe URL scheme", {"unsafe-url-scheme"}),
    ]
    for body, match, codes in cases:
        assert_refused(body, match, codes)


# --- Fix 5: meta refresh ---------------------------------------------------

def test_meta_refresh_javascript_refused():
    cases = [
        '<meta http-equiv="refresh" content="0;url=javascript:alert(1)">',
        "<meta http-equiv=refresh "
        'content="0;url=javascript:alert(1)">',
        '<META HTTP-EQUIV="REFRESH" CONTENT="0;URL=javascript:alert(1)">',
        '<meta http-equiv="refresh" '
        "content=\"0;url='javascript:alert(1)'\">",
        '<meta http-equiv="refresh" '
        'content="0;url=jav&#x61;script:alert(1)">',
    ]
    for body in cases:
        assert_refused(body, "unsafe URL scheme", {"unsafe-url-scheme"})


def test_meta_refresh_external_refused():
    assert_refused(
        '<meta http-equiv="refresh" '
        'content="0;url=https://evil.example/x">',
        "not allowlisted", {"external-asset"})


# --- Positive controls: safe pages must still pass both gates ------------

def test_local_srcset_allowed():
    assert_allowed(
        '<img src="local.png" srcset="local.png 1x, local-2x.png 2x">'
        '<img src="local.png" srcset=local.png>')


def test_local_css_url_allowed():
    assert_allowed(
        '<div style="background:url(images/bg.png)">x</div>'
        '<div style="background:url(#frag)">y</div>')


def test_meta_refresh_local_allowed():
    # A refresh to a local page, a plain reload with no URL, and
    # non-refresh meta tags are all harmless.
    assert_allowed(
        '<meta http-equiv="refresh" content="5;url=/next.html">'
        '<meta http-equiv="refresh" content="5">'
        '<meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width">')


def test_handler_lookalikes_allowed():
    # "onload=" inside a value is text, not a handler: a title that
    # mentions it, a local URL whose path contains it, and a data-*
    # attribute whose name merely contains "onclick".
    assert_allowed(
        '<div title="click onload=now">x</div>'
        '<a href="pages/onload=1.html">y</a>'
        '<div data-onclick="doThing()">z</div>')


def test_encoded_script_text_allowed():
    # Entity-encoded tag names are inert text: browsers do not decode
    # them into tags, so visible text mentioning <script> is safe.
    assert_allowed("<p>Use &lt;script&gt; to add code.</p>")
