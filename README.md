# CV

This repository tracks my CV, and adds scaffolding to re-build it
automatically on new changes/commits, as well as serving it through different
forms.

## Adding records with an AI agent

The CV is structured data (`src/cv.json` for the body, `src/publications.json`
for publications) with a swappable renderer — see `ARCHITECTURE.md`. A bundled
[Agent Skill](https://code.claude.com/docs/en/skills),
`.claude/skills/add-cv-record/`, teaches an agent to append a new record
correctly: it picks the right file, authors from `src/cv.template.json`'s
examples, validates against `src/cv.schema.json`, and opens the change as a PR.
It never edits the renderers.

**Install:** nothing to install — the skill lives in the repo. Any agent that
discovers `.claude/skills/` picks it up automatically.

**Use with [Claude Code](https://code.claude.com):** run `claude` in the repo
and just ask, e.g.

> Add this paper: https://doi.org/10.1111/gean.12205

For a DOI the skill fetches the record as CSL-JSON directly, so you rarely need
to type any fields. It works for any record type ("add this grant…", "add this
talk…").

**Use with [OpenCode](https://opencode.ai):** OpenCode reads `.claude/skills/`
natively, so the same skill works unmodified — including with a **local model**
(e.g. via Ollama/LM Studio), since the steps only need `curl`, `git`, and
`python3`. Just run `opencode` in the repo and ask the same way. With smaller
local models, prefer giving a DOI/URL so the skill fetches structured data
rather than transcribing it.

**Validate manually** (optional; the skill runs this for you):

```bash
python3 src/validate_cv.py      # or: make validate
```

Every addition lands as a PR — CI then rebuilds the PDF and web page from the
new data.

## Subset CVs

Shorter, audience-specific CVs built from the same data — see
`notes/SUBSET-CV-SPEC.md`. A TOML config, kept **outside this repository**,
lists the sections (and optionally the record ids) to include:

```bash
make subset-new CONFIG=~/cv-subsets/erc-2027.toml   # starter config: every section + id
# ...delete the sections and ids you don't want, then:
make subset CONFIG=~/cv-subsets/erc-2027.toml
```

Outputs land beside the config (`~/cv-subsets/erc-2027/`): the PDF, the
derived data, a copy of the config and a `manifest.json`. Rebuild any time
with the same `make subset` line. `make subset-list [SECTION="Teaching"]`
prints record ids with their dates and titles; `src/subset.template.toml`
documents every config key. Subsets are private: the build refuses to write into the repo,
`.gitignore` ignores `*.toml`, and CI fails if one is ever committed.

## AI

I have used extensively AI tools to build the infrastructure around this CV,
but no AI was used in adding any content to the CV.
