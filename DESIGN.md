# VektorShot — Design (name LOCKED Nov 19, Wallace: "I like the name")

**Status:** Phase 1 built, tested 20/20, live-tested on the real
VektorFlow AI Systems space (Nov 19). **Phase 2 built Nov 19 (local
only — not pushed, not merged, not deployed):** live Gemini vision,
model-written HTML through the same safety gates, and a real
render → compare → fix loop. The template path was too weak — Wallace:
"That is not a website" — so Phase 2 is the model-driven path. Big
Chat review of Phase 1 is still queued; Phase 2 review is owed too.

## Where the concept comes from

Studied, not copied: `abi/screenshot-to-code` (MIT, Copyright 2023 Abi Raja),
read-only inspection at `~/workspace/screenshot-to-code-inspect`, commit
`f2e5bbd`. Per Wallace's IP rule (Oct 31): learn from concepts only, build it
our way. No code from that repo goes into VektorFlow.

## The concept, in one line

A screenshot, mockup, or Figma design becomes working code: a vision model
reads the picture, writes the page, then screenshots its own output and fixes
what doesn't match.

## Why it fits VektorFlow

VektorCode builds from words today. This lets it build from a picture — a
sketch of a store page, a screenshot of a dashboard you like, a mockup for a
client. "Make it look like this" becomes working code. It also pairs with
VektorBridge: Bridge pulls live data, Shot builds the page that shows it.

## How ours works (our own parts, our own code)

1. **Input — screenshot first.** A file you drop in VektorCode chat, or a
   path you point at. Phase 1 is screenshot files only.
2. **Vision — free-tier-first cascade.** VektorCode's existing routing
   (Gemini Hydrogen / Groq vision / local Ollama vision) reads the picture:
   layout, text, colors, components. **Phase 2 wires Gemini live:**
   `GeminiVisionProvider` calls the native endpoint (Hydrogen, key from
   `GEMINI_API_KEY` only), downscales screenshots to ~512px first (big
   images 503/hang — proven Nov 19), 180s timeout, honest errors on
   missing key / 503 / timeout. Groq and Ollama live calls are not
   wired yet.
3. **Generation — model-written HTML first, template as fallback.**
   Phase 1's `generate_page()` fills a fixed template from a structured
   layout — safe, but the rebuild looks like a sketch, not the site.
   **Phase 2's `generate_page_direct()` takes the model's own HTML**
   and runs it through the same safety gates (secret scan, no
   `javascript:` links, no inline handlers, no non-allowlisted external
   URLs — Tailwind CDN only), injecting the Tailwind script and a
   `<title>` when the model leaves them out. HTML + Tailwind, in
   VektorFlow's design system by default (dark theme, cyan accent,
   brand V).
4. **Self-check — Playwright, wired for real.** Already our chosen browser tool (Nov 18).
   Render the page headless, screenshot it, compare it to the original
   (PIL pixel diff, or an honestly-labeled weak byte-length fallback
   when PIL is absent), ask the vision model for concrete visible
   differences, and re-prompt it with that list. Up to 3 rounds, then
   hand over what it has with an honest report. `render()` takes an
   optional `executable_path` for Chromium (the installed Playwright
   wants headless-shell 1255; the cache holds Chromium 1248).
5. **Verification — TEST-FIRST.** The page must render with no console
   errors and no broken asset references before it is handed over. Screenshot
   proof attached. Model-written HTML is untrusted until `check_html`
   passes AND a live render proves it.
6. **Skill — a VektorCode skill.** The code lands in the repo you are already
   working on. No second app to deploy, no second backend to keep alive.

## What we're adding for ownership

This is what makes it ours, not a copy with our name on it:

1. **Free-tier-first + $0 ledger.** Theirs needs paid keys (GPT, Claude,
   Gemini 3, Replicate) for its best results. Ours routes free vision models
   first and proves $0 per generation — and says so honestly when every free
   tier is dry, instead of failing silently or charging.
2. **VektorCode-native skill, not a standalone app.** Theirs is a whole
   second product: React frontend + FastAPI backend + Docker. Ours lives
   inside VektorCode as a skill. Nothing new to deploy.
3. **VektorFlow design system by default.** Every generated page looks like
   ours out of the box — dark, cyan, brand V — instead of generic.
4. **Bridge + Shot compose.** VektorBridge gets live data from any site;
   VektorShot builds the page that shows it. Neither tool we studied does
   both. Together they turn "that site, but ours" into a working page.
5. **Approval-gated + Aegis.** Generated code that touches money, publishing,
   or sending needs Wallace's tap, same as every other risky step. Images
   pulled out of a screenshot are saved locally and scanned — never hotlinked
   from unknown hosts.
6. **Secrets via env vars, never hardcoded.** Same rule as VektorBridge.
   Generated code never embeds credentials.
7. **Honest quality ladder.** Free vision models are weaker than the paid
   ones theirs uses — said up front, not discovered later. The self-check
   loop closes much of the gap. If a buyer wants the paid models, they bring
   their own key — same rule as the selling ladder.

## Phases

- **Phase 0:** Big Chat reviews this design. First verify the free vision
  inputs with a small probe before any build: Hydrogen image input, a Groq
  vision model, local Ollama vision. If a route can't see pictures, it is
  out — no guessing. (Done Nov 19: Hydrogen reads images; big images
  503/hang, downscale first.)
- **Phase 1:** Screenshot → HTML + Tailwind, Playwright self-check, skill
  wiring into VektorCode. **DONE Nov 19** (20 tests, repo live) — but the
  template rebuild was too weak to call a website.
- **Phase 2:** Live Gemini vision + model-written HTML + real
  compare-and-fix loop. **BUILT Nov 19 (local only, 40 tests passing).**
  This replaces the old Phase 2 plan below — Wallace ordered the
  better-websites fix first, and it is what the live test proved we
  needed.
- **Phase 3 (was Phase 2):** React + Tailwind; asset extraction (real
  logos/images out of the shot, saved locally).
- **Phase 4 (was Phase 3):** Figma import; video → prototype.

## Open decisions (Wallace)

- Final name — **LOCKED Nov 19: VektorShot** (Wallace: "I like the name").
- First UI to prove it on — **DECIDED + TESTED Nov 19:** the VektorFlow
  AI Systems space. Template rebuild proved too weak; Phase 2 re-test
  on the same UI is owed.
- Free-only vision, or allow buyer-supplied paid keys as an option.

## Limits, stated up front

- Free vision models are weaker than the paid ones theirs uses — first
  outputs will be rougher; the self-check loop closes much of the gap.
- Screenshot-only in Phase 1; Figma and video come later.
- Generated code is untrusted until it renders clean and passes the checks.
  Model-written HTML is doubly untrusted: it passes the safety gates
  first, then `check_html`, then a live render. The compare score is a
  guide, not proof — a page can score high and still read wrong.
- Only build UIs from pictures you have the right to use.
