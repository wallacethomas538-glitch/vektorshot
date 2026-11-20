---
name: vektorshot
description: Turn a screenshot into working HTML + Tailwind code in the VektorFlow design system: live Gemini vision reads the picture, the model writes the page (or the template path builds it), Playwright renders and self-checks it with a compare-and-fix loop, and static checks verify it before handover.
---

# VektorShot

Screenshot in, working page out. A vision model reads the picture, the
page is generated in VektorFlow's design system, Playwright renders it
and compares it to the original, and static checks verify it before it
is handed over. Phase 1 is screenshot files only, HTML + Tailwind only.
Phase 2 adds live Gemini vision, model-written HTML, and a real
render → compare → fix loop.

## Rules

- Only build UIs from pictures the user has the right to use.
- Generated code that touches money, publishing, or sending needs the
  user's tap — approval-gated, same as every other risky step.
- Images are never hotlinked: image elements become local placeholders.
  Real assets are supplied as local files and scanned, never fetched
  from unknown hosts.
- Secrets live in environment variables only. Generated code never
  embeds a key, token, or cookie. If layout text looks like a secret,
  generation refuses — do not work around it.
- A generated page is untrusted until it is verified: static checks
  here plus a live Playwright render. A page that never rendered is
  handed over as unverified, never as done. Model-written HTML is
  doubly untrusted: safety gates first, then `check_html`, then the
  live render. The compare score is a guide, not proof — a page can
  score high and still read wrong.
- Free-tier-first: vision routes Ollama, then Gemini, then Groq. Every
  generation is costed at $0.00 in the ledger. If every free tier is
  dry, say so honestly — never fail silently, never charge.

## 1. Vision

```python
from vektorshot import select_provider
provider = select_provider()  # first reachable route, else the stub
layout = provider.analyze_screenshot(image_bytes)
```

`select_provider` reports honestly: when it returns the stub, no live
vision ran. Check routes with `available_providers()` — it probes
Ollama over local HTTP and reports key presence for Gemini/Groq. Key
presence is not proof a key works.

Live Gemini is wired (Phase 2). `GeminiVisionProvider` calls the
native endpoint (gemini-4-hydrogen, key from `GEMINI_API_KEY` only),
downscales screenshots to ~512px on the long edge first (big images
503/hang), 180s timeout, honest errors on missing key / 503 / timeout.
It also writes HTML directly (`provider.generate_html(image_bytes)`)
and lists differences between two screenshots
(`provider.compare_screenshots(original, render)`). Groq and Ollama
live calls are not wired yet.

## 2. Generate

Two paths. Template path (Phase 1):

```python
from vektorshot import generate_page
page = generate_page(layout)  # HTML + Tailwind, dark theme, cyan accent
```

One page, VektorFlow design system by default. Text is escaped, images
are local placeholders, secret-looking text refuses to generate.

Direct path (Phase 2) — the model writes the page, which is what
makes a rebuild look like the original instead of a generic sketch:

```python
from vektorshot import GeminiVisionProvider, generate_page_direct
provider = GeminiVisionProvider()
reply = provider.generate_html(image_bytes)
page = generate_page_direct(reply)  # same safety gates as generate_page
```

`generate_page_direct` refuses unsafe replies (secrets, `javascript:`
links, inline handlers, non-allowlisted external URLs) and injects the
Tailwind CDN script and a `<title>` when the model leaves them out.

## 3. Self-check

```python
from vektorshot import run_self_check
run = run_self_check(original_png, page.html, provider, "workdir")
```

Renders the page, scores it against the original
(`compare_images`: PIL pixel diff, or an honestly-labeled weak
byte-length fallback when PIL is absent), asks the vision model for
concrete differences, and re-prompts it with that list — up to 3
rounds, then hands over with an honest report (`run.accepted`,
`run.history`, `run.notes`). Run it where a browser exists — local
Termux or Daytona, never Render free tier (Chromium does not fit in
512 MB). If the Playwright-managed browser is missing, pass
`executable_path` to `render()` with the Chromium binary to use.

## 4. Verify

```python
from vektorshot import check_html
report = check_html(page.html)
```

Static checks: document structure, allowlisted externals only (the
Tailwind CDN), no secrets, no `javascript:` links, no inline handlers.
`report.requires_live_render` is always True until a Playwright render
proves the page actually renders with no console errors.

## 5. Hand it over

The page lives in the output directory. Tell the user what it is, what
vision route produced it (live or stub), the self-check result, and
what verification passed. Attach the render screenshot as proof. If
anything is unverified, say so plainly.
