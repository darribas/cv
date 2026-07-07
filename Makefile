# CV build pipeline. Design rationale lives in ARCHITECTURE.md.
#
# Source of truth is src/ (hand-edited JSON + the Typst renderer).
# Build outputs go to docs/ (served by GitHub Pages later).

TYPST   ?= typst
SRC     := src/cv.typ
PDF     := docs/cv.pdf
JSON    := $(wildcard src/*.json)
PREVIEW := build/preview
FONTS   := fonts

.PHONY: pdf watch preview validate parse clean

## pdf: build the CV PDF into docs/  (default target)
pdf: $(PDF)

$(PDF): $(SRC) $(JSON) | docs
	$(TYPST) compile --font-path $(FONTS) $(SRC) $(PDF)

docs:
	mkdir -p docs

## watch: rebuild on save while editing
watch: | docs
	$(TYPST) watch --font-path $(FONTS) $(SRC) $(PDF)

## preview: render one PNG per page into build/ for visual review
preview: | docs
	mkdir -p $(PREVIEW)
	$(TYPST) compile --font-path $(FONTS) --format png --ppi 120 $(SRC) "$(PREVIEW)/cv-{p}.png"

## validate: check every src/*.json parses
validate:
	@for f in $(JSON); do python3 -m json.tool "$$f" > /dev/null && echo "OK  $$f"; done

## parse: one-shot migration bootstrap (.tex -> draft JSON); not part of the normal build
parse:
	python3 tools/tex2cv.py

## clean: remove build/preview artifacts (the committed PDF stays)
clean:
	rm -rf $(PREVIEW)
	rm -f $(PDF)
