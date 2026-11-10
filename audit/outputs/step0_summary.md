# Step 0 site table: summary

Created 2026-11-10T07:15:43+00:00 by `audit/23_build_site_table.py`. SRDB commit 02163a7 (data update 30 Dec 2025); COSORE 0.8.0 (git 02f32e8); WorldClim 2.1 30" bioclim 1, 4, 5, 6, 12, 14, 15, 17; Natural Earth 1:10m map units.

## Record filters (applied in order)

| Source | Rule | Before | Removed | After |
|---|---|---:|---:|---:|
| SRDB | all SRDB records (srdb-data.csv @02163a7) | 14169 | 0 | 14169 |
| SRDB | Rs_annual reported | 14169 | 6377 | 7792 |
| SRDB | unmanipulated (Manipulation == 'None' or missing) | 7792 | 2828 | 4964 |
| SRDB | coordinates present and in bounds | 4964 | 134 | 4830 |
| SRDB | Rs_annual within 50-4500 g C m-2 yr-1 | 4830 | 60 | 4770 |
| SRDB | no quality flag Q10-Q14 | 4770 | 262 | 4508 |
| SRDB | not a known duplicate (Duplicate_record empty) | 4508 | 13 | 4495 |
| SRDB | annual coverage >= 1 or missing | 4495 | 881 | 3614 |
| SRDB | country field agrees with coordinates (flagged records excluded) | 3614 | 81 | 3533 |
| COSORE | COSORE full-year dataset-year records (Rs ports, treatment None) | 63 | 0 | 63 |
| COSORE | Rs_annual within 50-4500 and coordinates present | 63 | 0 | 63 |
| Both | record located on land or within 10 km of land (continent assigned) | 3596 | 0 | 3596 |
| Both | WorldClim value found within 3 pixels (~2.7 km) (12 records used a neighbouring pixel) | 3596 | 8 | 3588 |

Marginal counts (records with Rs_annual failing each rule on its own): manipulated (Manipulation not 'None' or missing): 2828; no/invalid coordinates: 162; Rs_annual outside 50-4500: 72; quality flag Q10-Q14: 318; known duplicate (Duplicate_record set): 64; annual coverage < 1: 1482; annual coverage missing: 613; country/coordinate mismatch: 149.

Records with annual coverage missing kept in `incl_missing`: 368 (SRDB). Records in `strict`: 3220.

## Variant `strict`: 3220 records, 965 sites (0.05-degree cells)

Share of cells with more than one record: 60.5%. Cells whose records fall in two continents: 0. Sites with a MODIS NPP value: 576.

| Continent | Records | SRDB | COSORE | Studies | Sites | Sites with 2+ records | 3+ | Median Rs (g C m-2 yr-1) | Var log Rs |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Asia | 1401 | 1386 | 15 | 490 | 392 | 245 | 168 | 771 | 0.372 |
| North America | 745 | 713 | 32 | 205 | 210 | 135 | 95 | 767 | 0.391 |
| Europe | 739 | 731 | 8 | 199 | 226 | 130 | 84 | 653 | 0.324 |
| South & Central America | 208 | 203 | 5 | 73 | 77 | 47 | 28 | 1401 | 0.411 |
| Africa | 58 | 58 | 0 | 25 | 27 | 13 | 8 | 893 | 0.384 |
| Oceania | 69 | 66 | 3 | 28 | 33 | 14 | 10 | 908 | 0.263 |
| Total | 3220 | 3157 | 63 | 1018 | 965 | 584 | 393 | 767 | 0.392 |

## Variant `incl_missing`: 3588 records, 1061 sites (0.05-degree cells)

Share of cells with more than one record: 59.6%. Cells whose records fall in two continents: 0. Sites with a MODIS NPP value: 639.

| Continent | Records | SRDB | COSORE | Studies | Sites | Sites with 2+ records | 3+ | Median Rs (g C m-2 yr-1) | Var log Rs |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Asia | 1587 | 1572 | 15 | 537 | 432 | 267 | 186 | 765 | 0.382 |
| North America | 794 | 762 | 32 | 228 | 236 | 141 | 97 | 764 | 0.426 |
| Europe | 821 | 813 | 8 | 217 | 243 | 139 | 93 | 650 | 0.339 |
| South & Central America | 232 | 227 | 5 | 81 | 84 | 53 | 33 | 1348 | 0.407 |
| Africa | 71 | 71 | 0 | 29 | 31 | 17 | 11 | 872 | 0.594 |
| Oceania | 83 | 80 | 3 | 33 | 35 | 15 | 11 | 898 | 0.250 |
| Total | 3588 | 3525 | 63 | 1121 | 1061 | 632 | 431 | 764 | 0.408 |

Continents: Natural Earth CONTINENT field, with Central America, the Caribbean and South America grouped as South & Central America (UN subregions; includes Mexico), Russia east of 60 E assigned to Asia, Hawaii to Oceania and the Canary Islands to Africa.
