# QuoteCraft — layer-based quote poster editor

A browser-native poster editor for quote graphics, with an **AI copilot that actually operates the app**.
Everything stays as real, editable layers (text, quote marks, shapes, lights, gradients, particles, images,
groups) until the moment you export.

The whole app is a **single portable HTML file** after building — open it from a file path, a USB stick,
any static host, or install it as a PWA on a phone.

---

## Quick start

```bash
npm install
npm run dev        # http://localhost:5173 (also reachable from your phone on the LAN)
npm run build      # → dist/index.html  (one self-contained file)
npm run preview    # serve the production build
```

Verification suite (no API key needed — the Gemini API is mocked):

```bash
npm run verify     # typecheck + tool-layer test + AI-loop test + headless UI test + build
npm run smoke      # editor/AI tool layer against the real stores
npm run smoke:ai   # streaming, tool calls, retries, model healing
npm run smoke:ui   # renders the real UI in a DOM shim
```

## What changed in this revision

**1. Model fix — retired models are gone, newest Flash is the default**
* Gemini 2.5 Flash (and 2.0/1.5/1.0 models) are closed to new API keys — projects that pinned them failed with 404s.
* The app now ships a curated catalog with **`gemini-3.8-flash` as the default**, plus automatic
  **migration of any retired model stored in your settings** and a live **“Refresh models”** button that reads
  the models your key actually has (`GET /v1beta/models`).
* If a model 404s mid-conversation the runtime **heals itself**: it walks the fallback chain
  (3.8 → 3.7 → 3.6 → 3.5 → flash-latest → 3.1-pro → 2.5), switches, tells you, and persists the new model.

**2. The AI can control everything**
* ~35 tool declarations wired straight into the editor stores: canvas size & background, every layer type,
  typography, styling, ordering, grouping, alignment, distribution, selection, zoom, preview mode, panels,
  interface theme/accent/density, saving, exporting, templates, palettes and the full design generator.
* The copilot loops through tool calls (up to 12 rounds / 40 calls per turn), streams its prose answer, and
  shows a per-action activity feed — each entry has a one-click **undo**.
* Undo/redo, selection and history all behave exactly as if you had done the work by hand.

**3. Better AI system**
* Streaming SSE responses (text appears as it is generated), function calling, thought-signature preservation
  (required by Gemini 3 for multi-turn tool use), retry/backoff on 429/5xx, `Retry-After` support,
  cancellation, and a compatibility fallback for models that reject newer request fields.
* A design-aware system prompt: hierarchy, colour harmony, lighting, negative space, restraint — plus a
  palette library and canvas presets it can apply directly.

**4. Works on every device**
* Three shells: phone (bottom nav + bottom sheets), tablet (icon rail + slide-over inspector, including
  landscape phones), desktop/wide (rail + canvas + fixed inspector).
* `100dvh` layout, safe-area insets (notch/home bar), visual-viewport tracking so the composer stays above the
  keyboard, pinch-zoom & two-finger pan, 38px touch targets on coarse pointers, hover-only controls made
  permanently visible on touch, `prefers-reduced-motion`, light/dark themes, and a graceful message instead of
  a crash on browsers without 2D canvas.

**5. Easier workflow**
* **Command palette** (`Ctrl/⌘+K`) for every action — including the same tool layer the AI uses.
* **Selection toolbar** floating over the canvas: properties, duplicate, front/back, group/ungroup, delete.
* **Copilot** with a one-field design studio, contextual suggestion chips and instant streaming.
* Drag & drop or paste images straight onto the canvas, autosave with a configurable delay, toasts with
  actions, shortcuts dialog, installable offline PWA, and a start screen with template quick-starts.

**6. UI**
* A single tokenised design system (Tailwind v4 `@theme` + CSS variables) with dark **and** light themes,
  eight accent colours, compact/comfortable density, glass surfaces, coherent motion, focus rings,
  accessible roles/labels everywhere and a proper empty/error state for every panel.

## Using the AI

1. Get a key from Google AI Studio.
2. **Settings → AI → paste the key → “Test & connect”** (stored only in this browser; sent only to Google).
3. Press **AI** in the top bar (or `Ctrl/⌘+J`) and talk to it:
   * “Create a cinematic poster about patience, 1080×1350, warm amber light and a gold hairline.”
   * “Make it feel more premium and give it more negative space.”
   * “Switch to the Emerald Luxury palette, then export a 2× PNG.”
   * “Set the UI to light theme with a cyan accent.”

Without a key the entire manual editor keeps working — nothing is gated.

## Keyboard shortcuts

| Action | Keys |
| --- | --- |
| Command palette / Copilot | `⌘K` / `⌘J` |
| Undo / Redo | `⌘Z` / `⇧⌘Z` |
| Save / Export | `⌘S` / `⌘E` |
| Duplicate / Group / Ungroup | `⌘D` / `⌘G` / `⇧⌘G` |
| Front / Back | `⌘⇧]` / `⌘⇧[` |
| Nudge 1px / 10px | arrows / `⇧`+arrows |
| Zoom in-out / 100% / fit | `⌘+` `⌘−` / `⌘0` / `⇧1` |
| Preview / Hand tool | `P` / `H` |
| Toggle light & dark | `⇧⌘L` |
| All shortcuts | `?` |

## Project layout

```
src/
  ai/
    agent/        prompt, runtime (tool loop) and tools (the app-control layer)
    gemini/       model catalog, client (streaming/tools/retries), schemas, validator
  components/
    ai/           copilot chat UI
    editor/       shell, top bar, toolbars, panels, dialogs, command palette
    settings/     settings + AI configuration
    templates/    template library + dialogs
    ui/           design-system primitives (modal, sheet, slider, toast host…)
  engine/         canvas, elements factory, palettes, fonts, masking, export, serialisation
  store/          editor, project (IndexedDB), settings, AI, UI
public/           manifest, service worker, icon
scripts/          headless verification suite
```

## Privacy

No accounts, no backend, no analytics. Projects and keys live in your browser (IndexedDB / localStorage);
AI prompts go directly from your browser to `generativelanguage.googleapis.com` with your key.
