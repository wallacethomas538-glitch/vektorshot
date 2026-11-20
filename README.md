# VektorShot

Screenshot in, working page out. A vision model reads the picture, the
page is generated in the VektorFlow design system, Playwright renders it
and compares it to the original, and static checks verify it before
handover.

## How it works

1. **Vision** — a provider reads the screenshot. Free-tier-first
   routing: Ollama, then Gemini, then Groq. **Phase 2 wires Gemini
   live:** `GeminiVisionProvider` calls the native endpoint
   (gemini-4-hydrogen, key from `GEMINI_API_KEY` only), downscales
   screenshots to ~512px on the long edge first (big images 503/hang),
   180s timeout, honest errors. It can return a structured
   `LayoutDescription`, write HTML directly, or list visible
   differences between two screenshots. Phase 1 ships a deterministic
   stub provider so the whole pipeline can be built and tested with
   no live model and no keys.
2. **Generate** — two paths. `vektorshot.generate_page()` (Phase 1
   template) writes one self-contained HTML + Tailwind page from a
   layout: dark theme, cyan accent, brand V. Text is escaped, images
   are local placeholders (never hotlinked), and secret-looking text
   refuses to generate. **`vektorshot.generate_page_direct()` (Phase 2)
   takes the model's own HTML** and runs it through the same safety
   gates — secret scan, no `javascript:` links, no inline handlers,
   no non-allowlisted external URLs (Tailwind CDN only). The direct
   path is what makes a rebuild look like the original.
3. **Self-check** — Playwright renders the page headless and screenshots
   it; `compare_images` scores it against the original (PIL pixel
   diff, or an honestly-labeled weak byte-length fallback); the vision
   model lists concrete differences; the loop re-prompts it with that
   list, up to 3 rounds, then hands over with an honest report.
   `render()` accepts an `executable_path` for Chromium when the
   Playwright-managed browser is not the one available.
4. **Verify** — static checks: document structure, allowlisted externals
   only (the Tailwind CDN), no secrets, no `javascript:` links, no
   inline handlers. A page is untrusted until a live render proves it.

## Secrets

Secrets are read from environment variables at call time
(`GEMINI_API_KEY`, `GROQ_API_KEY`, `OLLAMA_HOST`). Generated code
never contains a key, token, or cookie. That is deliberate.

## Usage

```python
from vektorshot import select_provider, generate_page, check_html

provider = select_provider()  # first reachable route, else the stub
layout = provider.analyze_screenshot(image_bytes)
page = generate_page(layout)
report = check_html(page.html)  # static checks; live render still owed
```

Model-written HTML (Phase 2, live Gemini):

```python
from vektorshot import GeminiVisionProvider, generate_page_direct

provider = GeminiVisionProvider()  # key from GEMINI_API_KEY
reply = provider.generate_html(image_bytes)  # model writes the page
page = generate_page_direct(reply)  # same safety gates as generate_page
report = check_html(page.html)
```

Full loop (Phase 2) — render, compare, fix, up to 3 rounds:

```python
from vektorshot import run_self_check

run = run_self_check(original_png, page.html, provider, "workdir")
print(run.accepted, run.history, run.notes)
```

Run the self-check where a browser exists — local Termux or Daytona,
never Render free tier (Chromium does not fit in 512 MB). If the
Playwright-managed browser is missing, pass its path:

```python
from vektorshot import render
render("page.html", "render.png",
       executable_path="/home/hatch/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome")
```

## Tests

```bash
python3 -m pytest tests/ -q
```

40 tests (20 Phase 1 + 20 Phase 2), stdlib only except Pillow for the
downscale/compare tests. PNG fixtures are built in-test; no network, no
keys, no live model calls — the Gemini transport is mocked.

## Skill

`skills/vektorshot/SKILL.md` is the VektorCode skill file: it tells an
agent how to drive vision, generate, self-check, verify, and hand over.
It loads cleanly in VektorCode's skill loader
(`vektor_cloud/skills.py`): discovered as `vektorshot`, body well under
the 12,000-character cap.
