# CV build pipeline. Design rationale lives in ARCHITECTURE.md.
#
# Source of truth is src/ (hand-edited JSON + the Typst renderer).
# Build outputs go to docs/ (served by GitHub Pages).

TYPST    ?= typst
PYTHON   ?= python3
SRC      := src/cv.typ
PDF      := docs/cv.pdf
HTML     := docs/index.html
JSON     := $(wildcard src/*.json)
# What `make site` renders: src/cv.json plus the heading summaries configured
# in src/summaries.json (src/build_site_data.py). Relative to src/ for Typst.
SITEDATA := build/site/cv.json
PREVIEW  := build/preview
FONTS    := fonts

.PHONY: site pdf html watch preview validate test rates subset subset-list clean

## site: build both the PDF and the HTML page  (default target)
site: pdf html

## pdf: build the CV PDF into docs/
pdf: $(PDF)

$(PDF): $(SRC) $(SITEDATA) | docs
	$(TYPST) compile --root . --font-path $(FONTS) --input data=../$(SITEDATA) $(SRC) $(PDF)

## html: build the CV web page into docs/ (index.html, style.css, fonts/)
html: $(HTML)

$(HTML): src/render_html.py src/style.css $(SITEDATA) | docs
	$(PYTHON) src/render_html.py --data $(SITEDATA)

$(SITEDATA): src/build_site_data.py src/build_subset.py $(JSON)
	$(PYTHON) src/build_site_data.py --out $(SITEDATA)

docs:
	mkdir -p docs

## watch: rebuild the PDF on save while editing (straight from src/cv.json,
##        so without the heading summaries of src/summaries.json)
watch: | docs
	$(TYPST) watch --font-path $(FONTS) $(SRC) $(PDF)

## preview: render one PNG per page into build/ for visual review
preview: $(SITEDATA) | docs
	mkdir -p $(PREVIEW)
	$(TYPST) compile --root . --font-path $(FONTS) --input data=../$(SITEDATA) --format png --ppi 120 $(SRC) "$(PREVIEW)/cv-{p}.png"

## validate: check every src/*.json parses, then schema + id checks
validate:
	@for f in $(JSON); do $(PYTHON) -m json.tool "$$f" > /dev/null && echo "OK  $$f"; done
	@$(PYTHON) src/validate_cv.py

## test: run the unit tests (tests/test_*.py; Typst-dependent ones skip without it)
test:
	$(PYTHON) -m unittest discover -s tests -v

## rates: refresh the exchange rates in src/summaries.json from the ECB's
##        daily reference rates (network), for the full CV's totals
rates:
	@$(PYTHON) src/build_site_data.py --update-rates

## Subset CVs (notes/SUBSET-CV-SPEC.md). Configs live in the gitignored
## subsets/ folder or outside the repo.
##
## subset: build a subset CV from its config — or, if CONFIG doesn't exist
##         yet, write a starter config there (every section and record id)
##         to edit, then run the same command again to build it
##         make subset CONFIG=~/cv-subsets/erc-2027.toml [OUT=dir]
subset:
	@test -n "$(CONFIG)" || { echo "usage: make subset CONFIG=path/to/config.toml [OUT=dir]"; exit 2; }
	@$(PYTHON) src/build_subset.py "$(CONFIG)" --new-if-missing $(if $(OUT),--out "$(OUT)")

## subset-list: print record ids (all, or one section)
##         make subset-list [SECTION="Research Income"]
subset-list:
	@$(PYTHON) src/build_subset.py --list $(if $(SECTION),"$(SECTION)")

## clean: remove build/ artifacts and the built docs/ files (restore the
##        committed ones with `git checkout docs`)
clean:
	rm -rf $(PREVIEW) $(dir $(SITEDATA))
	rm -f $(PDF) $(HTML) docs/style.css
	rm -rf docs/fonts
