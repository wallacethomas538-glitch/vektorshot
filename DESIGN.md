# VektorShot — Design (name LOCKED Nov 19, Wallace: "I like the name")

**Status:** design only. No code written. Build awaits Big Chat review +
Wallace's tap (governance: Gemini builds, Mewsa verifies, Big Chat reviews,
Wallace decides).

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
   layout, text, colors, components.
3. **Generation — HTML + Tailwind first.** One stack, done well, in
   VektorFlow's design system by default (dark theme, cyan accent, brand V).
4. **Self-check — Playwright.** Already our chosen browser tool (Nov 18).
   Render the page headless, screenshot it, vision-compare against the
   original, fix mismatches. Up to N rounds, then hand over what it has with
   an honest report.
5. **Verification — TEST-FIRST.** The page must render with no console
   errors and no broken asset references before it is handed over. Screenshot
   proof attached.
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
  out — no guessing.
- **Phase 1:** Screenshot → HTML + Tailwind, Playwright self-check, skill
  wiring into VektorCode.
- **Phase 2:** React + Tailwind; asset extraction (real logos/images out of
  the shot, saved locally).
- **Phase 3:** Figma import; video → prototype.

## Open decisions (Wallace)

- Final name — **LOCKED Nov 19: VektorShot** (Wallace: "I like the name").
- First UI to prove it on — a store product page? the command center?
- Free-only vision, or allow buyer-supplied paid keys as an option.

## Limits, stated up front

- Free vision models are weaker than the paid ones theirs uses — first
  outputs will be rougher; the self-check loop closes much of the gap.
- Screenshot-only in Phase 1; Figma and video come later.
- Generated code is untrusted until it renders clean and passes the checks.
- Only build UIs from pictures you have the right to use.
