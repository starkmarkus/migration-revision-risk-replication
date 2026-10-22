# Implementation decisions — 18 October 2026

Recorded before the five outcome analyses. The numerical requirements in protocol-v1.json are unchanged.

- The date in an ABS detailed workbook is its file availability date. An explicit later archive-link date takes precedence. The release-page date and workbook date are retained separately. A release cannot supply exact counts before its detailed file was available. If the latest issued edition has no available exact cube at the cutoff, the panel records a missing observation; it does not silently fall back to a preceding edition or a rounded series.
- ABS September 2012 has a March 28, 2013 headline release but an April 18 detailed cube. June 2019 has a December 19 header and December 20 archive-link date. March 2022 has a September 21 release-page timestamp and September 26 cube header. These discrepancies are retained, not harmonised to an assumed first-day file.
- Initial release means the first archived edition containing the reference period. Its exact-count file availability and headline date are both recorded. NZ quarterly initial estimates require all three months in one edition. This is not a reconstruction of an unavailable first-day byte stream.
- Official provisional/final labels are recorded as unknown where the consolidated estimate panel has no explicit label. Neither zero standard error nor an age rule is substituted for an observed label.
- Bootstrap indices preserve the complete ordered calendar grid. Missing or excluded observations remain missing on that grid rather than compressing the time distance. Main matched-country age profiles require the same complete periods in both countries. Supplemental cohorts have their own disclosed balanced masks.
- Descriptive pandemic subgroups use reference periods before 2020, 2020–2022, and 2023 onward. These broad calendar groups are not causal or agency-specific restrictions. The NZ training change is flagged by the documented publication date; other corrections are recorded as event context, not assigned causal shares.
- Empirical country differences are NZ minus Australia on identical periods. Intervals are pointwise stationary-bootstrap sensitivity intervals, not multiplicity-adjusted tests or guarantees of future stability.
- The 24-month level sensitivity compares both reference definitions on the same eligible periods. The corresponding directional sensitivity is only computed when preceding-year exact counts exist in both reference vintages.

## Calendar-gate findings before outcome estimation

- ABS March 2019 detailed counts are linked as released 4 October 2019, after the 30 September six-month cutoff, although the headline issue is dated 19 September. The archive page confirms the separate October date. The common complete-path quarterly cohort is therefore 24 quarters, not 25. No date is moved to retain the omitted quarter.
- NZ Departures and Net migration label October 2021 as 30 October, while Arrivals uses 31 October. These are explicitly monthly rows. Normalize all monthly identifiers to calendar month-end, retaining the original date in `normalized_month_labels.csv`; no estimate is altered. Quarterly aggregation already grouped calendar months correctly.
- In the Australian extended history, the delayed September 2012 and March 2019 cubes also affect later-age snapshots for earlier reference quarters. The complete-path rule excludes those quarters from that balanced profile; age-specific availability and the entire calendar grid remain in the outputs.

## Result-driven diagnostic clarifications

- The NZ interval finding was checked against all archived monthly estimate and standard-error cells. No zero standard errors occur at the evaluated ages in the 75-month cohort. Low revision coverage is therefore not explained by collapsed zero-width intervals. Coverage is also reported by reference year and by the documented publication regime; no causal effect is inferred from these subgroup summaries.
- For the ABS December 2024 treatment, the descriptive case comparison brackets the whole announcement month with the September 2024 and March 2025 publications. Exact overlapping quarters already at least 18 months old are compared. This small overlap cannot reconstruct all historical corrections or isolate the treatment from other changes. A zero detected change in these cells does not prove there were no changes elsewhere.


## Source catalogue

```json
{
  "schemaVersion": 1,
  "items": [
    {
      "id": "research-design-sources",
      "title": "Methodological foundations of the research design",
      "queries": [
        {
          "id": "migration-revision-literature",
          "source": {
            "label": "Official migration methodology",
            "links": [
              {
                "label": "ONS: Predicting the stability of migration estimates",
                "url": "https://www.ons.gov.uk/peoplepopulationandcommunity/populationandmigration/internationalmigration/methodologies/predictingthestabilityofnoneulongterminternationalmigrationestimates"
              },
              {
                "label": "ABS: Measuring Net Overseas Migration",
                "url": "https://www.abs.gov.au/articles/measuring-net-overseas-migration-australia"
              },
              {
                "label": "ONS: Quantifying uncertainty",
                "url": "https://www.ons.gov.uk/methodology/methodologicalpublications/generalmethodology/onsworkingpaperseries/quantifyinguncertaintyinheadlineinternationalmigrationestimates"
              }
            ],
            "caveats": [
              "The thresholds, evaluation windows and fixed reference horizon are study design choices, not official quality standards."
            ]
          },
          "summary": "Existing revision analyses and the distinction between model uncertainty and later revisions limit claims of novelty and calibration."
        },
        {
          "id": "statistical-methods",
          "source": {
            "label": "Statistical literature",
            "links": [
              {
                "label": "Gneiting and Raftery 2007",
                "url": "https://doi.org/10.1198/016214506000001437"
              },
              {
                "label": "Politis and Romano 1994",
                "url": "https://doi.org/10.1080/01621459.1994.10476870"
              }
            ],
            "caveats": [
              "Block bootstrap methods require assumptions about temporal dependence and stability. The cited literature does not guarantee reliable inference from 24 quarters affected by structural changes."
            ]
          },
          "summary": "Interval evaluation accounts jointly for width and non-containment; block resampling preserves local temporal dependence."
        },
        {
          "id": "official-revision-analysis",
          "source": {
            "label": "Revision analysis and dissemination practice",
            "links": [
              {
                "label": "McKenzie (2006), OECD revision analysis",
                "url": "https://doi.org/10.1787/146528313656"
              },
              {
                "label": "Eurostat (2013), ESS guidelines on revision policy",
                "url": "https://doi.org/10.2785/42763"
              }
            ],
            "caveats": [
              "Macroeconomic revision guidance provides methodological context; it does not establish migration-specific quality thresholds."
            ]
          },
          "summary": "Fixed-horizon revision measures, transparent schedules and interpretation for users predate this comparative migration study."
        }
      ]
    }
  ]
}

```
