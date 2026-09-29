# AFLA beginner slide decks

| Deck | Slides | For |
|---|---|---|
| `AFLA_1_Getting_Started` (.pptx / .pdf) | 13 | installing, resources, putting AFLA in EPI2ME, inputs, library types, first run, troubleshooting, glossary |
| `AFLA_2_Germline_Analysis` | 15 | pipeline, case set-up, report tour, filtering funnel, trio inheritance, ACMG/AMP panel and points, HPO, CNV/ROH, exercise mode, accuracy, pitfalls |
| `AFLA_3_Somatic_Analysis` | 12 | germline vs somatic, running a tumour, amplicons/UMIs, tumour-only vs paired, TMB/MSI, tiers, evidence sources, CNV/fusions, exercise, pitfalls |

Screenshots are from real AFLA reports on public GIAB reference data (chromosome 20). Speaker notes on some slides
give teaching hints. Pair them with `docs/TEACHING_GUIDE.md`.

Rebuilding: `src/screenshots.js` captures report screenshots (Playwright + Chromium) and `src/make_slides.js` builds the
decks (pptxgenjs). Paths inside them point to the development machine's demo reports; adjust them before reuse.
