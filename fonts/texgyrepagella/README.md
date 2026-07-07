# TeX Gyre Pagella

Bundled so `typst compile --font-path fonts` finds a Palatino-alike without
depending on what's installed on the machine or CI runner — the original
`cv-darribas.tex` set its body font via `\usepackage{mathpazo}` (Palatino),
and TeX Gyre Pagella is the free, metric-matched clone TeXLive itself ships
as its Palatino substitute, so this is the closest free equivalent, not an
approximation of one.

Source: [TeX Gyre](http://www.gust.org.pl/projects/e-foundry/tex-gyre) by
GUST e-foundry (also on CTAN as `tex-gyre`), version 2.501.

> Copyright 2006-2018 for TeX Gyre extensions by B. Jackowski, J.M. Nowacki,
> et al. (on behalf of TeX USERS GROUPS). Vietnamese characters were added
> by Han The Thanh.

Licensed under the [GUST Font License](http://www.gust.org.pl/projects/e-foundry/licenses)
(GFL), which permits free use, modification and redistribution — see that
page for the full license text.
