# Migration revision risk

Data and analysis code for **When Do Migration Estimates Stabilize? Revision Risk in Australia and New Zealand**.

This repository reconstructs historical revisions to published migration estimates,
compares quarterly and annual monitoring horizons, examines arrivals/departures
offsets, and evaluates an exploratory empirical revision-interval benchmark.
Data freeze: 18 October 2026. Distribution: 1.3.1-analysis.

## Reproduce

Use Python 3.12 in a dedicated environment. From the repository root:

```text
python verify_archive.py
python -m pip install -r requirements.txt
python run_replication.py
```

The analysis uses frozen extracted vintage panels and two retained original New
Zealand workbooks. No data downloads are required. The runner recomputes the
analyses, bootstrap sensitivities and revision benchmark, generates numerical
claims, twelve table blocks and four figure previews, and runs numerical validations and
six synthetic tests. Package versions are pinned in `requirements.txt`.

## Outputs

- `analysis/`: recomputed observation-level panels, descriptive results,
  sensitivities, benchmark predictions and validation records.
- `paper/numerical_claims.csv`: individual numerical statements with their inputs.
- `paper/evidence_blocks.json`: numerical claims and LaTeX table/figure blocks.
- `paper/Numerical_Evidence.tex`: concatenated numerical evidence blocks, intended
  for inspection or inclusion in a separate document, not standalone compilation.
- `paper/evidence/`: figure previews, plotting inputs and numerical validation.
- `run_logs/`: step logs and execution status, generated locally.

Three contextual tables are retained in `paper/context_tables.tex`; the other
nine tables and all four figures are calculated from the analysis outputs.

Article prose, submission correspondence and manuscript PDFs are maintained
separately. The repository reproduces the numerical analysis and display content;
it does not generate submission-ready manuscripts. The template compilation and
manuscript citation/format checks are therefore outside this runner's scope.

## Data and provenance

`results/nz_vintages.csv` and `results/abs_vintages.csv` are frozen extracted public
aggregate observations. `results/archive_manifest.json` and `INPUT_PROVENANCE.json`
record source URLs, release metadata, original-file hashes and frozen-input hashes.
`raw/` contains two original Stats NZ workbooks. `design/` retains the analytical
protocols. `MANIFEST.json` and `verify_archive.py` verify the distributed files.

The complete source collection has 210 workbooks. This compact repository contains
two; the other 208 remain in a separate local archive. Original workbook extraction
and checks against the omitted originals are not rerun here. Australian validation
reconciles against the frozen extracted panels. Original-cell checks remain for
the two included New Zealand workbooks. No full-source audit is implied.

## Interpretation

The later published reference remains an estimate rather than observed true
migration. Monitoring horizons are not recommendations to delay publication.
Country comparisons do not rank statistical systems. The revision-interval
benchmark is exploratory; endpoint dependence, production changes, interval
widths and differences in target quantities matter for interpretation.

## Licence

Original software and technical documentation use the MIT licence in `LICENSE`.
Agency data retain the attribution and reuse terms in `SOURCE_RIGHTS.md`.
Neither agency endorses this study. Manuscript text is not licensed by this
repository. See `VALIDATION.json` for the scope and results of verification.
