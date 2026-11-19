---
name: vektorshot
description: Turn a screenshot into working HTML + Tailwind code in the VektorFlow design system: vision reads the picture, code is generated, Playwright renders and self-checks it, and static checks verify it before handover.
---

# VektorShot

Screenshot in, working page out. A vision model reads the picture, the
page is generated in VektorFlow's design system, Playwright renders it
and compares it to the original, and static checks verify it before it
is handed over. Phase 1 is screenshot files only, HTML + Tailwind only.

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
  handed over as unverified, never as done.
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
presence is not proof a key works. Live model calls are not wired in
Phase 1; the stub stands in for tests.

## 2. Generate

```python
from vektorshot import generate_page
page = generate_page(layout)  # HTML + Tailwind, dark theme, cyan accent
```

One page, VektorFlow design system by default. Text is escaped, images
are local placeholders, secret-looking text refuses to generate.

## 3. Self-check

```python
from vektorshot import SelfCheckLoop, build_screenshot_command
loop = SelfCheckLoop(max_rounds=3, accept_threshold=0.85)
argv = build_screenshot_command("page.html", "render.png")
```

Run the command where a browser exists — local Termux or Daytona,
never Render free tier (Chromium does not fit in 512 MB). Compare the
render against the original, then `loop.record(round_no, similarity,
issues)`: accept at 0.85 or above, fix while rounds remain, give up
after round 3 and hand over as-is with an honest report.

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
