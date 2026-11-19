# VektorShot

Screenshot in, working page out. A vision model reads the picture, the
page is generated in the VektorFlow design system, Playwright renders it
and compares it to the original, and static checks verify it before
handover.

## How it works

1. **Vision** — a provider reads the screenshot into a structured
   `LayoutDescription`: headings, text, buttons, nav, cards, images,
   inputs. Free-tier-first routing: Ollama, then Gemini, then Groq.
   Phase 1 ships a deterministic stub provider so the whole pipeline
   can be built and tested with no live model and no keys.
2. **Generate** — `vektorshot.generate_page()` writes one self-contained
   HTML + Tailwind page: dark theme, cyan accent, brand V. Text is
   escaped, images are local placeholders (never hotlinked), and
   secret-looking text refuses to generate.
3. **Self-check** — Playwright renders the page headless and screenshots
   it; the loop compares against the original and fixes mismatches, up
   to 3 rounds, then hands over with an honest report.
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

Run the self-check where a browser exists — local Termux or Daytona,
never Render free tier (Chromium does not fit in 512 MB):

```python
from vektorshot import build_screenshot_command
argv = build_screenshot_command("page.html", "render.png")
```

## Tests

```bash
python3 -m pytest tests/ -q
```

20 tests, stdlib only. PNG fixtures are built in-test; no network, no
keys, no live model calls.

## Skill

`skills/vektorshot/SKILL.md` is the VektorCode skill file: it tells an
agent how to drive vision, generate, self-check, verify, and hand over.
It loads cleanly in VektorCode's skill loader
(`vektor_cloud/skills.py`): discovered as `vektorshot`, body well under
the 12,000-character cap.
