# CV build pipeline. Design rationale lives in ARCHITECTURE.md.
#
# Source of truth is src/ (hand-edited JSON + the Typst renderer).
# Build outputs go to docs/ (served by GitHub Pages later).

TYPST    ?= typst
PYTHON   ?= python3
SRC      := src/cv.typ
PDF      := docs/cv.pdf
HTML     := docs/index.html
JSON     := $(wildcard src/*.json)
PREVIEW  := build/preview
FONTS    := fonts

.PHONY: site pdf html watch preview validate clean

## site: build both the PDF and the HTML page  (default target)
site: pdf html

## pdf: build the CV PDF into docs/
pdf: $(PDF)

$(PDF): $(SRC) $(JSON) | docs
	$(TYPST) compile --font-path $(FONTS) $(SRC) $(PDF)

## html: build the CV web page into docs/ (index.html, style.css, fonts/)
html: $(HTML)

$(HTML): src/render_html.py src/style.css $(JSON) | docs
	$(PYTHON) src/render_html.py

docs:
	mkdir -p docs

## watch: rebuild the PDF on save while editing
watch: | docs
	$(TYPST) watch --font-path $(FONTS) $(SRC) $(PDF)

## preview: render one PNG per page into build/ for visual review
preview: | docs
	mkdir -p $(PREVIEW)
	$(TYPST) compile --font-path $(FONTS) --format png --ppi 120 $(SRC) "$(PREVIEW)/cv-{p}.png"

## validate: check every src/*.json parses
validate:
	@for f in $(JSON); do python3 -m json.tool "$$f" > /dev/null && echo "OK  $$f"; done

## clean: remove build/preview artifacts (the committed PDF/HTML stay)
clean:
	rm -rf $(PREVIEW)
	rm -f $(PDF) $(HTML) docs/style.css
	rm -rf docs/fonts
