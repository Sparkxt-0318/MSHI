| Quantity | Handoff | v3 | Tolerance | Status | Note |
|---|---|---|---|---|---|
| COSORE sites with an annual value | 66 | 66 | exact | PASS |  |
| SRDB records after repo filters | 4,771 | 4,771 | exact | PASS |  |
| Records after coordinate check | 4,781 | 4,781 | ±1% | PASS |  |
| Records after QC | 3,694 | 3,694 | ±1% | PASS |  |
| QC removals: f_method | 450 | 450 | ±2% | PASS |  |
| QC removals: f_quality | 260 | 260 | ±2% | PASS |  |
| QC removals: f_coverage | 252 | 252 | ±2% | PASS |  |
| QC removals: f_ecosys | 243 | 243 | ±2% | PASS |  |
| QC removals: f_dup | 57 | 57 | ±2% | PASS |  |
| QC sites: Asia | 387 | 387 | ±2% | PASS |  |
| QC sites: North America | 257 | 257 | ±2% | PASS |  |
| QC sites: Europe | 236 | 236 | ±2% | PASS |  |
| QC sites: South America | 42 | 42 | ±2% | PASS |  |
| QC sites: Africa | 26 | 26 | ±2% | PASS |  |
| QC sites: Oceania | 23 | 23 | ±2% | PASS |  |
| QC sites: total | 971 | 971 | ±2% | PASS |  |
| Repo-filter sites: total | 1,225 | 1,225 | ±2% | PASS |  |
| Locked test: selected model | OLS-TP | — | same model | NOT RUN | fetch_worldclim: blocked by network policy (geodata.ucdavis.edu) |
| Locked test: Asia spatial-CV R² | 0.143 | — | ±0.01 | NOT RUN | fetch_worldclim: blocked by network policy (geodata.ucdavis.edu) |
| Locked test: Europe n | 235 | — | exact | NOT RUN | fetch_worldclim: blocked by network policy (geodata.ucdavis.edu) |
| Locked test: Europe R² | 0.079 | — | ±0.01 | NOT RUN | fetch_worldclim: blocked by network policy (geodata.ucdavis.edu) |
| Locked test: site-bootstrap CI low | 0.013 | — | ±0.01 | NOT RUN | fetch_worldclim: blocked by network policy (geodata.ucdavis.edu) |
| Locked test: site-bootstrap CI high | 0.125 | — | ±0.01 | NOT RUN | fetch_worldclim: blocked by network policy (geodata.ucdavis.edu) |
| Locked test: re-run identical to the locked result | identical | — | 1e-9 | NOT RUN | fetch_worldclim: blocked by network policy (geodata.ucdavis.edu) |
| NPP r vs committed NPP (original 889 sites) | 0.982 | — | ±0.01 | NOT RUN | modis_points: blocked by network policy (planetarycomputer.microsoft.com) |
| Original sites with NPP missing in the committed tables but present in v3 | 189 | — | none given | NOT RUN | modis_points: blocked by network policy (planetarycomputer.microsoft.com) |

PASS/FAIL: within/outside the tolerance in configs/v3.yaml. NOT RUN: no current result (reason in the note). STALE: produced by a different config or code. DEVIATION: the locked-test re-run differs from the locked result, which stays primary. INFO: no tolerance given in the brief.
