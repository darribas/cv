# Proof of concept — data-driven CV

This folder validates the pipeline chosen in [`../ARCHITECTURE.md`](../ARCHITECTURE.md)
**before** migrating the full 1,760-line `.tex`. It is a throwaway scratchpad:
a representative slice of the CV as structured data, plus a minimal Typst
renderer that turns it into a PDF.

The one question it exists to answer: **does hand-editing the JSON actually feel
good?** (ARCHITECTURE, "Known costs & open questions".)

## Files

| File | Role |
|------|------|
| `cv.json` | CV body as data (Education, Appointments, Research Income + a Publications pointer). Single source of truth. |
| `publications.json` | Publications as **CSL-JSON** (the format Zotero exports and pandoc/Typst read). |
| `cv.schema.json` | JSON Schema — gives VS Code autocomplete, hover docs, and red-underline validation. |
| `cv.template.json` | Copy-paste library: one annotated example per section type. |
| `cv.typ` | The renderer. The only bespoke artifact; owns all formatting. |

## Build

Typst is a single binary, no TeXLive needed:

```sh
# macOS
brew install typst
# then, from this folder:
typst compile cv.typ cv.pdf
```

`typst watch cv.typ cv.pdf` recompiles on save for live editing.

## What to look for

- **Authoring:** open `cv.json` in VS Code. Fields autocomplete; hovering a key
  shows its description; a mistyped key underlines red. Add an entry by copying a
  block from `cv.template.json`.
- **Comments in strict JSON:** any key starting with `//` (e.g. `"//note"`) is a
  comment the renderer ignores — no JSONC/preprocessing step.
- **Structure earning its keep:** amounts are `{value, currency}` and the
  renderer prints £/€/$ — the source never hard-codes a symbol. Publications are
  sorted by year by the renderer, not by hand.
- **PDF outline:** every section heading becomes a PDF bookmark (the TOC gap that
  motivated the whole effort).

## Known POC limitations

- Only 4 sections of the eventual ~18 are modelled — enough to exercise the
  interesting shapes (nested detail, currency, CSL publications).
- Publication formatting is a simple hand-rolled Typst function, not a full CSL
  style. Good enough to prove the data round-trips; a real CSL style can come later.
- **Fonts:** the renderer asks for TeX Gyre Pagella (a Palatino-alike, matching
  the current `mathpazo` look). If it is not installed, Typst falls back to its
  default serif and still compiles. CI will need the font provisioned explicitly.
