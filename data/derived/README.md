# data/derived — small derived tables (committed)

Produced by `python -m mshi.run`: the locked build by stages `cosore_annual` and `build_sites` (regenerate
with `make data`), the analysis build by `cosore_annual_analysis` and `build_sites_analysis` (`make analysis`;
see the main README, "Two site builds", and `docs/DECISIONS.md` D-P2-1 to D-P2-3).
Nothing here contains gridded-product values (WorldClim, SoilGrids, MODIS); feature tables are written
to `data/interim/` (gitignored) until the redistribution terms of those products are checked.

| File | Rows | What it is |
|---|---|---|
| `cosore_annual.csv` | 66 | One annual Rs value per COSORE v0.8.0 dataset (port-mean flux integrated to g C m⁻² yr⁻¹; ports with ≥ 150 observation days spanning ≥ 180 days), with each dataset's primary publication and acknowledgment text. |
| `records_v3.parquet` | 4,837 | SRDB records passing the repo filters (4,771) + COSORE sites (66), with QC flags, coordinate-check fields, continent, and per-record site ids for both variants. `srdb_row` is the original row index of `srdb-data.csv`. |
| `sites_v3_qc.parquet` | 971 | Primary site table: coordinate check + QC filters, records merged within 5 km, target = mean log Rs. |
| `sites_v3_repo.parquet` | 1,225 | Sensitivity site table: repo filters + coordinate check only. |
| `cosore_annual_analysis.csv` | 39 | COSORE for v3's own analyses (author's decision Q-6): untreated soil-respiration ports only, with ≥ 150 observation days spanning ≥ 180 days and ≥ 5 observation days in every calendar month; the annual value is the mean of the 12 monthly means of daily means (`rs_annual`), the handoff-style mean of all observations next to it (`rs_annual_obs_mean`); primary publication and acknowledgment as above. |
| `records_analysis.parquet` | 4,810 | The analysis build's records: the same 4,771 SRDB records + 39 COSORE sites, geodesic coordinate check, `continent_geo` (geographic continent) next to the locked `continent`, per-record site ids for both variants. |
| `sites_analysis_qc.parquet` | 965 | Analysis site table (primary): as `sites_v3_qc` but from the analysis records; site ids `v3aqc_*`. |
| `sites_analysis_repo.parquet` | 1,221 | Analysis site table (sensitivity): repo filters + coordinate check; site ids `v3arepo_*`. |

## Sources, licences and attribution

**SRDB v5** — Jian et al. 2021, *Earth System Science Data* 13:255, doi:10.5194/essd-13-255-2021
(citation as given in the v3 brief; full bibliographic details to be confirmed on Crossref, which is not
reachable from the build environment `[UNVERIFIED]`).
Data from GitHub `bpbond/srdb` at commit `02163a720bc0b84bd535ad0962c85735816448e8` (`srdb-data.csv`,
SHA-256 `c4d7714a…2911`). Licence: MIT. Notice:

> MIT License. Copyright (c) 2018 Ben Bond-Lamberty. Permission is hereby granted, free of charge, to any
> person obtaining a copy of this software and associated documentation files (the "Software"), to deal in
> the Software without restriction, including without limitation the rights to use, copy, modify, merge,
> publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the
> Software is furnished to do so, subject to the following conditions: The above copyright notice and this
> permission notice shall be included in all copies or substantial portions of the Software.
> THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT
> LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO
> EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
> IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE
> USE OR OTHER DEALINGS IN THE SOFTWARE.

(Full text: `LICENSE` in the SRDB repository at the commit above; SHA-256 `64bd84a5…d971`.)

**COSORE v0.8.0** — Bond-Lamberty et al. 2020, *Global Change Biology* 26:7268, doi:10.1111/gcb.15353
(as given in the v3 brief; details `[UNVERIFIED]` on Crossref from this environment). Data from GitHub `bpbond/cosore` at commit
`02f32e8e7f9a0f1c26c9dad61c574aef863f1df1`. **Licence: Creative Commons Attribution 4.0 International
(CC-BY-4.0)** — the repository's `LICENSE` at that commit (SHA-256 `d60376da…5df7`); its README states
"Only free use data (CC BY 4) accepted". (The v3 task brief said MIT; that is incorrect for COSORE.)
COSORE asks that each dataset's primary publication be cited when its data are used: see the
`primary_publication` column of `cosore_annual.csv` (50 of the 66 datasets list one) and of
`cosore_annual_analysis.csv` (27 of 39).
Changes made: in `cosore_annual.csv`, per-port fluxes were integrated to annual values and averaged per
dataset; in `cosore_annual_analysis.csv`, only untreated soil-respiration ports with full-year coverage were
kept, fluxes were clipped to the handoff's range, and each port's annual value is the mean of its 12 monthly
means of daily means, averaged per dataset (see `mshi/data/cosore.py`). Licence text:
https://creativecommons.org/licenses/by/4.0/

**Natural Earth v5.1.2** (public domain) — country polygons used for the coordinate check and continent
assignment, and the 1:50m admin-0 map subunits used for the geographic continent `continent_geo` of the
analysis build (`nvkelso/natural-earth-vector` commit `f1890d9f…`).
