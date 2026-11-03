## [data-build] data-build-01 — finder high / bug → VERDICT confirmed / high
**Natural Earth CONTINENT puts two French Guiana (Paracou) sites and two Canary Island sites into the locked 'Europe' test set** (build_sites_v3.py 43-54 (continent = NE CONTINENT of the containing country); consumed at clean_test.py:44 (d.continent == 'Europe'))

DESCRIPTION: Continent comes from the CONTINENT attribute of the country polygon that contains the point. In NE admin-0, France (which includes French Guiana) and Spain (which includes the Canaries) are both 'Europe'. In the rebuilt QC site table, 4 of the 236 'Europe' sites lie outside Europe:
- v3qc_00091 (5.03N, -53.00W; SRDB row 910, Paracou; log Rs 7.562)
- v3qc_00185 (5.282N, -52.912W; row 2075, Paracou; log Rs 7.153)
- two Tenerife forest sites (28.29N, -16.63W; 28.31N, -16.57W)

The repo-filter table has 5 such sites; the fifth is a 20-record Gran Canaria site. clean_test.py scores every site with continent == 'Europe', so two tropical-rainforest sites count as European test sites. The Paracou sites are the warmest and highest-Rs points in the test set (Europe mean log Rs 6.47, SD 0.56), and the Asia model also predicts them high, so they are high-leverage points that add explained variance.

The same mechanism makes 'North America' include 30 QC sites south of 24N (tropical Mexico, Central America, Caribbean, plus 5 in Hawaii). That matters when reading E4/E4b ('NA outside the CONUS box R2 0.51').

EVIDENCE: Rebuilt the record and site tables with a byte-identical copy of build_sites_v3.py (sha256 1d1f3c5d...) and my replica COSORE CSV. The output matches build_summary.json on every key. Scripts are in docs/review/2026-11-02/critique_scripts/data-build/scripts/.

- geo_diag.py lists the out-of-Europe 'Europe' sites.
- fg_influence.py refits the Asia OLS-TP (n=383; bio01/bio12 borrowed from the nearest original repo site; this approximation reproduces N2b to within 0.001). Paracou predictions are 7.010 and 7.078 against observed 7.562 and 7.153. Reconstructing SSE/SST from the locked JSON (n=235, R2 0.079) and E6 (RMSE 0.535 log) and removing the two Paracou sites gives R2 of about 0.062. So about 0.017, roughly 22% of the headline R2, comes from two South American sites.
- europe_proxy.py re-scores Europe using SRDB-reported MAT/MAP as the climate proxy (r = 0.94 / 0.90 with WorldClim at 613 repo sites; n = 183): R2 0.127 [0.052, 0.179] as built, 0.108 [0.030, 0.154] without Paracou, 0.104 [0.032, 0.150] without all four.

Applied to the locked CI [0.013, 0.125], a shift of this size would likely put the lower bound at about 0. This is an estimate: WorldClim is unavailable. Both Paracou points are inland, so they are presumably among the 235 scored sites.

AFFECTED: - clean_test_europe.json: Europe R2 0.079 [0.013, 0.125] and the H1 verdict; also AOA H2 counts.
- clean_test_europe_repo_sensitivity.json: n=282 includes 5 non-European sites.
- E6 matrix: every Europe row/column, including within-Europe CV 0.058 and LOCO.
- build_summary.json and the PROMPT section 4 continent reproduction targets.
- Interpretation of E4/E4b for the North America test sets.

FIX: Do not silently change the locked result (rule 4). Report a declared deviation/sensitivity: 'Europe excluding sites outside geographic Europe' (at minimum French Guiana; state the Canary Islands decision), and disclose it in the paper.

For all other analyses, assign continents geographically:
- override overseas territories (French Guiana -> South America; Canaries -> Africa or flagged; Hawaii flagged), or use NE map_units/subunits with an explicit override table;
- add a regression test that every site of a continent lies inside a sanity box for it (e.g. Europe lon -32..70, lat 34..82).

VERIFIER: Confirmed independently. build_sites_v3.py:43-51 takes CONTINENT from the NE admin-0 polygon that contains the point. France and Spain are CONTINENT='Europe' in ne_50m. clean_test.py:44 scores everything with continent=='Europe'.

In the rebuilt QC table, 4 of 236 'Europe' sites are outside geographic Europe: 2 in French Guiana (Paracou) and 2 on Tenerife. The repo table adds a 20-record Gran Canaria site, making 5. Both Paracou points are inland (11.6 and 37.5 km), so WorldClim is valid there and they are almost certainly among the 235 scored sites. The unscored 236th site is probably v3qc_00559 (40.0N, 3.6E), which is 20.8 km offshore.

Impact on the headline R2 (0.079):
- Removing the two French Guiana sites gives about 0.060-0.063. I estimated this with two independent Asia-model proxies and a grid of plausible Paracou climates.
- Removing all four non-European sites gives about 0.058.
- So roughly 20-24% of the R2 comes from two South American rainforest sites.
- The proxy re-score shows the CI lower bound moving by about -0.022. Applied to 0.013, H1 would likely fail in a sensitivity analysis (an estimate; WorldClim is unavailable). The 2-degree block CI already includes 0 as built.
- This is a referee-level objection to the main confirmatory test, so high severity stands.

Corrections to the finding:
1. This is not a code deviation. The code implements the locked plan's continent rule ('Natural Earth 1:50m point-in-polygon') exactly. It is a construct-validity flaw in the plan itself. The right remedy is the suggested declared sensitivity analysis, not changing the locked result.
2. The Paracou sites are 'among the highest' Rs in the set (ranks 2 and 22 of 236), not 'the highest'.
3. Of the 30 QC 'North America' sites south of 24N, only the 5 Hawaii sites come from the same overseas-territory mechanism. Panama, Costa Rica, Mexico and Puerto Rico are conventionally North America.
4. E4/E4b use the repo table, not the QC table. There, 41 of the 88 NA sites outside the US box lie south of 24N (9 in Hawaii). That is a caveat on how to read 'R2 0.51', not a bug.
5. The claimed effect on the AOA counts is not established.

VERIFIER EVIDENCE: Scripts are in docs/review/2026-11-02/critique_scripts/verify-data-build/scripts/.

Rebuild:
- Ran a copy of cosore_aggregate.py with only the 2 path constants changed (66 sites).
- Ran a byte-identical build_sites_v3.py (sha256 1d1f3c5d...) on SRDB c4d7714a.
- The output build_summary.json matches the handoff on every key.

v01_geo.py:
- NE CONTINENT: France = Europe, Spain = Europe.
- QC Europe sites outside lon -32..70 / lat 34..82:
  - v3qc_00091 (5.03, -53.00; srdb row 910, Paracou; y 7.562; rank 2 of 236)
  - v3qc_00185 (5.282, -52.912; row 2075; y 7.153; rank 22)
  - v3qc_00270 (28.292, -16.629; y 6.582)
  - v3qc_00423 (28.306, -16.568; y 5.752)
- Repo table adds v3repo_00540 (28.1, -15.4; 20 records; 0.4 km offshore).
- Europe mean 6.472, SD 0.557.
- QC NA sites south of 24N: 30 (Panama 13, Mexico 5, USA/Hawaii 5, Costa Rica 4, Puerto Rico 3). Repo table: 41.

v01_influence.py:
- SSE = 235 x 0.535^2 = 67.26; SST = 73.03 (var 0.3108, vs 0.3101 for the rebuilt 236 sites).
- Asia OLS-TP proxies:
  - (a) WorldClim borrowed from the nearest repo site within 10 km: n 383, a 4.573, bT 0.0163, blnP 0.260
  - (b) SRDB MAT/MAP: n 312, a 4.399, bT 0.0109, blnP 0.298
- Grid T 25.5-27 C x P 2200-3200 mm gives Paracou predictions 6.97-7.11 and R2 without French Guiana 0.060-0.063.
- Without all 4 non-European sites: 0.058.
- With perfect predictions at Paracou: 0.058.
- Break-even would need a Paracou residual sum of squares of at least 1.53.

v01_proxy_ci.py (SRDB MAT/MAP proxy, same bootstrap as clean_test):
- As built: 0.127 [0.052, 0.179]
- Without French Guiana: 0.108 [0.030, 0.154]
- Without all 4: 0.104 [0.032, 0.150]

E6 Asia->Europe has the same n=235 and R2 0.079 as the locked test, so it is the same scored set.


## [data-build] data-build-02 — finder medium / spec-deviation → VERDICT confirmed / medium
**COSORE site 'Rs' averages heterotrophic (Rh), transparent-chamber NEE and manipulated ports; 3 sites have no Rs/control port at all** (cosore_aggregate.py 59 (keeps only PORT/TIMESTAMP/FLUX), 70-86 (all ports integrated), 123 (site = mean over ports); PORTS.txt is never read)

DESCRIPTION: integrate_dataset averages every port that meets the day rules. It never reads PORTS.txt, whose CSR_MSMT_VAR (Rs/Rh/NEE/Reco) and CSR_TREATMENT columns identify trenched, girdled and root-exclusion (Rh) ports, clear-chamber NEE ports, and drought/litter manipulations. SRDB records are restricted to Manipulation None/NA, but COSORE is not.

Of the 308 qualifying ports in the 66 retained datasets, 64 ports in 15 datasets are not untreated Rs.

Three 'Rs' sites have no Rs/untreated port at all:
- d20200109_HIRANO_PDB: Rh only; Indonesia, Asia training set
- d20200328_UEYAMA_HOKUROKU: NEE only; Japan, Asia
- d20200328_UEYAMA_FAIRBANKS: NEE with CSR_OPAQUE=FALSE over Sphagnum/Carex; Alaska

For the other 12, restricting to Rs/None ports changes log Rs by:
- MAURITZ -0.22
- UEYAMA_TESHIO -0.20
- ARAIN_TP39 -0.18
- SCOTT_WKG -0.17
- LIANG -0.12
- BLACK -0.11
- ZHANG_oak +0.11
- ZHANG_maple +0.08
- others smaller

EVIDENCE: cosore_replica.py repeats the handoff logic and reproduces exactly 66 sites. cosore_diag.py parses PORTS.txt with the csv module, joins by port (falling back to port 0) and compares site means using all ports vs Rs/None ports only. Scripts are in docs/review/2026-11-02/critique_scripts/data-build/scripts/. PORTS.txt for HIRANO_PDB, UEYAMA_* and MAURITZ was inspected directly.

AFFECTED: - COSORE-derived site targets: QC sites containing COSORE records are 10 in Asia, 29 in North America, 5 in Europe.
- Same-site agreement (E1/N3) where COSORE overlaps SRDB.
- Headline sensitivity is small: in an approximate N2b refit the plot-forest coefficient goes 0.125 -> 0.124, and the proxy locked-test R2 changes by +0.002.

FIX: Read PORTS.txt. Keep only ports with CSR_MSMT_VAR == 'Rs' and CSR_TREATMENT == 'None' (and opaque chambers where CSR_OPAQUE is given). Drop datasets with no such port. Log the new COSORE site count as a deviation from the handoff's 66.

VERIFIER: Confirmed. cosore_aggregate.py:59 keeps only PORT, TIMESTAMP and FLUX. Lines 70-86 integrate every port that meets the day rule, line 123 averages them, and PORTS.txt is never read.

- 308 qualifying ports across the 66 datasets.
- 64 ports in 15 datasets are not untreated Rs: 46 Rh (trenched, girdled, root exclusion, trench+warm, None), 14 NEE (4 clear-chamber), 3 manipulated Rs (2 drought, 1 no-litter) and 1 port with no metadata.
- Three datasets have no Rs/None port at all: HIRANO_PDB (all 6 ports Rh), UEYAMA_HOKUROKU (6 NEE, opaque=FALSE) and UEYAMA_FAIRBANKS (3 NEE, opaque=FALSE).
- QC sites containing COSORE records: NA 29, Asia 10, Europe 5, plus 1 Oceania and 1 South America.

Corrections:
1. The per-dataset changes are stated with the wrong sign. Restricting to Rs/None RAISES log Rs at MAURITZ (+0.219), TESHIO, ARAIN_TP39, SCOTT_WKG, LIANG and BLACK, and lowers it at ZHANG_oak and ZHANG_maple. Mixing in Rh ports makes the as-built values too LOW.
2. The suggested '(opaque chambers where CSR_OPAQUE is given)' clause is too strict. 43 of the 52 Rs/None ports that report CSR_OPAQUE say FALSE, and 11 datasets have only such ports. Applied literally, the clause would discard 11 legitimate Rs datasets. Filter on CSR_MSMT_VAR and CSR_TREATMENT only.

The headline effect is small (an approximate N2b refit is shown in the evidence). Medium is right: this is a target-definition and description problem, and it also affects E1/N3.

VERIFIER EVIDENCE: Script: docs/review/2026-11-02/critique_scripts/verify-data-build/scripts/v_cosore_ports.py. It reads data.RDS with rdata 1.1.0 and parses PORTS.txt with the csv module (port row, else the port-0 fallback). Output is in out/cosore/ports_diag.csv; I read it with keep_default_na=False because pandas reads the string 'None' as NaN.

Counts: 308 ports, 64 non-Rs/None, 15 datasets. HIRANO_PDB is in site v3qc_00481 (Asia, 1 of 5 records), HOKUROKU in v3qc_00469 (Asia), FAIRBANKS in v3qc_00097 (NA).

Change in site log Rs when restricting to Rs/None ports (as-built g C -> Rs/None g C):
- MAURITZ: 953.5 -> 1187.1 (+0.219)
- UEYAMA_TESHIO: +0.197
- ARAIN_TP39: +0.183
- SCOTT_WKG: +0.174
- LIANG: +0.117
- BLACK: +0.107
- ZHANG_oak: -0.105
- ZHANG_maple: -0.082
- SAVAGE_hf006-05: +0.044
- DESAI: +0.029
- LIU: +0.017
- SIHI_H2: -0.009

Datasets whose Rs/None ports are all opaque=FALSE: SCOTT_SRM, SCOTT_WHS, SCOTT_WKG, MIAO, JASSAL, CHANG, MATHES, UEYAMA_TESHIO, UEYAMA_YAMASHIRO, ARAIN_TP39, OYONARTE.

v02_n2b_sens.py (approximate N2b, WorldClim borrowed from the nearest repo site; reproduces n 577 vs 578, coefficient 0.1247 vs 0.126, forest share 0.685): the plot-forest coefficient is 0.1277 with Rs/None-only ports, drop-not-clip and the no-Rs datasets removed.


## [data-build] data-build-03 — finder medium / stats-method → VERDICT confirmed / medium
**COSORE 'annual' Rs extrapolates growing-season means to 12 months, weights seasons by sampling density, and clips garbage values instead of dropping them** (cosore_aggregate.py 73-80 (n_days>=150 & span>=180; clip(-2,50); mean of all observations x 31,536,000 s), 123)

DESCRIPTION: Annual Rs is the plain mean of all clipped observations multiplied by one year. A port qualifies with 150 observation days spanning 180 days, so an April-November record counts as 'annual' and its growing-season mean is applied to winter. 23 of 66 sites have no qualifying port covering all 12 calendar months.

In the 26 full-year temperate/boreal COSORE datasets, the mean flux over April-November is 1.32x the 12-month climatological mean (IQR 1.25-1.37), and over May-November 1.41x. Consistent with this, partial-year COSORE sites exceed co-located SRDB records at the same 5-km site by +0.32 log (median +0.37, n=15), against a median of +0.04 for full-year sites (n=29). Worst cases (COSORE vs co-located SRDB, g C):
- ARAIN_TPD 1959 vs 561
- ARAIN_TP74 1460 vs 575
- SIHI_H1 1405 vs 640
- MATHES 1355 vs 681

Even for full-year data, the observation-weighted mean is a median 1.03x the month-balanced mean, and 11 of 43 datasets are above 1.10.

Clipping keeps out-of-range values at the bounds. d20191214_PANG (Asia training site) has a raw mean of -6541 umol m-2 s-1, with about 5% of values above 50 and about 5% below -2. Clipping gives 1308 g C m-2 yr-1; dropping those values gives 544 (+0.88 log). LIU is +0.22.

The docstring says 'multi-year sites are averaged', but the code pools observations across years.

EVIDENCE: Scripts in docs/review/2026-11-02/critique_scripts/data-build/scripts/:
- cosore_monthly.py: monthly climatology of daily means per qualifying port
- cosore_season_bias.py: month-window / 12-month ratios from full-year ports
- cosore_vs_srdb.py: COSORE minus co-located SRDB log Rs on the rebuilt 5-km sites
- cosore_diag.py: clip vs drop means per port

AFFECTED: - COSORE-derived targets, including Asia training sites PANG, LIU and UEYAMA_TESHIO.
- Within-site agreement (E1/N3).
- Downstream sensitivity is small: approximate N2b plot-forest coefficient 0.125 -> 0.127 when partial-year COSORE is dropped; proxy locked-test R2 +0.002 with all COSORE fixes. The issue is method and description, not the headline.

FIX: Integrate per port and year as daily, then monthly, means. Require all 12 months, or gap-fill with a temperature-response model and record the coverage (the analogue of SRDB Annual_coverage). Drop rather than clip implausible values. Average years. Report the change as a deviation.

VERIFIER: Confirmed. A port qualifies with at least 150 observation days spanning at least 180 days (lines 72-75). The annual value is the plain mean of all clipped observations x 378.79 (lines 78-80), pooled across years. That contradicts the docstring (line 13), which says multi-year sites are averaged. Clipping keeps out-of-range values at the bounds.

All numerical claims reproduce:
- 23 of 66 sites have no qualifying port that covers all 12 calendar months. Many cover only Apr-Nov.
- The Apr-Nov / 12-month flux ratio and the 26-dataset count reproduce exactly once 'temperate/boreal' is taken as |lat| >= 35. With |lat| >= 23.5 the ratio is slightly lower but the conclusion is the same.
- The co-located SRDB comparison, the four worst cases, the 1.03x / 11-of-43 obs-weighting result and the PANG and LIU clipping effects all match.

Nuance: full-year sites also exceed co-located SRDB on average (mean +0.16 log, median +0.04). The contrast between partial-year and full-year sites is therefore smaller in means than in medians, and the comparison is confounded by different plots, years and methods. The seasonal-ratio evidence is the stronger argument.

The headline effect is small. This is a methods and description problem plus secondary targets (E1/N3), so medium is right.

VERIFIER EVIDENCE: Scripts in docs/review/2026-11-02/critique_scripts/verify-data-build/scripts/.

v03_season.py:
- 23 of 66 sites are partial-year (month lists printed). Examples: SAVAGE_hf006-05, SIHI_H1/H2, PANG, MATHES and ARAIN_TP74 cover months 4-11 only; SZUTU_TONZI covers 1, 2, 10-12.
- Full-year ports with |lat| >= 35: 26 datasets, Apr-Nov ratio median 1.321 (IQR 1.254-1.375).
- Full-year ports with |lat| >= 23.5: 38 datasets, median 1.294 (IQR 1.159-1.347). May-Nov median 1.389.
- 43 full-year datasets: obs-weighted / month-balanced mean median 1.029; 11 are above 1.10 and 2 below 0.90.
- PANG: raw mean -6540.6 umol; 4.7% of values above 50 and 6.0% below -2. Clipped 1308.0 vs dropped 544.2 g C (+0.877 log). LIU: +0.215.
- 63 datasets have ports spanning more than one calendar year.

v03_vs_srdb.py (repo table):
- Partial-year COSORE sites vs co-located SRDB: n=15, mean +0.314, median +0.366.
- Full-year: n=29, median +0.039, mean +0.158.
- Worst cases: ARAIN_TPD 1958.5 vs 561.1; TP74 1459.8 vs 575.4; SIHI_H1 1404.6 vs 640.2; MATHES 1354.9 vs 680.5 g C.

v02_n2b_sens.py: approximate N2b plot-forest coefficient goes 0.1247 -> 0.1269 with all COSORE fixes, including dropping partial-year datasets.


## [data-build] data-build-04 — finder medium / spec-deviation → VERDICT confirmed / medium
**Coordinate check measures '100 km' in Web Mercator, and over half of its 52 'coordinate errors' are correct coordinates with a wrong Country label** (build_sites_v3.py 57-63 (alias table; line 62 'Congo' -> Republic of the Congo), 67-77 (distance in EPSG:3857, >100 km rule))

DESCRIPTION: (a) Distances are computed in EPSG:3857, which inflates them by about sec(lat). The effective threshold is therefore about 100*cos(lat) km: 84 km at 33N and 50 km at 60N. The locked plan says '> 100 km'. With geodesic distances, 42 of 138 checkable mismatches are flagged instead of 52. The 10 that flip:
- 6 'Siwaliks, Haryana' records at (33.0, 73.0): 95.6 km true
- 1 Guangxi record: 96.0 km
- 3 Malta records reported as Italy: about 98 km

(b) 28 of the 52 flagged records lie where their own SRDB Site_name/Region places them; the error is in the Country field:
- Yangambi/Tshopo, DRC, reported as 'Congo' (6; the alias maps 'Congo' to the Republic of the Congo)
- Nantou County, Taiwan, reported as 'China' (4)
- Kailaqi Forest/Genhe, Inner Mongolia, reported as 'Mongolia' (7)
- Xrobb l-Ghagin, Malta, reported as 'Italy' (3)
- La Foa River, New Caledonia, reported as 'New Zealand' (3)
- Elva and Rouge, Estonia, reported as 'Norway' (2)
- Sarawak reported as 'Indonesia' (2)
- Catchacoma, Ontario, reported as 'USA' (1)

Only 24 are true coordinate errors (sign, lat/lon swap, digit typo). The 6 Siwaliks records really are misplaced (Haryana is about 500 km away) but are caught only because of the Mercator inflation.

EVIDENCE: coord_diag.py recomputes the distance to the reported-country polygon in a local azimuthal-equidistant projection centred on each point. Site_name/Region for all 52 flagged records come from srdb-data.csv. The script is in docs/review/2026-11-02/critique_scripts/data-build/scripts/.

AFFECTED: - Reproduction targets: coord_mismatch_records 52 and records_after_coord_check 4,781.
- Site counts: Europe loses Malta and Elva/Rouge (up to 3 sites); Asia loses Genhe, Nantou and Sarawak; Africa (n=26) loses 2 DRC sites; Oceania loses La Foa.
- The methods wording ('coordinate errors').

FIX: - Compute geodesic distance (local AEQD, or pyproj.Geod to the nearest boundary point).
- Describe the rule as 'reported-country mismatch > 100 km'.
- Fix the 'Congo' alias (it is ambiguous; check against both Congos) and decide explicitly how to treat label-only mismatches (Taiwan/China, Inner Mongolia/Mongolia, Malta/Italy).
- Log the resulting counts (42 flagged under the literal rule) as a deviation.

VERIFIER: Confirmed. Lines 67-73 measure distance in EPSG:3857, which inflates it by about sec(lat). Recomputed geodesically, 42 records are flagged instead of 52, and the 10 that flip are exactly the ones listed. 28 of the 52 flagged records sit where their own SRDB Site_name/Region puts them (label-only errors); 24 are real coordinate errors. The 'Congo' alias (line 62) maps the Yangambi (DRC) records to the Republic of the Congo.

The stated site-count impact is overstated for the primary QC table. The DRC records (6, alkali method), Genhe (7, coverage) and Siwaliks (6, method) are removed by QC anyway. Rebuilding with geodesic distance and keeping label-only records changes QC sites by Europe +3, Asia +1, NA +1, Oceania +1 and Africa 0. The Africa and Genhe losses apply only to the repo-filter table.

One point the finding misses: Malta lies 98 km from Italy, so under the locked plan's literal '>100 km' rule it should not have been dropped. The locked Europe set is therefore one site off its own plan, and prep_log 13 'Deviation from plan: none' is not strictly true.

The headline is essentially unaffected, but the reproduction targets and the methods wording ('coordinate errors') change. Medium, at the low end.

VERIFIER EVIDENCE: Scripts in docs/review/2026-11-02/critique_scripts/verify-data-build/scripts/.

v04_coord.py (distance to the reported-country polygon in a local AEQD projection centred on each point; polygon clipped to +/-20 deg):
- 138 checkable mismatches: 52 flagged with Mercator, 42 with geodesic distance > 100 km (non-territory), 0 flagged only by geodesic distance.
- Mercator/geodesic ratio averages 1.006 x sec(lat).
- The 10 flips: 6 Siwaliks/Haryana at (33.0, 73.0), 95.6 km; 1 Shi Kang/Guangxi at (21.744, 104.314), 96.0 km; 3 Xrobb l-Ghagin/Malta, 98.0-98.2 km.
- Label-only groups (from Site_name/Region in srdb-data.csv): Congo->DRC (Yangambi/Tshopo) 6, China->Taiwan (Nantou) 4, Mongolia->China (Kailaqi/Genhe) 7, Italy->Malta 3, NZ->New Caledonia (La Foa) 3, Norway->Estonia (Elva, Rouge) 2, Indonesia->Malaysia (Sarawak) 2, USA->Canada (Catchacoma) 1. Total 28.

QC flags of the flagged records: DRC = method, Genhe = coverage, Siwaliks = method.

v04_sites.py:
- As built: 4781 / 3694 records; Asia 387, NA 257, Europe 236, SA 42, Africa 26, Oceania 23.
- Geodesic rule: 4791 / 3698 records; Asia 388, Europe 237.
- Geodesic + keep label-only: 4816 / 3710 records; Asia 388, NA 258, Europe 239, Africa 26, Oceania 24.


## [data-build] data-build-05 — finder medium / bug → VERDICT confirmed / medium
**NPP window means are diluted by zeros where the 0.05 deg window crosses a MODIS tile edge (up to 50%, or NPP = 0 instead of NaN)** (modis_points_lst.py 47-55 (line 50: boundless=True, fill_value=0; line 52: NPP valid if 0 <= a <= 32700))

DESCRIPTION: Each window is read only from the tile that contains the site, with boundless=True and fill_value=0. For NPP the validity test (0 <= a <= 32700) accepts the fill, so every out-of-tile pixel counts as NPP = 0. LST is unaffected because the a > 0 test excludes the fill.

Emulating the exact window geometry (rasterio from_bounds plus round_offsets/round_lengths) for all v3 sites: 21 QC sites (11 Asia, 6 North America, 4 Europe) have NPP windows partly outside their tile, 11 of them by at least 25%. Eight are exactly 50% outside because round-degree latitudes sit on tile rows, e.g. (40.0, 115.0), (30.0, 102.0), (30.0, 101.83), (40.0, -105.5), (40.0, 140.56), (10.0, 78.167), (40.0, -3.5), (40.0, 3.6).

Where the in-tile pixels are masked fill (water/urban), the site gets NPP = 0 instead of NaN and stays in NPP models; (40.0, 3.6) is a point at sea.

EVIDENCE: Scripts in docs/review/2026-11-02/critique_scripts/data-build/scripts/:
- modis_edges.py emulates the tile choice and window and counts out-of-tile pixels for every v3 site.
- boundless_test.py builds a synthetic 2400x2400 sinusoidal tile (h26 v04) with constant value 5000 and nodata 32767, then runs the script's read logic for (40.0N, 115.0E). Result: 150 of 300 pixels are 0 and the window mean is 250 g C m-2 yr-1 instead of 500.

AFFECTED: - The npp feature for about 2% of sites.
- C8+NPP / C8+MODIS / ALL candidates in the locked selection table and the secondary Europe scores.
- E2 NPP comparisons and the E3 'NPP slope differs (p = 0.02)'.
- The 'NPP r = 0.982 vs committed' reproduction target.
- The selected OLS-TP model and the N1/N2 pilots (which use the GEE raster) are not affected.

FIX: Read with a nodata fill (fill_value=32767, or masked=True) or mosaic the neighbouring tile(s). Add a regression test with a point exactly on a tile boundary (e.g. 40.0N).

VERIFIER: Confirmed, including the mechanism inside rasterio 1.5.2. With boundless=True and a window, read() always goes through a VRT (_io.pyx:566, 596-614) with nodata = background = fill_value = 0, and the ComplexSource NODATA is also 0 (vrt.py:153, 176-178, 212-214). Out-of-tile pixels therefore come back as 0 and pass the NPP test 0 <= a <= 32700 (modis_points_lst.py:52).

In-tile 32767 fill stays 32767 and is excluded, so only the out-of-tile part is wrong. LST is unaffected because its test is a > 0.

The counts match exactly: 21 QC sites (Asia 11, NA 6, Europe 4), 11 of them at least 25% outside the tile and 8 exactly 50%, at the listed round-degree coordinates.

New point: the 'NPP r = 0.982' reproduction target partly bakes in this bug. If the bug were the only difference, r would be about 0.993 on the original sites, so fixing it could move r by up to ~+0.007.

Caveat: the (40.0, 3.6) example is 20.8 km offshore. Its WorldClim values are probably NaN, so it is likely dropped from every model (it is probably the unscored 236th Europe site). 'Stays in NPP models' is not shown for that site.

The effect on E2/E3 (NPP slope p = 0.02) cannot be quantified here. The selected OLS-TP model and N1/N2 are unaffected. Medium, because it changes secondary numbers.

VERIFIER EVIDENCE: Scripts in docs/review/2026-11-02/critique_scripts/verify-data-build/scripts/.

Read the rasterio 1.5.2 source: _io.pyx lines 566-614 and vrt.py _boundless_vrt_doc.

v05_modis.py, part 1: the script's h/v formula plus rasterio from_bounds().round_offsets().round_lengths() on the standard 2400x2400 tile transform, for every site.
- QC: 21 sites partly outside (2.2%); 11 at least 25%; 8 exactly 50%: v3qc_00731 (40, -105.5), 00842 (40, 115), 00398 (30, 102), 00375 (40, 140.56), 00372 (10, 78.167), 00586 (40, -3.5), 00593 (30, 101.83), 00559 (40, 3.6).
- Repo: 26 / 15 / 11.

v05_modis.py, part 2: synthetic int16 tiles (value 5000, every 7th column 32767 fill, every 11th 32766 water, nodata 32767) read with the exact code from lines 47-55.
- (40.0, 115.0), tile h26v4, window col 1930 / row 2394, 25x12: 150 of 300 pixels are 0, in-tile 32767 kept (18), mean NPP 222 instead of 500.
- (40.0, 3.6): 60 of 120 pixels are 0, mean 206.
- Interior control (45.3, 7.5): 0 zeros, mean 500.

v05_orig.py: 23 of the original 889 sites are partly outside the tile (13 by at least 25%). Simulated r(committed NPP, committed x (1 - frac_out)) = 0.993 (n=689).


## [data-build] data-build-06 — finder low / bug → VERDICT confirmed / low
**Projected-corner bounding box makes the MODIS 'window' 1-9x wider than 0.05 deg, systematically more so in East Asia and western North America than in Europe** (modis_points_lst.py 47-49)

DESCRIPTION: The four corners of a +/-0.025 deg lon/lat box are projected to sinusoidal and replaced by their axis-aligned bounding box. In sinusoidal coordinates that box is a parallelogram sheared by about R*|lon|*sin(lat)*0.05 deg, so the window's east-west extent grows with |lon|*tan(lat).

Across QC sites the east-west extent relative to nominal has median:
- Europe 1.20x
- Africa 1.03x
- South America 1.24x
- Asia 2.22x (max 5.9x)
- North America 2.29x (max 9.1x)
- Oceania 2.75x

For example, (40.0N, 140.56E) reads 28x12 500-m pixels while (40.0N, 3.5W) reads 10x12. NPP/LST spatial support therefore differs by continent, which is a small feature-definition shift in a transfer study.

EVIDENCE: modis_edges.py and the inline check (window x-extent divided by 0.05 deg * cos(lat)) for every QC site; boundless_test.py shows width=25 columns at (40N, 115E) against about 9 nominal. Scripts are in docs/review/2026-11-02/critique_scripts/data-build/scripts/.

AFFECTED: NPP/LST features (MODIS candidates, E2/E3) and the README/plan description '0.05 deg window mean'. Not the OLS-TP headline.

FIX: Define the window in the tile's pixel grid around the projected point (fixed +/-N pixels in x and y), or reproject or warp to EPSG:4326 at 0.05 deg before averaging. Describe the support accurately.

VERIFIER: Confirmed. Lines 47-49 project the 4 corners of a +/-0.025 deg box and take their axis-aligned bounding box in sinusoidal coordinates. The east-west extent therefore grows by about |lon_rad|*tan(lat), while the north-south extent stays correct (12 pixels of 463 m = 0.05 deg). The per-continent medians and maxima match the finding to within rounding, and the two quoted examples are exactly right.

The spatial support of the MODIS features differs by region and does not match the '0.05 deg window' description. The effect on smooth NPP/LST fields is probably small, and the headline is not affected. Low is right.

VERIFIER EVIDENCE: v05_modis.py in docs/review/2026-11-02/critique_scripts/verify-data-build/scripts/. For every QC site: window width in pixels divided by the nominal 0.05 deg x cos(lat) x R / 463.3 m.

Median (max) by continent:
- Africa: 1.01 (1.29)
- Europe: 1.21 (2.44)
- South America: 1.21 (2.26)
- Asia: 2.22 (5.86)
- North America: 2.27 (9.10)
- Oceania: 2.70 (3.91)

Examples: v3qc_00375 (40.0, 140.56) reads 28x12 pixels and v3qc_00586 (40.0, -3.5) reads 10x12. The synthetic read at (40, 115) uses 25 columns against a nominal of about 9.2.


## [data-build] data-build-07 — finder low / doc-mismatch → VERDICT confirmed / low
**'24 RDS files can't be read by rdata' is wrong: 0 parse failures, 6 datasets with no data.RDS in the git tree, 18 with no qualifying port** (cosore_aggregate.py 87-88 (no qualifying port returns None), 113-117 (None counted as 'RDS unreadable'), 124-127 (out-of-range counted as 'no qualifying port'))

DESCRIPTION: With rdata 1.1.0, every data.RDS present in the v0.8.0 checkout parses. Of the 91 non-TEST datasets:
- 66 retained
- 6 have no data/ directory in the git tree at commit 02f32e8 (d20190526_MINIONS_BNZ, d20190619_GU, d20200109_KISHIMOTO-MO, d20200304_GALVAGNO, d20200304_ZANCHI, d20201013_LIANG)
- 18 parse fine but have no port meeting the 150-day/180-day rule
- 1 (d20200331_PEICHL, 26 g C m-2 yr-1) fails the 50-4500 range

The code returns None both for missing files and for 'no qualifying port', so its counters print '24 unreadable / 1 no qualifying port'. README, prep_log section 9 and the PROMPT section 4 pitfall repeat this. The suggested readRDS workaround would recover nothing.

EVIDENCE: cosore_replica.py records the reason for each skip in out/cosore/cosore_fails.csv. git ls-tree on the COSORE checkout shows no data/ for those 6 datasets. Paths are under docs/review/2026-11-02/critique_scripts/data-build/.

AFFECTED: Methods text, the Phase-1 pitfall list and the planned 'readRDS deviation'. The site count of 66 is unchanged.

FIX: Use separate counters for: file missing, parse error, no qualifying port, out of range. List the 6 missing-data datasets in DECISIONS.md and note that their data are not in the v0.8.0 repository.

VERIFIER: Confirmed. integrate_dataset returns None both on a parse failure and when no port qualifies (lines 87-88). main() counts every None as 'RDS unreadable' (lines 114-117), and an out-of-range site as 'no qualifying port' (lines 124-127).

With rdata 1.1.0 there are 0 parse failures. Of the 24 'unreadable' datasets:
- 6 have no data/ directory in the git tree at 02f32e8.
- 18 parse fine but have no port that meets the 150-day / 180-day rule.
The single 'no qualifying port' case is PEICHL, which fails the 50-4500 g C range check.

The README, prep_log 9 and the PROMPT pitfall all repeat the wrong '24 RDS unreadable' label. A readRDS workaround would recover nothing. The count of 66 sites is unaffected.

VERIFIER EVIDENCE: My copy of the handoff script printed '24 unreadable / 1 no qualifying port' with 66 sites.

v_cosore_ports.py (separate counters for each reason) gives:
- 0 parse errors
- 6 'data.RDS missing': MINIONS_BNZ, GU, KISHIMOTO-MO, GALVAGNO, ZANCHI, d20201013_LIANG
- 18 'parsed OK; no port with >=150 days & >=180-day span'
- d20200331_PEICHL at 26.1 g C
The list is in out/cosore/fails.csv.

'git ls-tree -r HEAD' in the COSORE checkout (02f32e8) lists only ANCILLARY/COLUMNS/CONTRIBUTORS/DESCRIPTION/PORTS for each of the 6 datasets. There are 85 data.RDS files for the 91 non-TEST datasets.


## [data-build] data-build-08 — finder low / doc-mismatch → VERDICT confirmed / low
**QC 'removals' in build_summary are overlapping per-flag counts, and the record counts are not a single sequence** (build_sites_v3.py 107-110)

DESCRIPTION: qc_removed_by counts each flag over the coordinate-checked base (450 / 260 / 252 / 243 / 57, total 1,262), but only 1,087 records are removed (4,781 -> 3,694) because flags overlap. records_after_coord_check (4,781) is larger than srdb_repo_filter_records (4,771) because it adds the 66 COSORE records and removes 52 coordinate-flagged and 4 offland records. The PROMPT section 4 reproduction table presents these as 'QC removals' in a sequence.

EVIDENCE: Rebuilt tables (out/v3) under docs/review/2026-11-02/critique_scripts/data-build/: 4771 + 66 - 52 - 4 = 4781; sum of flags 1262 vs 4781 - 3694 = 1087.

AFFECTED: How the QC is reported in the paper and in the regression-test labels; no numbers change.

FIX: Report a sequential exclusion table (or a flag-overlap/UpSet table), and split the record counts by SRDB vs COSORE.

VERIFIER: Confirmed. Lines 107-110 report qc_removed_by as per-flag counts over the coordinate-checked base, and the flags overlap. records_after_coord_check is SRDB + COSORE - coordinate-flagged - offland. The PROMPT 4 table labels these per-flag counts 'QC removals', which reads as if they were a sequence. No number changes; this is a documentation issue only.

VERIFIER EVIDENCE: From the rebuilt records_v3.parquet:
- 4,837 records = 4,771 SRDB + 66 COSORE.
- f_coord 52, f_offland 4 (all SRDB), no overlap, giving 4,781.
- Per-flag counts 450/260/252/243/57 sum to 1,262, but only 1,087 records are removed (4,781 -> 3,694); 165 records carry 2 or more flags.
- Sequential exclusion in the code's flag order: 450 / 224 / 205 / 195 / 13.


## [data-build] data-build-09 — finder low / stats-method → VERDICT confirmed / low
**Site plot type uses an alphabetical tie-break between mixed records (Agriculture beats Forest, Forest beats Grassland)** (build_sites_v3.py 98 (ecosystem = x.mode().iat[0]))

DESCRIPTION: Series.mode() returns tied values in sorted order and .iat[0] takes the first. In the QC table, 44 sites have tied ecosystem types, for example Forest|Grassland (15 sites, picks Forest) and Agriculture|Forest (8 sites, picks Agriculture). 47 of the 624 sites in the N2 Q1 set contain both forest and non-forest records.

The headline plot-forest share is 0.694 as built. It becomes 0.676 if ties go to non-forest and 0.708 if ties go to forest; the record-weighted mean is 0.687.

The crosswalks from COSORE IGBP strings to classes are re-implemented separately in each experiment script and differ: exp_forest_bias lacks 'Deciduous needleleaf forest', 'Woody savanna', 'Closed shrubland' and 'Croplands'. This has no effect on the current QC table but is fragile.

EVIDENCE: n2_tie.py reproduces N2 Q1 exactly (n=624; plot 0.694, pixel 0.304) from the rebuilt QC sites and the repo GEE IGBP raster, then recomputes the share under the alternative tie rules. site_diag.py tabulates the ties. Scripts are in docs/review/2026-11-02/critique_scripts/data-build/scripts/.

AFFECTED: N2 '68.5% / 69.4% of plots are forest' (range 67.6-70.8%) and the plot-class inputs to N2b-N2d. The direction of the argument is unaffected.

FIX: Make the rule explicit (e.g. record-weighted class fractions, or a documented tie rule). Define a single crosswalk in configs/plot_classes.yaml covering every SRDB and COSORE value, as Phase 3 requires.

VERIFIER: Confirmed. In pandas 3.1, Series.mode() returns tied values in sorted order, so line 98's .iat[0] picks the alphabetically first type: Agriculture beats Forest, and Forest beats Grassland. The tie counts, the N2 Q1 reproduction and the forest share under each alternative tie rule all match the finding exactly.

exp_forest_bias.py:24 omits 'Deciduous needleleaf forest', the only omission that matters for the forest flag. No current QC site has that value, so there is no effect now; the crosswalk is fragile, as stated.

The effect on the N2 headline is about +/-1.5 percentage points and does not change its direction. Low is right.

VERIFIER EVIDENCE: v09_ties.py in docs/review/2026-11-02/critique_scripts/verify-data-build/scripts/.

- Mode demo: pd.Series([...]).mode() returns ['Agriculture', 'Forest', 'Grassland'].
- The site ecosystem recomputed from records matches the rebuilt table exactly.
- 44 QC sites have tied modes: Forest|Grassland 15, Agriculture|Forest 8, Agriculture|Grassland 5, and others.
- N2 Q1 reproduced exactly from the rebuilt QC sites and the repo GEE landcover_igbp_2023.tif: n=624, plot-forest share 0.694.
- 47 Q1 sites contain both forest and non-forest records.
- Forest share: 0.676 if ties go to non-forest, 0.708 if ties go to forest, 0.687 record-weighted.
- Site ecosystem values in the QC table contain no 'Deciduous needleleaf forest', 'Woody savanna', 'Closed shrubland' or 'Croplands'.


### checked_ok for data-build
- Rebuild fidelity: a byte-identical copy of build_sites_v3.py run on SRDB 02163a72, my replica COSORE CSV (66 sites, same logic as cosore_aggregate.py) and NE 5.1.2 reproduces build_summary.json exactly on every key (4,771; 52; 4,781; 3,694; 450/260/252/243/57; 971 = 387/257/236/42/26/23; 1,225).
- SRDB rec_id is assigned before dropna, so it carries the original CSV row index (pitfall handled).
- Manipulation: the only kept strings among in-range records are 'None' (4,751) and blank (20). pandas 3.1 reads both as NaN; no exact 'Control'/'control' exists, so that clause is dead but harmless. Control-like strings that are excluded are negligible ('Ambient CO2' 1, 'No grazing' 2).
- Meas_method regex 'alkali|soda' (case-insensitive) catches 'Alkali absorption' (441) and 'Soda lime' (25); no other alkali/soda-lime spellings exist.
- Quality_flag regex Q1[0-4] matches Q10-Q14, including inside comma lists. Bare 'Q1' (50 records; notes cite figures, i.e. Q01) is correctly not matched. Q13 notes ('May duplicate...') are consistent with dropping Q13.
- Annual_coverage values all lie in 0.01-1 (no percent-scale values); the 488 NaN records are kept, per the spec.
- Duplicate_record links are one-directional (none of the 57 targets carries its own entry), so dropping flagged records keeps one copy.
- Ecosystem filter: SRDB Wetland 225, Urban 19. COSORE CSR_IGBP 'Wetland' uppercases to 'WETLAND', so the filter fires: the 3 COSORE wetland sites (ANJILELI, SIHI_H2wetland, MIAO) are all removed by QC and none survive. 'URB' cannot match 'Urban', but no COSORE dataset is urban.
- COSORE: the unit factor 12.011*31,536,000/1e6 = 378.79 is correct. rdata 1.1.0 returns CSR_TIMESTAMP_BEGIN as float64 epoch seconds, so unit='s' is correct (UTC vs local day boundaries is negligible). The >=150 obs-day and >=180-day span rule is implemented as specified.
- The 50-km nearest-polygon fallback in EPSG:3857 has no effect in this snapshot: a geodesic recheck gives the same 4 offland records, including a lon=193.9 typo.
- Russia split at 60E: 56 records go to Europe and 27 to Asia; there are no Russian records at lon < 0.
- Territory exceptions fire for 24 records, all legitimate: Puerto Rico 14, Svalbard/Adventdalen 6 (SRDB Region 'Greenland'), Greenland 3, New Caledonia 1. Country names not in NE (12 records) are never checked, but all are correctly located (e.g. Lanzhot, 7.7 km from Czechia).
- 5-km connected-component chaining is bounded: 17 QC sites span more than 5 km (max 15.7 km); every record is within 8 km of its site centroid; there are no antimeridian or multi-continent sites.
- site_key (lat/lon rounded to 5 decimals): 971 and 1,225 unique keys with no collisions. N2 Q1 reproduces exactly (n=624, 0.694/0.304) from the rebuilt table, so the feature table rows match the site rows.
- MODIS: the sinusoidal h/v tile formula is correct; NPP x0.1 with codes >= 32761 excluded; LST x0.02 - 273.15 with the 0 fill excluded; the first-composite-per-month selection and the MOD-only prefix filter are correct; LST tile-edge windows (19 sites) only lose pixels, with no bias.
- SoilGrids scale factors are correct (soc/10, nitrogen/100, phh2o/10, clay/sand/silt/10, bdod/100, cec/10). SCALESIZE 7200x2774 over -180..180 / -56..82.7 gives exactly 0.05 deg; treating zero as missing is a harmless safety net.
- COSORE/SRDB label mixing: all 17 site modes that are COSORE IGBP strings are mapped by the N2 crosswalks in exp_plot_pixel, exp_forest_bias and exp_poststrat.
- N2b sanity check: with climate borrowed from the original repo tables, the rebuilt QC sites give n=577, plot-forest share 0.685 and coefficient 0.125 [0.007, 0.246], against the handoff's 578, 0.685 and 0.126 [0.009, 0.244]. This supports the proxy estimates used in data-build-01/02/03.


## [locked-test] locked-test-europe-not-untouched — finder medium / claim-unsupported → VERDICT confirmed / medium
**About 13% of the 'untouched' Europe test sites were training and held-out CV sites in earlier work** (ANALYSIS_PLAN_LOCKED.md; prep_log.md; PROMPT_mshi_v3.md (evidence: scripts/reproduce.py; original repo scripts/task2_sweep.py) plan L3, L7-8; prep_log L157; PROMPT L19; reproduce.py L80-82; repo HEAD a809a97 task2_sweep.py L84, item1_c2_train_fnpp.py L70, item1_c3_train_full_modis.py L99)

DESCRIPTION: The plan (L3, L7-8), prep_log section 10 (L157) and the PROMPT (L19) say Europe was never used to score any model. That is not true. The original 'Asia' bounding box (25-180E) contained European sites. 30 of the 235 locked-test Europe sites are in the original Asia-box training tables. Those rows were (a) training data for the original models, whose feature set (C8 = 'F') and XGB parameters were carried into the locked candidate set, and (b) held-out validation sites in 5-degree spatial-block CV, both in the original repo and in the audit's own reproduce.py run before the lock. The audit used that CV to argue 'Asia-only selection would have picked Full+MODIS' (prep_log L69). This is literally 'a model trained on Asia(-box) sites scored on European sites' before the lock. The information that leaked is small, because no Europe-specific score was reported, and the locked selection rule is mechanical. But the 'untouched' claim as written is false, and a referee who reads the original repo's box definition will find this.

EVIDENCE: I rebuilt the v3 tables with copies of build_sites_v3.py and cosore_aggregate.py (66 COSORE sites). build_summary matched the handoff exactly (4,771/4,781/3,694 records; QC 971 sites, Asia 387, Europe 236; repo 1,225). I identified the exact locked-test rows: dropping Asia v3qc_00184/00576/00604 and Europe v3qc_00559 reproduces rmse_rs_intercept = 386.9086311104987 to full float precision. Haversine BallTree (scratch scripts overlap.py, overlap2.py): 30 distinct Europe test sites lie within 5 km (29 within 1 km) of 38 rows of both training_features_v2.parquet and training_features_v1_real_c6450a7.parquet (Estonia 13, Finland 8, Russia 7, Latvia 1, Romania 1). All 38 rows are in the F rows (n=600) that reproduce.py scored in 5-fold 5-degree CV (checkpoint1/reproduction.json cv_per_fold), and 25 are in the F+NPP rows. Repo-filter sensitivity: 38 of 284 Europe sites. Scratch dir: docs/review/2026-11-02/critique_scripts/locked-test/

AFFECTED: How the locked test is described (D5: 'one clean test scored once on untouched sites'); plan L3/L7-8, prep_log L157, PROMPT L19. The numbers themselves are unchanged.

FIX: Correct the statement everywhere. Disclose that 30/235 (12.8%) of the Europe test sites were training data and held-out CV sites in the earlier Asia-box work. Add a post-hoc sensitivity, labelled as such, that scores the locked model on the 205 remaining sites with no re-selection. Store a per-site 'previously_used' flag in the rebuilt site table.

VERIFIER: I reproduced every number in this finding on my own, and found one point that makes it stronger. 28 of the test sites contain the identical SRDB record (same row id) that sits in the original Asia-box training tables, so this is the same data, not just nearby sites. The bundle also contradicts itself: prep_log L78/L84 and checkpoint1/site_geography.json already say the 25-180E 'Asia' box held 65 European sites (Estonia 21, Finland 12, Romania 3, all of Russia). Yet plan L3, L7-8, prep_log L157 and PROMPT L19 say Europe was never used to score anything. The original CV code (task2_sweep.py L84 at a809a97 on the v1 table, item1_c2_train_fnpp.py L70, item1_c3_train_full_modis.py L99, and the audit's reproduce.py L81, which ran before the lock) applies no region filter. In k-fold CV every complete row is held out exactly once, so all of these European rows were scored as held-out sites. Those fold scores fed the audit's 'Asia-only selection would have picked Full+MODIS' argument (prep_log L69). The severity should stay medium, not high. No Europe-specific score was ever computed. The locked model trains only on v3 continent==Asia, which excludes these sites. Selection was mechanical. So no reported number changes, but the word 'untouched' is false and must be corrected. 7 of the 30 sites are Russia west of 60E, which the original box counted as Asia. The other 23 are in unambiguously European countries.

VERIFIER EVIDENCE: Rebuild: I ran copies of cosore_aggregate.py (paths taken as arguments; 66 sites, 24 RDS files unreadable, 1 with no qualifying port) and build_sites_v3.py. Both are in docs/review/2026-11-02/critique_scripts/verify-locked-test/scripts/. The resulting build_summary.json is identical to the handoff (empty JSON diff). Exact locked rows (find_locked_rows.py): I searched exhaustively over every combination of 1 Europe drop and 3 Asia drops for rmse_rs_intercept. Only Europe v3qc_00559 (40.0N 3.6E, offshore Mallorca) plus Asia v3qc_00184/00576/00604 (Japan/China coastal) gives 386.9086311104987 with diff 0.0. The next-best set is 1.4e-10 away. Overlap (overlap_check.py): 30 of 235 test sites lie within 5 km of 38 rows of both training_features_v2 and v1_real_c6450a7 (29 within 1 km; Estonia 13, Finland 8, Russia 7, Latvia 1, Romania 1). 28 test sites share 30 identical SRDB record ids. I checked that training srdb_<i> equals SRDB CSV row i: max |dlat|, |dlon| and |dRs| are all 0 over 605 rows. All 38 rows are complete for F (BIO + target), 25 are complete for F+NPP, and all 38 rows lie in the Asia box. In the repo-filter variant, 38 of 284 Europe sites overlap.


## [locked-test] locked-test-h1-ci-conditional — finder medium / stats-method → VERDICT confirmed / medium
**H1 passes only under a fixed-model, site-independent bootstrap; the margin is smaller than the training-sample uncertainty** (scripts/clean_test.py L68-77 (boot_ci), L84 (single fit), L90; prep_log L176-177)

DESCRIPTION: H1 is met exactly as the plan specifies: site-bootstrap lower bound 0.0134 > 0. The plan's rule on L45 is followed. However, both CIs resample only Europe sites around a single fit (L84), so they leave out the uncertainty from the Asia training sample. The 2-degree block CI already includes 0. Including training-sample uncertainty would probably erase the 0.013 margin as well. The prep_log wording 'met on the site bootstrap, borderline on the spatial bootstrap' is accurate, but the paper must not present the result as evidence that Asia-trained models have positive skill in Europe without these qualifiers.

EVIDENCE: From the JSON: site CI [0.0134, 0.1254]; 2-degree block CI [-0.0003, 0.1345]. Monte Carlo check (boot_mc.py: boot_ci copied verbatim, exact Europe y, synthetic predictions calibrated to R2 0.079 and RMSE_rs 385.5): the SD of the 2.5% bound over 100 RNG seeds is 0.0020 (site) and 0.0025 (block). The site bound is therefore robustly > 0, and the sign of the block bound is RNG noise. PROXY, not the locked features (proxy_ols.py, proxy_ols_seeds.py): SRDB-reported MAT and ln MAP in place of WorldClim; 310 Asia / 182 Europe sites; proxy Europe R2 0.126. Resampling Asia sites with an OLS refit, on top of resampling Europe sites, lowered the 2.5% bound by 0.025 (seed 42) and 0.031/0.031/0.031 (seeds 1-3) for the site bootstrap, and by 0.020-0.031 for 2-degree blocks. That is about 2x the 0.013 margin, or about 0.022-0.028 after scaling to n=384. Europe has 93 2-degree blocks (33 singletons). These blocks are smaller than the 200-300 km log-Rs correlation range reported in prep_log section 2.

AFFECTED: The H1 verdict and how it is worded (prep_log L177, README L33, PROMPT L19 'Europe R2 = 0.079 [0.013, 0.125]').

FIX: Keep the verdict of the plan written and hashed before scoring, but state that the CI is conditional on the fitted model and assumes independent sites. Add post-hoc intervals, labelled as such: a two-sample bootstrap (resample Asia sites and refit OLS-TP; resample Europe sites) and a 5-degree block bootstrap. Phrase the result as 'small positive R2; lower bound not robust to spatial dependence or training-sample uncertainty'.

VERIFIER: In the code (L84, L90, L68-77), both intervals resample only Europe (y, p) around one fitted model. H1 is met exactly as pre-specified (plan L45 uses the site bootstrap), and the prep_log L177 wording is accurate. The defect is in how PROMPT L19 and README L33 state the result: a bare '[0.013, 0.125]'. I checked the RNG claim with my own calibrated simulation, and it holds. The site lower bound is robustly above 0. The 2-degree block bound of -0.0003 sits inside RNG noise. Two independent proxies support the claim that training-sample uncertainty is about 2x the 0.0134 margin. One of them uses the real WorldClim bio01/bio12 from the original tables. Both are proxies, not the locked features, so 'would probably erase' is well supported but not proven. One sub-point holds only partly. The Europe semivariogram shows much of the dependence within 25 km, though a correlation of about 0.25 remains at 100-300 km. So the '2-degree blocks are smaller than the range' argument is weaker than stated. prep_log L72 had already noted that training and seed uncertainty were not included, but only for the original US CIs. Keep medium.

VERIFIER EVIDENCE: JSON: ci_site [0.01335, 0.12538]; ci_block2 [-0.00026, 0.13448]. rng_mc2.py used synthetic predictions on the exact 235 Europe y, calibrated to R2 0.0790, bias -0.046 and a seed-42 site CI of [0.0155, 0.1248]. Over 100 RNG seeds, the 2.5% bound had SD 0.0022 for the site bootstrap (min 0.0076) and SD 0.0028 for the 2-degree block bootstrap. proxy_boot.py was my own SRDB-reported MAT/ln MAP rebuild: 310 Asia / 182 Europe sites, Europe R2 0.126. The two-sample bootstrap (Asia resampled and OLS refit, plus Europe resampled) lowered the 2.5% bound by 0.031/0.027/0.028/0.026 (site; seeds 42/1/2/3) and by 0.031/0.031/0.026/0.032 (2-degree blocks), replicating the reviewer. wc_analogue.py used real WorldClim from the original v2 tables, OLS bio01+ln bio12, Asia box to US box, n 600/272, R2 0.129. The drop was 0.017-0.025 at n_a=600 and 0.033-0.034 with a resampled training size of 384. Europe has 93 2-degree blocks, 33 of them singletons. eu_semivar.py: semivariance of Europe log Rs is 0.117 at <25 km, 0.23-0.28 at 25-1000 km, and 0.311 total variance.


## [locked-test] locked-test-gC-backtransform-baseline — finder medium / stats-method → VERDICT confirmed / medium
**'No practical gain in g C units' comes from a naive exp() back-transform and an Asia geometric-mean baseline** (scripts/clean_test.py L89-92, L98; prep_log L176-177; README L33)

DESCRIPTION: Three choices drive the g C comparison. (1) The model's prediction is converted to g C as exp(predicted log Rs). That is a median-type estimate, with no smearing. (2) The 'observed' value is exp(site-mean log Rs), which for 135 of 235 sites is a geometric mean of the site's records. (3) The 'constant Asia mean' baseline is exp(mean log Rs) for Asia, i.e. the Asia geometric mean of 723 g C, not the Asia mean Rs of 870 g C. The naive back-transform pulls both model and baseline toward the median. Europe's Rs level is about 11% below Asia's (log difference -0.111). By coincidence, these two offsets put the Asia geometric mean (723) next to Europe's arithmetic mean (743), so the constant looks near-optimal. Meanwhile the model's log-space advantage in level is cancelled by its own downward bias (central prediction exp(6.427) = 618). The statement 'RMSE 385.5 vs 386.9 for the constant Asia mean, no practical gain in g C' is therefore specific to these definitions, and 'Asia mean' is mislabelled. Separately, the plan asks for MAE with the intercept baseline (L44), but the code computes the baseline only for RMSE.

EVIDENCE: Exact values from the rebuilt locked-test rows (exact_sets.py). The best possible constant for Europe (its own mean, 742.6, an oracle) has RMSE 386.43. The model's 385.51 therefore equals R2 = 0.005 in g C units, and the code's baseline is within 0.5 g C of the oracle. With the Asia arithmetic mean (870.4; this is also the Duan-smeared intercept) as baseline: RMSE 407.0, MAE 312.7, so the model is 5.3% (RMSE) and 14.6% (MAE) better. With the code's geometric-mean baseline: MAE 272.2, against model MAE 267.1 (-1.9%). PROXY (SRDB MAT/MAP OLS, proxy_ols.py): Duan smearing lowered the model RMSE 374.5 -> 357.6 (smear factor 1.156) and raised the baseline 389.2 -> 407.4 (factor 1.187). The g C gain went from 3.8% to 12.2%.

AFFECTED: prep_log section 13 'RMSE 385.5 vs 386.9 ... constant Asia mean' and 'no practical gain in g C units'; README L33; the planned Fig. 6 (RMSE against a constant).

FIX: Label the baseline as exp(mean log Rs) for Asia (geometric mean, 723 g C), and say that exp(prediction) estimates the median. Report the oracle constant (386.4) and the baseline MAE (272.2). Add a Duan-smeared version for both model and baseline, labelled post hoc; this needs the v3 features. Treat log-space skill (5.9%) as the primary scale-free comparison.

VERIFIER: Every number reproduces exactly on the identified rows. The code back-transforms naively: rp=exp(p) at L89 and baseline exp(mean log Asia) at L92/L98. The constant is the Asia geometric mean, 723. By coincidence it sits about 20 g C below Europe's arithmetic mean of 743, which makes it almost an oracle. The model's naive central value is 618. In log space the model's level bias is smaller than the constant's (-0.046 vs +0.111). The Jensen gap, ln(742.6/647.5) = 0.137, reverses this in g C. So 'no practical gain in g C units' depends on the back-transform convention. That said, against even the oracle constant the naive model reaches only g C R2 0.005, so the claim is true as computed. As a labelled rough estimate, rescaling the real model by a plausible smear factor (1.10-1.17, with prediction SD 0.12-0.2) gives RMSE of about 366-371. That is 4-5% below the code's own baseline. Plan L44 asks for MAE with the intercept baseline. Only the baseline RMSE is computed. Model MAE (L91) is computed but reported nowhere. One minor overstatement: plan L44 itself labels the log-space intercept '(Asia mean)', so 'ambiguous in g C' fits better than 'mislabelled'.

VERIFIER EVIDENCE: exact_rows_stats.py on the 384/235 rows: mean log Asia 6.58390 gives exp 723.36. The Asia arithmetic mean of site values is 870.37, which equals the Duan-smeared intercept (ratio 1.2032). Europe arithmetic mean 742.57, geometric mean 647.46; log difference -0.1108; 135/235 sites have 2 or more records. Code baseline RMSE is 386.9086311104987 (exact). The oracle (Europe mean) has RMSE 386.43, so the model's g C R2 is 0.00475. The arithmetic-mean baseline has RMSE 407.02 and MAE 312.70, so the model is 5.28% better on RMSE and 14.59% better on MAE. The geometric baseline has MAE 272.20 vs the model's 267.08 (1.88% better). Model central value exp(6.4271) = 618.4. Log skill vs the Asia constant is 0.0587. Proxy (proxy_boot.py) replicated: model 374.5 -> 357.6 (smear 1.156), baseline 389.2 -> 407.4 (smear 1.187), gain 3.8% -> 12.2%.


## [locked-test] locked-test-plan-hash-not-verified — finder medium / reproducibility → VERDICT confirmed / medium
**The plan hash is copied from a sidecar file and never checked; the lock has no external timestamp** (scripts/clean_test.py L61; prep_log L156, L174; PROMPT L104)

DESCRIPTION: The script fills plan_sha256 by reading the first token of ANALYSIS_PLAN_LOCKED.sha256 in the features directory. It never opens or hashes ANALYSIS_PLAN_LOCKED.md. The field in the results is therefore a copy, not a verification. The only timestamp (07:28:35Z) is self-reported inside that same sidecar, and the plan has no commit in the repo history. The OPEN item in prep_log L156 suggests committing it now, but that would post-date the ~08:25 UTC scoring, so it cannot prove the plan came first. The output JSON also records no features-table hash, package versions, run time or per-site predictions. The features_v3 tables are not in the bundle, so the scored result cannot be re-analysed exactly.

EVIDENCE: I ran a copy of clean_test.py on a synthetic features table (make_synth.py) with no plan .md present and a sidecar containing 'NOT-A-REAL-HASH'. It ran to completion and wrote "plan_sha256": "NOT-A-REAL-HASH" (synth/out_synth.json). Separately I checked integrity. sha256sum of the bundle's ANALYSIS_PLAN_LOCKED.md is 9d50e120...3dac, equal to the recorded value. results/clean_test_europe.json hashes to b091795f...d1e6, as recorded in prep_log L174. So there is no evidence of tampering. `git log -- docs/handoff/ANALYSIS_PLAN_LOCKED.md` is empty.

AFFECTED: The credibility of the 'pre-registered / locked' claim; reproducibility of the locked numbers (the PROMPT allows ±0.01 because the inputs must be re-downloaded).

FIX: In the rebuild, hash the plan at run time and abort on mismatch, with a test as PROMPT L104 asks. Write the plan hash, features-file hashes, package versions (xgboost matters for the XGB candidates), git commit, UTC time and per-site predictions into the result. Archive the scored features tables with their hashes. In the paper, call the lock internally time-stamped (no external registry before scoring).

VERIFIER: L61 reads the first token of the .sha256 sidecar and never opens or hashes ANALYSIS_PLAN_LOCKED.md. I confirmed this by running the script. The integrity checks all pass, so nothing was tampered with. The provenance gaps are real: the output JSON has no features hash, package versions, run time or per-site predictions, and no features_v3 parquet is in the bundle. One evidence statement is now out of date in a way that strengthens the finding. The plan's only git commit is b98b2ce, the Phase-0 copy, about 27.5 h AFTER the ~08:25Z 2026-11-01 scoring. a809a97 has no plan file. That commit must not be read as the lock time. Severity stays medium, because it changes how 'pre-registered' can be described (internally time-stamped only). The missing external timestamp was already flagged as [OPEN] in prep_log L156; what is new is that the proposed remedy (commit now) cannot establish precedence. The code defect itself is latent, and PROMPT L104 already requires the fix.

VERIFIER EVIDENCE: I ran clean_test_copy.py --no-score on synth/features_synth.parquet with no plan .md and a sidecar reading 'NOT-A-REAL-HASH'. It ran to completion and wrote "plan_sha256": "NOT-A-REAL-HASH" (docs/review/2026-11-02/critique_scripts/verify-locked-test/synth/out_noscore.json). sha256sum of the plan is 9d50e120...3dac, matching the recorded value. results/clean_test_europe.json hashes to b091795f...d1e6, matching prep_log L174. The sidecar contains only the hash line and '2026-11-01T07:28:35Z'. `git log --all -- '*ANALYSIS_PLAN_LOCKED*'` returns only b98b2ce, dated 2026-11-02 11:56:12 +0000. Top-level JSON keys: plan_sha256, train, test, selection_table, selected, primary, aoa, all_candidates_on_test.


## [locked-test] locked-test-undeclared-deviations — finder medium / spec-deviation → VERDICT confirmed / low
**'Deviation from plan: none' is inaccurate** (scripts/clean_test.py; prep_log.md clean_test.py L92, L122, L133; plan L44, L46-49, L53-55; prep_log L178, L180)

DESCRIPTION: The following departures are not declared. (1) H2: the plan requires R2 inside vs outside the AOA, with a bootstrap CI on the difference (L48-49). The script computes it only if both groups have more than 10 sites (L122), a rule that is not in the plan. With 2 sites outside, the planned estimate was silently not produced. 'Not testable' is the right substance, but it is an unplanned contingency. (2) The plan asks for MAE with an intercept baseline (L44). Only the intercept RMSE is computed (L92), and MAE does not appear in prep_log or README. (3) An unplanned analysis, sq_err_by_DI_tercile (L133), is written into the primary JSON without an exploratory label and is never mentioned. Its values are 0.272/0.347/0.242, i.e. no rise in error with DI, which is useful but exploratory. (4) The tie-break is implemented differently from the plan text (see locked-test-tiebreak-chains). (5) UNVERIFIED: plan L53-55 says the noise-ceiling, shift and data-quality analyses run only after scoring, yet prep_log lists E1-E5 (section 12) before the scoring (section 13). E1 used Europe records (ICC Europe 0.62). The bundle has no timestamps to settle the order. None of this could change the mechanical selection.

EVIDENCE: Code lines as cited. JSON: n_inside 233, n_outside 2; there is no inside/outside or r2_diff key. Primary JSON keys contain no MAE for the baseline. prep_log L176 lists RMSE, skill, Spearman and bias but no MAE.

AFFECTED: How H2 is reported; the deviation statement in prep_log section 13.

FIX: Replace 'none' with a deviations list. Report H2 as 'not evaluable: 2/235 sites outside the AOA (threshold 0.198); planned contrast not estimable'. Add the baseline MAE (272.2, recomputed exactly). Label the DI-tercile errors as exploratory. Have the author confirm the run order of E1-E5 relative to 08:25 UTC.

VERIFIER: I verified items 1-4: (1) the >10-site rule at L122 is not in the plan, and the planned inside-minus-outside contrast (plan L48-49) was never produced; (2) there is no baseline MAE, and model MAE is computed but unreported; (3) sq_err_by_DI_tercile is unplanned and unlabelled in the primary JSON; (4) the tie-break code differs from the plan text, with no effect here. So 'Deviation from plan: none' is inaccurate. I downgrade from medium to low. None of these can change any number or the selection. H2's non-testability is already stated plainly (prep_log L178, README). The fix is to replace 'none' with a short deviations list. Item 5 is still unverified. The circumstantial evidence leans toward E1-E5 having run before scoring: §12 comes before §13, and only §14 and exp_matrix.py carry an 'after the locked test' label, while E1-E5 do not. But the bundle has no timestamps. If the author confirms E1 (Europe ICC) or E5 (trained on 967 sites including Europe, though it scores only NA and the grid) ran before 08:25Z, that is a medium, reportable deviation from plan L53-55. E2/E3 use only Asia and NA (exp_shift.py L36, L42-43).

VERIFIER EVIDENCE: clean_test_europe.json aoa keys: threshold 0.1979, frac_inside 0.9915, n_inside 233, n_outside 2, sq_err_by_DI_tercile [0.2718, 0.3467, 0.2417]. There is no inside/outside or r2_diff key. Primary keys contain no baseline MAE. mae_rs = 267.08 is present (L91) but absent from prep_log L176 and README L33. I recomputed the baseline MAE on the exact rows: 272.20. exp_noise_ceiling.py L41-42 groups by continent, so it includes Europe. The E5 JSON shows all_sites n_train 967.


## [locked-test] locked-test-tiebreak-chains — finder low / bug → VERDICT confirmed / low
**The selection tie-break chains, and candidates can be compared on different fold partitions (latent; no effect on the result)** (scripts/clean_test.py L57-60 (tie-break); L49-53 (folds built from each candidate's own rows))

DESCRIPTION: (a) After switching to a simpler candidate, the loop compares later candidates with the new best's score, not the top score. A chain of 0.01 steps can therefore select a model more than 0.01 below the top, which breaks the plan's rule ('within 0.01' of the highest). (b) Folds are built from each candidate's own complete rows. If a dropped site was the only site in its 5-degree block, the block list changes and np.random shuffle re-partitions every block. Candidates are then scored on different CV splits, so differences around the 0.01 tie-break window are compared across different partitions.

EVIDENCE: tiebreak.py, synthetic table (ALL-RF 0.150/20 predictors, C8+MODIS-RF 0.141/12, C8-RF 0.132/8, OLS-TP 0.123/2): the code picks OLS-TP, 0.027 below the top; the plan rule picks C8+MODIS-RF. On both real selection tables the code and the plan rule agree (OLS-TP is top; margin 0.0115 over RF C8+MODIS). partition_demo.py on the exact 384 Asia rows: 69 blocks, 16 singletons. Dropping one singleton-block site changes the seed-42 partition of the remaining sites (adjusted Rand index 0.147); dropping a shared-block site leaves it unchanged (ARI 1.0). For 2-5 random drops (n_train 382/380/379 vs 384), the chance of a partition change is 0.08-0.19. Whether this happened in the real run cannot be checked offline, because the missing-NPP/SoilGrids sites are unknown.

AFFECTED: None of the reported results. It matters for the rebuild and for any future selection fixed in a plan written, committed and hashed before the analysis.

FIX: Fix the reference at the top score and pick the fewest predictors among candidates within 0.01, breaking ties by higher CV R2. Assign blocks to folds once, from the block IDs of all Asia sites, so every candidate uses the same split. Add a unit test.

VERIFIER: (a) In L57-60 the reference moves to each newly chosen simpler candidate, so a chain of steps can end more than 0.01 below the top. That breaks plan L39. (b) folds() at L36-40 shuffles np.unique(blocks) for each candidate's own rows. If a dropped site was the only one in its block, the permutation changes and every block is re-partitioned. I reproduced both. Neither affects the reported selection: OLS-TP is top on every real table and no candidate has fewer predictors. Whether (b) happened in the real run cannot be checked offline. Low is correct.

VERIFIER EVIDENCE: tiebreak_partition.py: on the toy table (0.150/20, 0.141/12, 0.132/8, 0.123/2) the code picks OLS-TP and the plan rule picks C8+MODIS-RF. On clean_test_europe, clean_test_selection_only and the repo sensitivity table, code and plan both pick OLS-TP (top-minus-second margins 0.0115, 0.0115, 0.0188). Exact 384 Asia rows: 69 5-degree blocks, 16 singletons. Dropping one singleton-block site gives ARI 0.147 against the full seed-42 partition. Dropping a shared-block site gives ARI 1.000. Random drops of 2/4/5 sites change the partition with probability 0.086/0.160/0.189.


## [locked-test] locked-test-cv-metric-definition — finder low / doc-mismatch → VERDICT confirmed / low
**Two different 'within-Asia spatial-CV R2' values for the same model and rows; '±' is a fold SD** (scripts/clean_test.py; scripts/exp_matrix.py; prep_log.md clean_test.py L52-56; exp_matrix.py L52-57; prep_log L175, L184)

DESCRIPTION: The selection metric is the mean of 15 per-fold R2 values (5 folds x seeds 42/43/44), each computed around its own fold mean: 0.143. E6 reports 0.163 for the identical OLS-TP model on the identical 384 rows, but that is a pooled out-of-fold R2 with seed 42 only. The prep_log quotes both values as the Asia spatial-CV R2. '0.143 ± 0.076' uses the SD across the 15 fold-level R2 values (cv_r2_sd). That is not an SE, and folds range from 29 to 124 sites.

EVIDENCE: exp_matrix.py reproduces the locked Asia->Europe R2 of 0.079 with n 235 / 384, confirming the same rows. fold_structure.py on the exact rows: fold sizes 29-124; per-fold variance of log Rs 0.275-0.659; null-model mean per-fold R2 -0.022 vs pooled -0.015/-0.005/-0.004.

AFFECTED: Methods text and any table that quotes the Asia CV R2.

FIX: Define the selection metric explicitly in Methods (mean of per-fold R2 over 3x5 folds). Use one definition for the CV R2 in all tables, or name both. Label the ± as the SD across folds.

VERIFIER: The selection metric (clean_test.py L52-56) is the mean of 15 per-fold R2 values over seeds 42-44, giving 0.143. E6's 0.163 (exp_matrix.py L52-57, with folds defaulting to seed=42 at L30) is a pooled out-of-fold R2 from one seed, on the same 384 rows. prep_log L175 and L184 quote both as 'Asia spatial-CV R2'. The '± 0.076' is np.std over the 15 fold values: an SD across folds, not an SE. E6's Asia->Europe entry (n 235, R2 0.079, RMSE 0.535, skill 0.059) matches my exact-row values (RMSE_log 0.5354, skill 0.0587), which confirms the rows are the same. This is a documentation issue only.

VERIFIER EVIDENCE: Fold sizes for seeds 42/43/44: [84,103,63,59,75], [94,124,60,77,29], [68,56,84,82,94], a range of 29-124. Per-fold variance of log Rs runs 0.275-0.659. The null model's mean per-fold R2 is -0.0218, against pooled -0.0149/-0.0049/-0.0036. E6_matrix_OLS-TP.json within_cv Asia: n 384, r2 0.163.


## [locked-test] locked-test-secondary-table-unpaired — finder low / stats-method → VERDICT confirmed / low
**The secondary all-candidate table supports no ranking claim** (scripts/clean_test.py L135-140; prep_log L179)

DESCRIPTION: The table is plan-conformant and has no re-selection. But each ML candidate is scored with one seed (0), on its own n (232-235), with unpaired CIs. 'Every ML model's CI includes 0' is literally true, but it depends on the seed: ALL-RF's lower bound is -0.005 and C8+MODIS-RF's is -0.020. OLS 0.079 vs ALL-XGB 0.0745 differ by 0.005. The table cannot support statements such as 'only the linear model transfers' or 'linear beats ML on Europe'.

EVIDENCE: JSON all_candidates_on_test. The earlier XGB seed range on the US was 0.115-0.173 (prep_log L35), i.e. seed effects of a few hundredths.

AFFECTED: Any paper sentence ranking candidates on Europe.

FIX: Limit the text to 'no candidate is clearly better than the selected model'. If contrasts are wanted, use a paired bootstrap on the common 232 sites with seed ensembles, labelled secondary/post hoc.

VERIFIER: This is accurate as a caution. L135-140 score every candidate with seed 0 on its own complete rows (n 232-235), and the table reports only marginal CIs. 'Every ML CI includes 0' is literally true. Read beside OLS's interval, which excludes 0, it invites a 'significant vs not significant' ranking the data do not support (OLS 0.0790 vs ALL-XGB 0.0745). One nuance: the five candidates with n=235 share the same rows and order, and boot_ci uses seed 42, so their bootstrap draws are identical. Paired difference CIs would therefore be trivial to add. The sub-claim that the result 'depends on the seed' cannot be verified without the v3 features. It is plausible: ALL-RF's lower bound is only 0.005 below 0, and prep_log L49 shows an RF seed range of 0.145-0.164 on the US. The bundle contains no explicit Europe ranking sentence. The risk is in how L179 will be paraphrased.

VERIFIER EVIDENCE: JSON all_candidates_on_test: n = 235/235/235/235/234/234/232/232/232/232/235. ALL-RF ci_site lower bound -0.00527; C8+MODIS-RF -0.0203. ALL-XGB r2 0.07445 vs OLS-TP 0.07900. Code: score(s,l) defaults to seed=0 (L80), and e is built with dropna on the same columns, so it is identical for all C8-based n=235 sets.


### checked_ok for locked-test
- Candidate set: 5 predictor sets x {XGB, RF} + OLS-TP = 11 candidates. Set contents (C8, +npp, +npp/lst_day/lst_night/lst_diurnal_range, +8 SoilGrids, ALL = 20) match plan L25-29 (clean_test.py L16-19, L45).
- Learner parameters: instantiating them under sklearn 1.9.1 / xgboost 2.1.4 and reading get_params() gives exactly plan L31-34 (XGB 250/3/0.05/0.85/0.85/4/0.5/2.0, rs 0; RF 500 trees, min_samples_leaf 5, max_features 0.5, rs 0). OLS-TP = LinearRegression on [bio01, ln bio12], with intercept.
- Per-set complete-case dropping (L49, L82-83) matches plan L35. n_train is 384/380/380/382/379; OLS-TP and C8 share the same 384 rows.
- Spatial CV: 5x5-degree lon/lat blocks; shuffled block list split into 5 folds; block-to-fold seeds 42/43/44; metric = mean of per-fold R2 (L36-40, L52-56). On the exact rows: 69 blocks, fold sizes 29-124.
- No Europe data enters selection: selection and AOA standardisation use Asia rows only (L44, L49, L105). clean_test_selection_only.json (separate --no-score run) gives the identical selection; RF cv_r2 values differ only at 1e-16 (n_jobs=2 non-determinism).
- Refit of the selected model on all Asia complete rows (n=384, L82-84); scored once; the secondary table refits each candidate with no re-selection.
- Primary R2 = r2_score on log Rs with SST around the Europe mean (L90). The site bootstrap (2,000 draws, fixed model, percentile) and the 2-degree block bootstrap (blocks resampled with replacement; Europe has 93 blocks, 33 singletons) are implemented as planned (L68-77).
- The H1 verdict follows the plan's rule (site-bootstrap lower bound 0.0134 > 0). The Monte Carlo SD of the bounds is about 0.002, so 'met on site, borderline on spatial (-0.0003)' is accurate. The intercept-only (Asia mean) log-space R2 on Europe is -0.039 (exact), so R2 > 0 is a stricter bar than beating the Asia-mean constant.
- Exact reproduction: rebuilding the v3 tables from SRDB + COSORE (66 sites) + Natural Earth reproduces build_summary.json exactly. The intercept baseline exp(mean log Rs Asia) reproduces rmse_rs_intercept 386.9086311104987 exactly. The log-space skill of 5.9% quoted in prep_log section 13 (taken from E6) is consistent: recomputed 0.0587.
- exp_matrix.py (an independent code path) reproduces the Asia->Europe OLS-TP R2 of 0.079, n 235.
- AOA matches Meyer & Pebesma 2021 / CAST trainDI: standardisation with Asia mean/SD; unweighted for OLS (plan L47); dbar = mean of all pairwise training distances; CV training DI = distance to the nearest point outside the site's own fold (seed-42 folds); threshold = largest training DI <= Q3 + 1.5 IQR, i.e. the boxplot upper whisker (np type-7 quartiles vs R's hinges is negligible); Europe DI = distance to the nearest Asia point. The inside/outside branch runs correctly on synthetic data with many outside sites.
- Seed-spread rule correctly not applied for OLS (L99-101); prep_log notes this.
- Every locked-test number in prep_log sections 13/14, README L33-34 and PROMPT L19/L101 matches the JSONs: 0.143 ± 0.076, RF C8+MODIS 0.132, XGB <= 0.046, n 235, R2 0.079 [0.013, 0.125], block [-0.000, 0.134], RMSE 385.5 vs 386.9, Spearman 0.26, bias -0.046, 233/235 inside, ML range -0.051 to +0.074; sensitivity n 282, R2 0.052 [0.004, 0.092], block [-0.004, 0.099], RMSE 405.1 vs 405.9. The plan file's SHA-256 equals the recorded 9d50e120...3dac, and the results file hashes to b091795f...d1e6 as recorded.
- Spatial separation of train and test: the nearest Asia training site to any Europe test site is 1,602 km (QC; none within 500 km) and 360 km (repo filters; 1 within 500 km). The QC Asia set has only 13 West-Asian/Ural sites (Israel 6, Russia >= 60E 6, Kazakhstan 1). There is no cross-continent proximity leakage and no 5-km site merging across continents.
- The repo-filter sensitivity is plan-specified; it re-runs the same selection and again picks OLS-TP.
- I wrote nothing under /home/user/MSHI; docs/handoff is byte-identical to the original unzip. Scratch scripts and outputs are in docs/review/2026-11-02/critique_scripts/locked-test/


## [new-argument] new-argument-01 — finder high / claim-unsupported → VERDICT confirmed / high
**Claim (1) '68.5% vs 30.1%' depends on counting IGBP 8 (woody savanna, 30-60% tree cover) as non-forest; with IGBP 8 as forest the pixel share at plots is 47.7%** (docs/handoff/scripts/exp_forest_bias.py (also exp_plot_pixel.py, exp_selection_bias.py) exp_forest_bias.py L31, L45; exp_plot_pixel.py L28; exp_selection_bias.py L60, L64)

DESCRIPTION: N2/N2b (and N1) define pixel forest and landscape forest as IGBP 1-5 only (>60% tree cover). IGBP 8 (woody savanna, 30-60%) and 9 (savanna, 10-30%) count as non-forest. SRDB 'Forest' has no canopy threshold. Most 'forest plot in non-forest pixel' cases are exactly these classes. N2c/N2d already treat IGBP 8 as ambiguous (X1/X2), but the N2/N2b numbers behind claims (1) and (2) use only the X2-like convention, the one that maximises the gap. PROMPT section 6.1 itself lists woody savanna as an ambiguous case to state.

EVIDENCE: I rebuilt the v3 sites with the handoff build_sites_v3.py and cosore_aggregate.py (paths changed only). build_summary.json is identical to the handoff's, and COSORE gives the same 66 sites as data/derived. With the committed landcover_igbp_2023.tif I reproduced the N2 Q1 crosstab exactly: n=624, all 36 cells, 0.694/0.304, agreement 0.575, 254. I also reproduced the N2b sample: n=581 before the 3-site WorldClim drop (handoff 578), plot forest 0.685 (exact), pixel 0.299 (handoff 0.301), landscape 0.199 (handoff 0.198). IGBP codes under the 433 Q1 forest plots: 1-5: 179; 8: 100; 9: 36; 12: 31; 13: 28; 17: 19; 10: 17; 14: 17; 11: 3; 16: 2; 6: 1. In the N2b sample, pixel-forest share at plots is 0.299 for IGBP 1-5, 0.477 for 1-5+8 and 0.552 for 1-5+8+9. Forest plots in 'forest' pixels: 41.2% / 64.8% / 73.6%. Area-weighted landscape forest share over the N2b footprint: 0.199 / 0.319. Proxy re-run of N2b (see new-argument-04 for the validated proxy) with IGBP 8 = forest for both the pixel flag and the landscape fraction: inflation 4.3% becomes 2.6% (iid [0.0, 5.5], 2-deg block [-0.2, 6.2]), and the pixel coefficient 0.003 becomes 0.051 [-0.057, 0.156]. Scripts: docs/review/2026-11-02/critique_scripts/new-argument/scripts/n2_replicate.py, n2b_shares.py, n2b_totals_fast.py.

AFFECTED: PROMPT section 1 claim (1) 30.1% (and the 'measured in forests' gap: 38 pp becomes 21 pp); claim (2) pixel coefficient; claim (3) binary lower bound 4.3%; N2_plot_pixel.json Q1; N2b_forest_bias.json pixel_forest_share, landscape share, inflation; N1 site/peer forest fractions

FIX: Report claim (1) under at least IGBP 1-5 / 1-5+8 / 1-5+8+9 (30% / 48% / 55%), state the IGBP canopy definitions, and justify the mapping of SRDB 'Forest' (no threshold) onto them. Fix the primary crosswalk in the Phase-3 plan before any held-out region is scored. Use one crosswalk consistently for the plot comparison, the pixel flag and the landscape fractions.

VERIFIER: Confirmed. N2b, N2 and N1 all define a forest pixel and forest landscape as IGBP 1-5 only (exp_forest_bias.py L31, L45; exp_plot_pixel.py L28 maps 8/9 to 'Savanna'; exp_selection_bias.py L60, L64). IGBP 8 (30-60% tree cover) is a definitional boundary for SRDB 'Forest', and PROMPT L130 itself calls woody savanna ambiguous. I reproduced every number independently. Claim (1) keeps its direction (68.5% > 47.7% > 30.1%), but the headline gap drops from 38 pp to 21 pp. The 1-5+8 crosswalk also moves claim (2) (pixel coefficient 0.003 -> 0.051) and claim (3) (binary inflation 4.4% -> 2.7%). That is a headline change and a referee-level objection, so high stays. Not checkable offline: SRDB's own definition of Ecosystem_type (there is no SRDB documentation under data/raw/srdb).

VERIFIER EVIDENCE: Checked OK first: a verbatim copy of build_sites_v3.py (docs/review/2026-11-02/critique_scripts/verify-new-argument/scripts/build_sites_v3_verbatim.py) run on SRDB + data/derived/cosore_annual.csv + Natural Earth 5.1.2 gives a build_summary.json identical to the handoff's. An exact replication of N2 Q1 (docs/review/2026-11-02/critique_scripts/verify-new-argument/scripts/v_q1.py) matches all five Q1 keys of N2_plot_pixel.json. IGBP codes under the 433 Q1 forest plots: 1-5 179 (1:9, 2:56, 4:65, 5:49); 8:100; 9:36; 12:31; 13:28; 17:19; 10:17; 14:17; 11:3; 16:2; 6:1. N2b sample before the WorldClim drop (n=581, all with code>0; the 4 coastal sites without proxy climate all sit in IGBP-17 cells): plot-forest share 0.685 (398 plots). Pixel-forest share at plots is 0.2995 for 1-5, 0.4768 for 1-5+8 and 0.5525 for 1-5+8+9; forest plots in such pixels are 41.2%, 64.8% and 73.6% (v_shares.py). Area-weighted landscape forest share is 0.199 (1-5) vs 0.319 (1-5+8). Proxy N2b: site climate from the nearest original-pipeline site within 10 km (577/581 sites); cell climate from atlas_lookup.json 0.5-deg centres, which cover 89.5% of the footprint area, with the rest filled from the nearest atlas cell within 1 deg. Run through the handoff's own totals() copied verbatim, the proxy reproduces N2b: n 577 vs 578; plot coefficient 0.125 [0.007,0.246] vs 0.126 [0.009,0.244]; pixel 0.003 [-0.099,0.099] vs 0.005 [-0.097,0.106]; A/B/C 39.47/39.47/37.82 vs 39.09/39.10/37.46 Pg; inflation 0.044 [0.003,0.091] vs 0.043 [0.003,0.088] (docs/review/2026-11-02/critique_scripts/verify-new-argument/out/n2b_replicate.json). With IGBP 8 = forest for both the pixel flag and the cell fraction (numpy re-implementation, 2000 draws): inflation 2.67%, iid [0.0,5.5], 2-deg block [-0.2,6.3] (n=581 variant: 2.84% [0.3,5.8]). Pixel coefficient 0.051 [-0.057,0.156]; plot-pixel difference 0.074 [-0.061,0.202] (docs/review/2026-11-02/critique_scripts/verify-new-argument/out/n2b_fast_s577_cfill.json).


## [new-argument] new-argument-02 — finder high / stats-method → VERDICT confirmed / high
**The 4.3% binary inflation is an artefact of pooled Duan smearing: residual variance differs by class, and with class-specific smearing or a log-link GLM the inflation is about 0-2% with CIs spanning 0** (docs/handoff/scripts/exp_forest_bias.py; exp_poststrat.py; exp_poststrat_nodesert.py exp_forest_bias.py L63, L65-66; exp_poststrat.py L67-71)

DESCRIPTION: Totals are arithmetic sums, but the class effect is fitted on log Rs and back-transformed with one smearing factor per model (L63; exp_poststrat.py L68 smC). That assumes homoscedastic residuals across classes. Non-forest plots have much larger log residual SD. So the pooled factor overstates forest and understates non-forest arithmetic means, which biases the post-stratified total C low and the inflation A/C-1 high. On the log scale the forest effect is +0.125 (geometric mean). On the arithmetic-mean scale that drives fluxes it is about +0.02 to +0.05 and not significant.

EVIDENCE: PROXY re-analysis, validated against the handoff (details in new-argument-04). Residuals of the N2b C model: SD 0.481 for forest (n=395) vs 0.670 for non-forest (n=182); Brown-Forsythe p = 5.6e-8. Pooled smearing factors A vs C are 1.1522 vs 1.1525, so per model smearing is not the issue; class heteroscedasticity is. Binary inflation, handoff spec: 4.33% (iid [0.0, 8.8]). With class-specific smearing: -0.19% (iid 2000 [-4.5, 4.8]; 2-deg block [-4.4, 5.3]). Log-link GLMs fitted to Rs, which need no retransformation: quasi-Poisson forest coefficient 0.048 [-0.074, 0.170] (HC3), inflation 1.71%; Gamma-log 0.049 [-0.069, 0.167], inflation 1.72%. Forest effect on the arithmetic scale (log-ratio of class-smeared means): 0.018 [-0.104, 0.149]. N2d with class-specific smearing: X1 7.2% becomes 5.0% [2.0, 8.7], X2 15.1% becomes 12.6% [7.0, 19.0]; what remains is carried by the 5-plot savanna class (new-argument-03). Scripts: .../critique/new-argument/scripts/smearing.py, n2d_smearing.py; outputs .../out/smearing.json, n2d_smearing.json.

AFFECTED: Claim (3) lower bound '4%' (N2b_forest_bias.json inflation_A 0.043 [0.003, 0.088]); the relevance of claim (2) to upscaled fluxes; N2c/N2d inflations (smaller effect)

FIX: Retransform with class-specific smearing, or fit the class model as a log-link GLM (Gamma or quasi-Poisson) for totals. Report class effects on the arithmetic scale. Fix the retransformation in the Phase-3 analysis plan (written, committed and hashed before the analysis), and show both if the choice is contested (measurement noise vs real heterogeneity).

VERIFIER: Confirmed. exp_forest_bias.py L63-66 and exp_poststrat.py L67-71 apply one pooled Duan factor to every class. That is consistent only if the log errors are homoscedastic, and here they are strongly heteroscedastic by class. Class-specific smearing and log-link GLMs (which need no retransformation) both put the binary inflation at about 0-2% with CIs spanning 0. On the arithmetic scale that drives fluxes, the forest effect is about 0.02-0.05 and not significant. So the '4%' lower bound of claim (3), and the flux relevance of claim (2), are not robust: high is kept. Two caveats. First, if the extra non-forest variance is measurement noise rather than real heterogeneity, class-specific smearing over-corrects, and the truth lies between the two estimates (the reviewer notes this). Second, the multi-class N2d inflation only shrinks (7.2 -> 5.0%, 15.1 -> 12.6%), and what remains is carried by savanna and shrubland together, not only by the 5 savanna plots (see 03).

VERIFIER EVIDENCE: Proxy validated as in finding 01 (n=577, 28,145 cells, 2000 draws; docs/review/2026-11-02/critique_scripts/verify-new-argument/scripts/v_n2b_fast.py, output docs/review/2026-11-02/critique_scripts/verify-new-argument/out/n2b_fast_s577_cfill.json). C-model residual SD is 0.481 for forest (n=395) vs 0.670 for non-forest (n=182); Brown-Forsythe p = 5.6e-8. Pooled smearing factors: A 1.1522 vs C 1.1525. Class-specific factors: 1.113 forest vs 1.238 non-forest. Binary inflation under the handoff spec: 4.36%, iid [0.0,8.9], block [-0.3,9.9]. With class-specific smearing: -0.19%, iid [-4.5,4.8], 2-deg block [-4.4,5.3] (n=581 variant: 0.00% [-4.2,5.0]). Quasi-Poisson log-link: forest coefficient 0.048, HC3 [-0.074,0.170]; inflation 1.71% (500 iid draws, [-2.0,6.5]). Gamma log-link: 0.049 [-0.069,0.167]; inflation 1.73%. Arithmetic-scale forest effect: 0.018 [-0.104,0.149]. N2d proxy (n=564) reproduces the handoff: X1 7.24% [3.7,10.6] vs 7.2% [3.7,10.4]; X2 15.06% vs 15.0%. With class-specific smearing it gives X1 5.0% [2.0,8.7] and X2 12.6% [7.0,18.9] (docs/review/2026-11-02/critique_scripts/verify-new-argument/out/n2cd_d.json).


## [new-argument] new-argument-03 — finder high / stats-method → VERDICT uncertain / medium
**The 15% upper end rests on a Savanna class of 5 plots applied to 11-23% of the landscape; applying the Phase-3 plan's own <20-plot pooling rule gives -1.7% to +3.9%, all CIs spanning 0** (docs/handoff/scripts/exp_poststrat.py; exp_poststrat_nodesert.py exp_poststrat.py L14, L45-47, L66, L69-71)

DESCRIPTION: N2c/N2d fit unpooled class dummies. The N2c sample has Forest 398, Grassland 78, Agriculture 73, Shrubland 14, Desert 13 and Savanna 5 plots (4 in CONUS: TX, OR, CA, GA; 1 in Yunnan). The Savanna coefficient (-0.66 vs forest) is applied to IGBP 9 (X1, 11% of area) or IGBP 8+9 (X2, 23.5%). Nearly half of IGBP-8 area is boreal (north of 50 deg N), where no savanna plot exists. PROMPT section 6.2 requires merging any class with fewer than 20 plots into its nearest neighbour; Savanna, Shrubland and Desert all qualify. The X1-to-X2 spread (7.5% to 14.6%) is essentially the savanna coefficient times the IGBP-8 area.

EVIDENCE: PROXY re-analysis (numpy OLS, same spec). It reproduces N2d: X1 7.2% [3.7, 10.6] vs handoff 7.2% [3.7, 10.4]; X2 15.1% vs 15.0%; landscape shares within 0.005. N2c-with-desert cannot be reproduced because the atlas climate misses barren cells. Multi-class coefficients vs forest (HC3 SE): Savanna -0.66 (0.21, n=5), Shrubland -0.47 (0.17, n=14), Desert -0.85 (0.23, n=13), Agriculture -0.15 (0.08, n=72), Grassland -0.00 (0.08, n=78). Leave-one-savanna-plot-out, N2d X2: 12.5-16.7%. With the pooling rule and the handoff's pooled smearing: Savanna to Grassland gives X1 2.3% [-1.1, 5.7], X2 3.1% [-2.3, 8.7]; Savanna to Forest gives 1.2% [-0.6, 3.1]; Savanna+Shrubland to Grassland gives 2.4% [-0.6, 5.9] / 3.9% [-1.0, 9.6]. With class-specific smearing, every pooled variant falls in -1.7% to -0.7%, with CIs spanning 0. IGBP-8 area share by latitude band: 28.1% at 50-60 deg N and 20.5% at 60-80 deg N. Scripts: .../critique/new-argument/scripts/n2c_proxy_run.py, n2d_smearing.py, n2d_smearing_pool2.py, footprint.py.

AFFECTED: Claim (3) '4-15%' upper end; N2c_poststrat.json and N2d_poststrat_no_desert.json X1/X2 inflations; '3-13 Pg' upper end

FIX: Apply the pre-specified pooling, or partial pooling with a class random effect (PROMPT 6.3 item 6), before quoting any range. Report each class's contribution to C-A. Do not let a class with fewer than 20 plots set a bound. Restrict class effects to the climate range where that class was sampled.

VERIFIER: The defect is confirmed, but the stated impact is not established. Defect: N2c/N2d fit unpooled class dummies (exp_poststrat.py L66), so the X1 -> X2 step is the 5-plot Savanna coefficient (4 CONUS plots, 1 in Yunnan) applied to IGBP 8, about half of which lies north of 50N. Impact: the claim that the <20-plot rule gives -1.7% to +3.9% with all CIs spanning 0 holds only for hard merges into Grassland or Forest. Two of the reviewer's three N2d variants also leave Shrubland (14 plots) unpooled, so they violate the same rule. The PROMPT fixes the threshold but not the merge target, and other rule-compliant merges give different answers. Merging into Agriculture (the nearest large class by coefficient) gives CIs above 0. A dryland merge in N2c (Savanna + Desert into Shrubland, 32 plots) leaves the upper end roughly unchanged. Partial pooling, which PROMPT 6.3 item 6 asks for, keeps most of it. Leave-one-out also shows the effect is not driven by a single plot. Correct statement: the upper end depends on how the <20-plot dryland classes are handled, about 2-15%. prep_log L192 already flags these classes as fragile. The Phase-3 plan must pre-specify the merge target, not only the threshold. Severity lowered to medium.

VERIFIER EVIDENCE: Reproduced on the N2d proxy (n=564; docs/review/2026-11-02/critique_scripts/verify-new-argument/scripts/v_n2cd.py, log docs/review/2026-11-02/critique_scripts/verify-new-argument/out/log_n2d.txt). HC3 coefficients vs forest: Savanna -0.674 (0.216, n=5), Shrubland -0.485 (0.166, n=14), Agriculture -0.162 (0.079), Grassland -0.009 (0.083). Savanna plots: TX, OR, CA, GA and Yunnan. Leave-one-savanna-plot-out X2: 12.5-16.6%. Sav->Grass: 2.4% [-1.0,5.8] / 3.2% [-2.2,8.8]. Sav->Forest: 1.4% [-0.5,3.3]. Sav+Shrub->Grass: 2.4% / 3.9% [-1.0,9.5]. With class-specific smearing these merges give -1.6% to -0.6%. IGBP-8 area: 28.1% at 50-60N and 20.5% at 60-80N. Counter-checks (docs/review/2026-11-02/critique_scripts/verify-new-argument/scripts/v_n2c_dryland.py, v_n2c_dryland_cs.py and v_partial_pool.py in the same folder; logs out/log_dryland_pooledsmear.txt, out/log_dryland_classsmear.txt and out/log_partial_pool.txt there). N2d with Sav+Shrub->Agriculture: X1 3.4% [1.0,6.1], X2 6.3% [2.2,10.7]. N2c with desert is approximate because barren-cell climate is filled from the nearest atlas cell (base X1/X2 9.1%/16.3% vs handoff 7.5%/14.6%). The dryland merge Savanna+Desert->Shrubland (32 plots, meets the threshold) gives X1 8.4% [4.9,12.6] and X2 15.3% [9.4,21.7]; with class-specific smearing, 5.5% [2.2,10.0] and 11.4% [5.8,18.4]. Method-of-moments empirical-Bayes shrinkage of the N2d class effects (tau^2 = 0.073; Savanna -0.674 -> -0.515, Shrubland -0.485 -> -0.425) gives X1 6.4% and X2 12.6%.


## [new-argument] new-argument-04 — finder high / stats-method → VERDICT confirmed / high
**Claim (2): the plot−pixel difference is never tested and is not significant, the plot effect is not robust to spatial blocking, the 'attenuation' reading has no power with these data, and the 'forest' effect is not forest-specific** (docs/handoff/scripts/exp_forest_bias.py L60-62, L72-86)

DESCRIPTION: Only marginal iid site-bootstrap CIs from 500 draws are reported. The script stores both coefficients in every draw (L76) but never computes the paired difference, which is the test PROMPT 6.2 H2 requires. Spatial dependence is ignored, although the locked test used a 2-deg block bootstrap. Under non-differential misclassification, the expected pixel coefficient is λ·β, where λ = slope of E[plot forest | pixel forest, climate]. With λ ≈ 0.17 that is about 0.02, so a pixel coefficient of ~0 is predicted by attenuation and by a null alike; the pixel result cannot support 'which is attenuation'. The crosstab also shows structured, not random, disagreement: 54% of forest-plot/non-forest-pixel cases are IGBP 8/9 (a definition boundary), and 19% are water/urban cells (a scale effect). Finally, given climate, grassland plots have the same log Rs as forest plots. The binary +0.126 is carried by agriculture and 32 shrub/savanna/desert plots, which undercuts the 'measured in forests' framing.

EVIDENCE: PROXY: site climate (bio01, bio12) from the nearest original-pipeline site (training_features_v2 / us_validation_features_v2; 577/581 within 10 km, median 0 km). 0.5-deg cell-centre climate from legacy/data/outputs/atlas_lookup.json (covers 89.5% of the N2b footprint area). Validation: plot coefficient 0.125 [0.001, 0.242] and pixel 0.003 [-0.101, 0.101] vs handoff 0.126 [0.009, 0.244] and 0.005 [-0.097, 0.106]; inflation 4.33% vs 4.3%. New results, 2000 draws each: paired plot−pixel difference 0.122, iid [-0.011, 0.255], 2-deg block (262 blocks) [-0.019, 0.271]. Plot coefficient with block bootstrap [-0.007, 0.263]; binary inflation with block bootstrap [-0.3%, 9.9%]. λ = 0.168 [0.101, 0.231], so the expected attenuated pixel coefficient is 0.021 [0.000, 0.044]. Surrogacy check (pixel given plot class): -0.019 [-0.12, 0.08]. Among forest plots only, the pixel-forest coefficient is 0.057 [-0.048, 0.158]. Multi-class coefficients vs forest (HC3): Grassland -0.000 ± 0.083 (n=78), Agriculture -0.152 ± 0.080 (n=72), Shrubland -0.47, Savanna -0.66, Desert -0.85. Scripts: .../critique/new-argument/scripts/proxy_climate.py, cells_proxy.py, n2b_attenuation.py, n2b_totals_fast.py; outputs .../out/n2b_attenuation.json, n2b_totals_fast.json.

AFFECTED: PROMPT section 1 claim (2), including its 'attenuation' interpretation; N2b_forest_bias.json coef CIs; README N2 headline

FIX: Report the paired difference with a spatial-block bootstrap; at the pilot stage it is not significant. Call attenuation a hypothesis until a regression-calibration model is fitted (6.3 item 4), and report λ. Report multi-class effects and reframe the mechanism around the classes that carry it, not 'forest'.

VERIFIER: Confirmed on code and data. L76 stores both coefficients in every draw, but L79-86 report only marginal iid CIs. PROMPT 6.2 H2 requires a CI on the difference, and the locked test used a 2-deg block bootstrap (prep_log L176). The paired-difference CI just includes 0. With lambda about 0.17, attenuation predicts a pixel coefficient of about 0.02, which cannot be told apart from 0 with this precision, so the data cannot support 'which is attenuation'. Given climate, grassland plots are equal to forest plots. One sub-claim is overstated. The block CI of the plot coefficient is borderline, not clearly non-robust: its lower bound is -0.007 when all 4 coastal sites without proxy climate are dropped (n=577) and +0.009 when all are kept (n=581); the handoff's n=578 lies between. The paired-difference test is likewise borderline (lower bounds -0.019 to -0.002). Interpretation, not tested: the effect is carried by agriculture and the dryland classes, which overlaps the arid-zone bias of Cao et al. that PROMPT L27-29 says the paper must distinguish itself from.

VERIFIER EVIDENCE: Proxy, 2000 draws (docs/review/2026-11-02/critique_scripts/verify-new-argument/out/n2b_fast_s577_cfill.json and docs/review/2026-11-02/critique_scripts/verify-new-argument/out/n2b_fast_s581_cfill.json). n=577: plot coefficient 0.125, iid [0.001,0.242], 2-deg block over 262 blocks [-0.007,0.263]. Pixel 0.003 [-0.101,0.101]. Paired difference 0.122, iid [-0.011,0.255], block [-0.019,0.271]. n=581: plot block CI [0.009,0.276]; difference iid [-0.007,0.266], block [-0.002,0.273]. Lambda (OLS of plot flag on pixel flag + climate + continent) is 0.168 [0.101,0.231], so the expected attenuated pixel coefficient is 0.021 [0.000,0.044]. Pixel coefficient given the plot flag: -0.019 [-0.12,0.08]. Pixel coefficient among forest plots only: 0.057 [-0.045,0.154]. Binary inflation, block CI: [-0.3%,9.9%] (n=581: [0.3%,10.1%]). Q1 crosstab: of the 254 forest-plot/non-forest-pixel cases, 136 (53.5%) are IGBP 8/9 and 47 (18.5%) are water or urban. Forest-specificity, HC3 (docs/review/2026-11-02/critique_scripts/verify-new-argument/scripts/v_forest_specific.py): forest vs grassland only, +0.004 [-0.159,0.166] (n=473). After dropping the 32 shrub/savanna/desert plots, +0.094 [-0.029,0.217]. Forest vs agriculture only, +0.225 [0.068,0.382].


## [new-argument] new-argument-05 — finder high / claim-unsupported → VERDICT confirmed / high
**'Scaled globally, that is 3-13 Pg C/yr' is not computed by any script or results file, and the likely arithmetic overstates it** (none (no script); PROMPT_mshi_v3.md PROMPT_mshi_v3.md L26)

DESCRIPTION: No handoff script or JSON scales the footprint inflation to a global flux. The figure appears only in PROMPT L26. My inference, labelled as such: it matches E5's global total 87.3 Pg × {0.043, 0.150} = {3.8, 13.1}. That arithmetic has four problems. (i) Inflation is A/C-1, relative to the post-stratified total, so the absolute reduction is A·i/(1+i) = 3.6-11.4 Pg. (ii) 87.3 Pg comes from a different model (E5 C8 XGB, all sites, global) than the OLS footprint models. (iii) Carrying a box-footprint ratio to unsampled continents is exactly what the Phase-3 held-out test is meant to establish. (iv) Under new-argument-02/03 the range includes ~0. The comparison with Jian et al. 2022 is also not computed, and I could not verify it offline.

EVIDENCE: grep over docs/handoff/scripts/*.py and results/*.json for global, Pg C, 87.3 and 3-13 finds only E5 (global_rs_PgC 87.3, all_sites) and PROMPT L26. Arithmetic: 87.3×0.043/1.043 = 3.60; 87.3×0.15/1.15 = 11.39.

AFFECTED: PROMPT section 1 headline '3-13 Pg C yr-1' and its comparison with the Rs-GPP gap

FIX: Remove the number until Phase 3 computes it in code: the same model for numerator and denominator, the absolute difference A−C with a bootstrap CI, and the held-out regions. Label any interim extrapolation as such.

VERIFIER: Confirmed. No code anywhere in the repo computes '3-13 Pg C/yr'. The reviewer labels the arithmetic as an inference; that inference is plausible. There is one more inconsistency the reviewer did not mention: E5's 87.3 Pg is back-transformed with no smearing at all, while the footprint totals use Duan smearing (factor about 1.15). So scaling one by the other mixes retransformation scales, as well as models (XGB vs OLS) and domains (global vs boxes). Under 02 and 03 the inflation range itself is also not robust. It is a headline number in PROMPT section 1 with no computation behind it, so high stays.

VERIFIER EVIDENCE: grep -rIn over /home/user/MSHI (excluding .git, .venv and data) for '3–13', '13 Pg' and 'Pg C yr' finds the figure only at PROMPT_mshi_v3.md L26. Pg totals exist only in E5 (87.3 all-site, 92.8 Asia-only), N1, N2b, N2c and N2d, and the last four are footprint totals. exp_global_aoa.py: XGB C8 trained on all QC sites (L3, L14-16, L38), predicting on all global 0.5-deg WorldClim land cells (L18-26). L60 is `rs = np.exp(pred)` with no retransformation; compare exp_forest_bias.py L63, which smears. Arithmetic: 87.3 x 0.043 = 3.75 and 87.3 x 0.150 = 13.1. A·i/(1+i) gives 3.60 and 11.39. No script uses GPP, so the Jian et al. 2022 comparison is not computed either.


## [new-argument] new-argument-06 — finder medium / claim-unsupported → VERDICT confirmed / medium
**'Holds even for coordinates precise to about 10 m' is backed by no code; ≥4 decimals is not 10 m (two-thirds are DMS conversions), n is about 40 forest plots, and the test cannot address a 5.5-km pixel mismatch** (none (no script); prep_log.md L192 prep_log.md L192; PROMPT_mshi_v3.md L22; build_sites_v3.py L95)

DESCRIPTION: No handoff script counts coordinate decimals. Reconstructed from the raw CSV strings, the subset is tiny and imprecise. Many ≥4-decimal SRDB coordinates are degree-minute(-second) conversions; e.g. 42.03333333 = 42°02′, which is ±0.9 km, not 10 m. A naive count on site-table floats is wrong, because site lat/lon are means of record coordinates (build_sites_v3.py L95). The comparison pixel is a 0.05° cell (~5.5 km), so sub-km precision barely changes which cell a plot falls in. The test rules out gross coordinate error but not the scale or definition explanations.

EVIDENCE: Ran .../critique/new-argument/scripts/decimals.py and decimals2.py on raw srdb-data.csv strings mapped to the rebuilt QC sites. Forest plots whose every record has ≥4 decimals: 14/40 in IGBP 1-5 pixels = 35.0% (Wilson [22.1, 50.5]), matching prep_log's '34%', vs 179/433 = 41.3% overall. SRDB rows with ≥4 decimals in both coordinates: 1,521; 598 are minute-level DMS and 429 second-level. Excluding DMS-like coordinates leaves 13 forest plots (4 in forest pixels). Counting decimals on site-mean floats gives 130 '≥4-decimal' sites, 73 of which contain a record with fewer than 4 decimals.

AFFECTED: PROMPT section 1 claim (1) second sentence; prep_log section 15 'not coordinate error'

FIX: Compute the stratification in code from the raw strings, flag DMS conversions, and report n with a CI. Describe it as '≥4 decimal digits', not '≈10 m'. Address scale with the planned WorldCover 30-m to 5-km neighbourhoods.

VERIFIER: Confirmed, with numeric corrections. No handoff code counts coordinate decimals. The >=4-decimal forest subset is about 36-39 plots, with a wide CI. Coordinate precision far below the 5.5-km cell size cannot separate the scale explanation from the definition explanation. Two corrections. First, the reviewer's counts are slightly inflated by a parsing slip: their decimals.py does not strip whitespace, and 86 SRDB coordinate strings carry a trailing space (e.g. '53.883 '), so some 3-decimal values were counted as 4. Second, 'two-thirds are DMS conversions' overstates the imprecision. Only minute-level conversions (about 40% of >=4-decimal rows) are +/-0.9 km. Second-level conversions (about 28%) are +/-15 m, which is roughly the claimed 10 m.

VERIFIER EVIDENCE: A grep for 'decimal' and 'precis' across docs/handoff hits only prep_log L92/L192 and PROMPT L22/L155, no script. Reconstruction (docs/review/2026-11-02/critique_scripts/verify-new-argument/scripts/v_decimals.py, log docs/review/2026-11-02/critique_scripts/verify-new-argument/out/log_decimals.txt): records are mapped to sites by re-running the to_sites() connected-component labelling, asserted equal to the rebuilt site coordinates. Raw coordinate strings are read from srdb-data.csv as str and stripped. Q1 forest plots whose every record has >=4 decimals in both coordinates: 13/39 in IGBP 1-5 = 33.3% (Wilson [20.6,49.0]); N2b sample 12/36. Overall: 179/433 = 41.3%. SRDB rows with >=4 decimals in both coordinates: 1,471 (the reviewer reports 1,521). Of these, 589 are minute-level DMS and 413 second-level. Excluding only minute-level DMS leaves 30 Q1 forest plots, 36.7% [21.9,54.5] in forest pixels. Excluding all DMS leaves 15, of which 5 are in forest pixels. Site-mean floats: 130 sites look like >=4 decimals, and 73 of them contain a record with <4 decimals (matches the reviewer).


## [new-argument] new-argument-07 — finder medium / doc-mismatch → VERDICT confirmed / medium
**Claim (3) wording: 'lowers totals by 4-15%' should read 4.1-13.0%, and the 'Asia + US footprint' is 20% Africa and Europe by area with no plots from either** (docs/handoff/scripts/exp_forest_bias.py; exp_poststrat.py exp_forest_bias.py L27-28, L35, L84; exp_poststrat.py L29, L32, L40, L81)

DESCRIPTION: The scripts report inflation = A/C − 1. The reduction from post-stratifying is 1 − C/A = 4.1% (for 4.3%) to 13.0% (for 15.0%). The README wording ('inflation of naive totals') is correct; PROMPT L24 is not. The landscape is the two boxes, which include NE Africa, Arabia, European Russia, Ukraine, Finland and others. The plots, though, are filtered to the Asia and North America continents, and non-Asian cells in the eastern box get the 'Asia' intercept. The US box also spans southern Canada and northern Mexico.

EVIDENCE: Ran .../critique/new-argument/scripts/footprint.py: point-in-polygon of 0.5-deg cell centres with Natural Earth 1:50m and Russia split at 60°E, as in build_sites_v3.py. N2c footprint area: Asia 64.8%, North America 14.0%, Africa 11.8%, Europe 7.6%, off-polygon 1.2%, Oceania 0.6%. 20.5% of the barren ('Desert') area is in Africa.

AFFECTED: PROMPT section 1 claim (3) wording; N2b/N2c/N2d totals_PgC and their domain description

FIX: Write 'naive totals exceed post-stratified totals by 4-15% (post-stratified totals 4-13% lower)'. Either restrict the landscape to the plots' continents or describe the domain as the two lon/lat boxes.

VERIFIER: Confirmed. The scripts define inflation as A/C-1 (exp_forest_bias.py L84; exp_poststrat.py L81), so the reduction from post-stratifying is 1-C/A: 4.1% to 13.0%, not 4-15%. Cells take their continent from the box they fall in (exp_forest_bias.py L48, L55; exp_poststrat.py L40, L60), while plots are restricted to Asia and North America (L28; L29). So about a fifth of the landscape is predicted with the Asia intercept and no local plots. That domain issue justifies medium; the wording fix alone would be low.

VERIFIER EVIDENCE: 1-1/1.043 = 4.1%; 1-1/1.150 = 13.0%; 1-1/1.146 = 12.7%. docs/review/2026-11-02/critique_scripts/verify-new-argument/scripts/v_footprint.py rasterises Natural Earth 1:50m countries (Russia split at 60E) onto the same 0.05-deg pixels the handoff reads, with the handoff's weights. N2c footprint by area: Asia 65.1%, North America 14.1%, Africa 11.9%, Europe 7.6%, off-polygon 0.8%, Oceania 0.6%. N2b and N2d: Africa 10.0%, Europe 9.1%. Barren (IGBP 16) area: 20.6% in Africa. These agree with the reviewer's cell-centre figures to within 0.4 pp.


## [new-argument] new-argument-08 — finder medium / bug → VERDICT confirmed / medium
**N2 Q2 plot-type effects are silently empty (substring filter bug), and pixel effects use Agriculture, not Forest, as reference** (docs/handoff/scripts/exp_plot_pixel.py L51-57)

DESCRIPTION: The filter `if "plot" in k` never matches statsmodels names such as "C(ptype, Treatment('Forest'))[T.Agriculture]", which contain 'ptype', not 'plot'. Q2_plot_type_effects_vs_forest_log is therefore {} in N2_plot_pixel.json. The only multi-class plot-effect output, the one that would show grassland ≈ forest (new-argument-04), was never produced. Q2_pixel_type_effects_log uses C(pixel)'s default alphabetical reference (Agriculture), so 'Forest 0.06' means forest vs agriculture pixels and is not comparable with plot effects vs forest.

EVIDENCE: Fitted the L51 formula on the proxy sample. Parameter names are "C(ptype, Treatment('Forest'))[T.Agriculture]" etc.; any('plot' in k) is False (.../critique/new-argument/scripts/misc_checks.py). N2_plot_pixel.json shows "Q2_plot_type_effects_vs_forest_log": {}.

AFFECTED: N2_plot_pixel.json Q2 (both dicts)

FIX: Select terms by 'ptype', assert the result is non-empty, use Treatment('Forest') for the pixel model too, and re-run Q2. Expect grassland ≈ forest.

VERIFIER: Confirmed. The filter `'plot' in k` can never match a ptype term name, so Q2_plot_type_effects_vs_forest_log is silently {}. The pixel model uses Agriculture as its reference, so 'Forest 0.06' means forest vs agriculture pixels. No document cites Q2, which puts severity on the medium/low border. Medium is kept because the suppressed output (grassland equal to forest) bears on the paper's 'forest' framing (see 04).

VERIFIER EVIDENCE: docs/review/2026-11-02/critique_scripts/verify-new-argument/scripts/v_q2_names.py fits the L51 formula. The parameter names are "C(ptype, Treatment('Forest'))[T.Agriculture]" etc.; any('plot' in k) is False and any('ptype' in k) is True. The pixel model's parameters are C(pixel)[T.Forest|Grassland|Other|Savanna|Shrubland]. Agriculture is absent because it is the reference, matching exactly the five keys in N2_plot_pixel.json. On the N2d proxy (HC3), grassland vs forest is -0.009 +/- 0.083.


## [new-argument] new-argument-09 — finder medium / bug → VERDICT confirmed / medium
**N2 Q4 R² compares models on different samples and silently drops a failed fold, so it cannot show 'plot type helps, pixel type hurts'** (docs/handoff/scripts/exp_plot_pixel.py L68, L72-78, L81-82)

DESCRIPTION: Pixel-type models use s (in-box sites only, L68). Climate and plot-type models use d (all sites of the continent), so for North America the pixel model is scored on the CONUS box only. The try/except at L72-76 swallows prediction errors, and L77-78 scores only the finite predictions, so a model can be scored on a subset without warning.

EVIDENCE: Proxy, same in-box sample, verbatim folds. North America (n=194): climate 0.256, +pixel 0.203, +plot 0.217. The handoff reports climate 0.451 (all NA) vs +pixel 0.199 (box) vs +plot 0.461 (all NA). Asia: +plot is scored on 281/383 sites because fold 1 (102 sites) holds the only Asian Savanna plot, and the PatsyError from the unseen level is swallowed. This reproduces the handoff's 0.211 (proxy 0.212), so the handoff number was very likely computed on the same subset (.../critique/new-argument/scripts/q4_fold.py, misc_checks.py).

AFFECTED: N2_plot_pixel.json Q4_r2

FIX: Score all models on one common sample, handle unseen levels explicitly (pool, or drop with a count), and remove the bare except.

VERIFIER: Confirmed, and the problem is wider than stated. The North America plot-type score (0.461) was also computed with a silently failed fold. So both 'plot type helps' numbers are scored on subsets and compared with climate-only scores on the full samples.

VERIFIER EVIDENCE: Fold check (docs/review/2026-11-02/critique_scripts/verify-new-argument/scripts/v_q4_folds.py; folds() copied verbatim; needs only coordinates and labels). Within Asia, fold 1 (105 of 387 sites; 102 of 383 with climate) holds the only Asian Savanna plot, and the resulting PatsyError is swallowed. The proxy therefore scores plot-type on 281/383 sites: R2 0.212 vs handoff 0.211. Climate-only on the same 281 sites gives 0.176, vs 0.164 on all 383, so the apparent gain falls from 0.048 to 0.036. Within North America, fold 1 (55 of 257 sites) holds both NA 'Other' plots (two Alaskan Tundra sites in the same 5-deg block), so that fold fails for the plot-type model too. On a common in-box NA sample (n=194, proxy; v_q4_na.py in the same folder): climate 0.256, +plot 0.217, +pixel 0.203 (handoff pixel score 0.199). The pixel model's Asia->Europe score also uses only the ~30 in-box European sites (Q1 count).


## [new-argument] new-argument-10 — finder medium / claim-unsupported → VERDICT confirmed / medium
**Identification: the gap is entirely plot label vs 0.05° cell label, and the same product supplies the 'true' landscape fractions; prep_log's '17-32% in same climates' and 'MCD12Q1 pixels' are misdescribed** (docs/handoff/scripts/exp_plot_pixel.py; exp_forest_bias.py; prep_log.md exp_plot_pixel.py L87-103; exp_forest_bias.py L33-47; prep_log.md L192)

DESCRIPTION: At the cell scale the sites are representative: the forest share of the cells holding sites equals the forest share of land in the same climates. All of the mismatch is between the plot label and the label of a ~30 km² 0.05° cell, not a 500-m MCD12Q1 pixel. That is equally consistent with preferential placement inside cells (the paper's mechanism) and with the product or its scale under-detecting forest. Post-stratification treats the product's fractions as truth for the landscape while treating the same product as error-prone at the plots. A referee will raise this; Phase 3's WorldCover/CCI analyses are needed before claim (1) is stated as a mechanism. Separately, 17% in prep_log is not a climate-matched value.

EVIDENCE: N2_plot_pixel.json Q3: pixel forest share at sites Asia 0.299, NA 0.304 vs landscape in the same climates 0.312, 0.268. N1: 0.352/0.309 vs peers 0.285/0.279. The climate-matched values are therefore 0.27-0.31; '17%' matches only the footprint-wide, non-climate-matched N2c X2 share (0.165). Raster profile: 0.05°, uint8, categorical (no tropical snow/ice or coastal 15/16 averaging rings; lc_artifacts.py). 47 of 433 forest plots sit in cells labelled water (19) or urban (28). Proxy Rogan-Gladen check: applying the plot-level confusion rates (sensitivity 0.415, FPR 0.055) to each cell gives a landscape forest share of 0.273 instead of 0.201, and N2b inflation 3.2% instead of 4.3% (rogan_gladen.py).

AFFECTED: PROMPT section 1 framing; prep_log section 15 '17-32%' and 'MCD12Q1 pixels'

FIX: Describe the raster as 0.05° IGBP cells (2023), correct '17-32%' to 0.27-0.31 (climate-matched), and state the product-error alternative explicitly. Do not present composition mismatch as mechanism until the 10-m/300-m analyses are done.

VERIFIER: Confirmed. Every factual sub-claim checks out. 'Equals' is approximately right: the cells holding sites are within -1 to +7 pp of their climate peers, against a 38-pp plot-cell gap. The Rogan-Gladen number is a what-if, not a correction: it assumes the plot-level confusion rates transfer to the landscape, which is itself the contested point. Medium kept.

VERIFIER EVIDENCE: N2 Q3: pixel forest share at sites 0.299 (Asia) and 0.304 (NA) vs landscape in the same climates 0.312 and 0.268. N1: 0.352/0.309 vs peers 0.285/0.279. The climate-matched forest share is therefore 0.27-0.31. The '17%' in prep_log L192 can only be N2c X2's footprint-wide 0.165 (exp_poststrat.py L62), which is not climate-matched. Raster profile: 0.05 deg, uint8, nodata None, values 0-17. legacy/src/download.py L140-147 exports MCD12Q1 LC_Type1 2023 from GEE with no scale or reducer given, so the units compared are ~5.5-km cells, not 500-m MCD12Q1 pixels. Q1: 19 + 28 of the 433 forest plots sit in water or urban cells. Rogan-Gladen what-if (docs/review/2026-11-02/critique_scripts/verify-new-argument/scripts/v_rogan.py; Se 0.415 and FPR 0.055 from the proxy N2b sample; applied per cell and clipped to [0,1]): landscape forest share 0.199 -> 0.270; inflation 4.36% -> 3.22%.


## [new-argument] new-argument-11 — finder low / doc-mismatch → VERDICT confirmed / low
**N2 crosstab JSON is transposed relative to its name: outer keys are pixel classes, inner keys are plot classes** (docs/handoff/scripts/exp_plot_pixel.py L44)

DESCRIPTION: `pd.crosstab(s.ptype, s.pixel).to_dict()` returns {pixel: {plot: n}}, but the key is named Q1_crosstab_plot_x_pixel. Read as named, "Savanna": {"Forest": 136} would mean 136 savanna plots in forest pixels; there are only 6 savanna plots. It actually means 136 forest plots in savanna cells. Also, 'Other' exists only as a pixel class; no plot is 'Other'.

EVIDENCE: Exact replication of all 36 cells (.../critique/new-argument/scripts/n2_replicate.py). The to_dict() outer keys equal the pixel classes from igbp_group.

AFFECTED: N2_plot_pixel.json Q1_crosstab_plot_x_pixel

FIX: Write long-format records (plot_class, pixel_class, n), or use orient='index' and rename.

VERIFIER: Confirmed. pd.crosstab(s.ptype, s.pixel).to_dict() returns {pixel_class: {plot_class: n}}, the transpose of what the key name says.

VERIFIER EVIDENCE: Exact Q1 replication (docs/review/2026-11-02/critique_scripts/verify-new-argument/out/log_q1.txt). The outer keys are Agriculture, Forest, Grassland, Other, Savanna and Shrubland, i.e. the igbp_group outputs. 'Other' is never a plot class in Q1. The inner keys include 'Desert', which is never a pixel class. Q1 has only 6 savanna plots, so "Savanna": {"Forest": 136} means 136 forest plots in IGBP 8/9 cells.


## [new-argument] new-argument-12 — finder low / doc-mismatch → VERDICT confirmed / low
**Samples and footprints differ across the N2 files (published crosstab ≠ headline sample; four exclusion sets); SRDB 'Desert' is mapped onto IGBP barren** (docs/handoff/scripts/exp_plot_pixel.py; exp_forest_bias.py; exp_poststrat.py; exp_poststrat_nodesert.py exp_plot_pixel.py L38-43, L92; exp_forest_bias.py L28, L44; exp_poststrat.py L29, L38, L47; nodesert L38)

DESCRIPTION: N2 Q1 (n=624) has no continent filter and includes 30 Europe, 10 Africa and 3 Oceania sites from the boxes, giving 69.4%/30.4%. The headline 68.5%/30.1% comes from N2b (n=578, Asia+NA). The excluded landscape classes are {13,15,17} in N2 Q3, {13,15,16,17} in N2b, {11,13,15,17} in N2c and {11,13,15,16,17} in N2d, so the naive totals (39.09 / 43.05 / 39.92 Pg) are not comparable. The 13 'Desert' plots sit mostly in IGBP-10 grassland cells (9/13; 1 in barren), yet the Desert class is applied to IGBP-16 barren (17% of N2c area); N2d shows this barely moves the result.

EVIDENCE: Replicated samples: Q1 continent counts {Asia 387, NA 194, Europe 30, Africa 10, Oceania 3}; IGBP codes at the 13 desert plots (n2c sample listing).

AFFECTED: N2_plot_pixel.json vs N2b/N2c/N2d comparability

FIX: Use one site sample, one footprint and one crosswalk table for all N2 outputs, and publish the crosstab for the headline sample.

VERIFIER: Confirmed, with one small numeric correction. Of the 13 Desert plots, 8 sit in IGBP-10 cells, not 9. The rest of the finding holds.

VERIFIER EVIDENCE: Exact Q1 replication. Continents: Asia 387, NA 194, Europe 30, Africa 10, Oceania 3. Q1 forest shares are 0.694/0.304, against N2b's 0.685/0.301. Exclusion sets read from the code: exp_plot_pixel.py L92 excludes {13,15,17} (and 0); exp_forest_bias.py L44 {13,15,16,17}; exp_poststrat.py L38 {11,13,15,17}; nodesert L38 {11,13,15,16,17}. Naive totals: 39.09 / 43.05 / 39.92 Pg. The 13 Desert plots sit in IGBP 10 (8), 7 (3), 16 (1) and 12 (1), so 8/13 are in grassland cells, not 9/13, and 1 is in barren. N2c 7.5%/14.6% vs N2d 7.2%/15.0% confirms that the desert mapping barely moves the result.


## [new-argument] new-argument-13 — finder low / stats-method → VERDICT confirmed / low
**Bootstrap details: few draws, a conditional skip, X1/X2 resamples not paired, map and crosswalk uncertainty excluded** (docs/handoff/scripts/exp_poststrat.py; exp_poststrat_nodesert.py; exp_forest_bias.py exp_poststrat.py L52, L75-79; exp_forest_bias.py L74)

DESCRIPTION: N2c/N2d run 300 iid draws and skip any draw lacking a class (2-3 skipped), which conditions the bootstrap on all classes being present. X1 and X2 consume consecutive parts of one RNG stream, so their resamples differ and the X2−X1 difference has no CI. N2b uses 500 draws. Percentile bounds from about 300 draws carry roughly ±0.5-1 pp Monte Carlo error. All CIs reflect plot sampling only, not land-cover or crosswalk uncertainty, and none is spatially blocked (see new-argument-04).

EVIDENCE: Code reading. n_boot 297/298/298/297 in the N2c/N2d JSONs. Proxy with 1000 draws gives N2d intervals close to the handoff's, e.g. X1 [3.7, 10.6] vs [3.7, 10.4].

AFFECTED: N2c/N2d inflation_ci; N2b CIs

FIX: Use ≥2000 draws, paired across crosswalks, a spatial-block design, and partial pooling instead of skipping. State what the CI covers.

VERIFIER: Confirmed by reading the code, and the Monte Carlo error claim is about right.

VERIFIER EVIDENCE: exp_poststrat.py creates a single rng at L15 and loops over X1 and X2 at L52. L76-79 run 300 draws per crosswalk and skip any draw missing a class: n_boot is 297/298 (N2c) and 298/297 (N2d). Because the two crosswalks consume consecutive parts of the same stream, X1 and X2 never share resamples and their difference has no CI. exp_forest_bias.py L74 runs 500 iid draws. No script uses a spatial block bootstrap. Monte Carlo error: with a bootstrap SD of about 0.035 (X2), the SE of a 2.5% percentile at B=300 is about 0.5 pp. Proxy N2d with 1000 draws: X1 [3.7,10.6] vs handoff [3.7,10.4]; X2 [7.9,21.6] vs [8.9,22.0].


### checked_ok for new-argument
- Site build: running the handoff build_sites_v3.py and cosore_aggregate.py in my scratch dir (paths changed only) reproduces build_summary.json exactly. The COSORE annual table (66 sites) is identical to /home/user/MSHI/data/derived/cosore_annual.csv; SRDB sha256 c4d7714a...2911 verified.
- N2 Q1 reproduces exactly from the rebuilt sites and committed raster: n=624, all 36 crosstab cells, plot 0.694 / pixel 0.304, agreement 0.575, 254 forest plots in non-forest pixels. N2b sample: n=581 before the WorldClim dropna (handoff 578), plot forest share 0.685 exact, pixel 0.299 (0.301), landscape 0.199 (0.198).
- The proxy re-analysis (original-pipeline site climate plus legacy atlas cell climate) reproduces handoff values: N2b plot/pixel coefficients 0.125/0.003 (0.126/0.005) with CIs within 0.01; inflation 4.33% (4.3%); N2d X1/X2 7.2%/15.1% (7.2%/15.0%); N2d landscape shares within 0.005. N2c-with-desert is not reproducible, because the atlas lacks barren cells.
- Plot-class harmonisation for the QC in-box sample is complete. SRDB Ecosystem_type values are Forest, Agriculture, Grassland, Shrubland, Desert, Savanna, Tundra and Bare; Wetland/Urban are removed by QC; Peatland is absent from QC. The COSORE strings missing from the N2b/N2c maps (Woody savanna, Deciduous needleleaf forest, Evergreen needleleaf plantation) never become a site label because the SRDB mode wins, and the 4 Tundra sites are outside the boxes. The alphabetical mode tie-break (build_sites_v3.py L98) touches 27 sites; forest share is 0.685 by mode, 0.678 record-weighted and 0.680 as site-mean fraction, an immaterial difference.
- Land-cover raster: 0.05°, uint8, categorical, with no code-averaging artefacts (no snow/ice in the tropics, no coastal 15/16 rings). Its top edge at 87.874° makes the window reads in N2b/N2c sit 0.024° north of the assumed latitudes, but no pixel changes 0.5° cell, so there is no effect.
- Landscape composition mechanics: counting 0.05° pixels per 0.5° cell, area = cos(lat) × (0.5°)² × included-pixel fraction, and the n≥20 rule, which drops only 0.75% of included area, are all correct.
- Duan smearing per model: the A and C factors are nearly equal (1.1522 vs 1.1525), so per-model smearing alone does not drive A vs C. The problem is between-class heteroscedasticity (new-argument-02).
- Site centroid vs record coordinates: the IGBP 1-5 share among forest-labelled QC records is 0.449 at record coordinates vs 0.450 at site centroids; 2.9% change cell; maximum record-to-centroid distance is 8 km (99th percentile 3.9 km).
- Temporal mismatch with 2023 land cover does not explain the mismatch: forest plots with study year before 2000 are in IGBP 1-5 cells 45% of the time, vs 46% for 2000-09 and 36% for 2010+.
- N1 (exp_selection_bias.py): the JSON matches prep_log section 15. The NPP raster has no MODIS fill values (max 24,455; NaN outside the footprint), so the npp>0 filter is valid. 466/581 in-box sites are kept, with NPP-masked cells excluded consistently for sites and peers. Peers are area-uniform (arcsin sampling). The full-cell area in Q3 does not affect the ratio. README '2-3% inflation' corresponds to JSON values of 1.6-3.0%.
- Results JSONs match the quoted numbers: N2b 0.685/0.301/0.126 [0.009, 0.244]/0.005 [-0.097, 0.106]/4.3% [0.3, 8.8]; N2c 7.5%/14.6%; N2d 7.2%/15.0%; N1 median ranks and ratios. No JSON or script supports the '≈10 m' sentence or the '3-13 Pg' figure.
- /home/user/MSHI was not modified; git status is clean. All scripts and outputs are in docs/review/2026-11-02/critique_scripts/new-argument/ (scripts/, out/).


## [transfer-noise] transfer-noise-01 — finder high / claim-unsupported → VERDICT confirmed / high
**'Transfer penalty <= 0.09 R2' holds only for leave-one-continent-out; pairwise penalties reach 0.18 (OLS-TP) and 0.24 (XGB), and none has uncertainty** (exp_matrix.py (results E6_matrix_OLS-TP.json, E6_matrix_XGB.json; claims at prep_log.md:186, README.md:39, PROMPT_mshi_v3.md:20) exp_matrix.py:30-34, 47-57; prep_log.md:96, 186)

DESCRIPTION: The README's E6 headline, the prep_log §14 'Reading' and PROMPT §1 say the transfer penalty (within-continent minus cross-continent R2) is small (<= 0.09) and zero for Europe. In the JSONs that holds only for LOCO. OLS-TP penalties are Asia +0.038, Europe -0.030, NA +0.088; XGB penalties are +0.048, -0.113, +0.048. For the selected OLS-TP model, two of the six pairwise transfers among the three continents that have a within-CV benchmark exceed 0.09. Asia->NA: within-NA 0.451 vs 0.348, penalty +0.103. NA->Asia: within-Asia 0.163 vs -0.015, penalty +0.178, so the NA-trained model has no skill in Asia. For XGB, Europe->NA is +0.238 and Europe->Asia +0.220. prep_log §3 (line 96) itself says US->Asia transfer 'is asymmetric and fails in that direction'. In addition: (a) each within-continent benchmark is a single fold assignment (seed 42, pooled out-of-fold R2) with no CI, and no penalty has a CI. (b) The Europe penalties are negative: OLS -0.02 to -0.03, XGB -0.04 to -0.11. A within-CV model trained on about 4/5 of 235 sites, with whole 5-degree blocks held out, scores below models trained on another full continent (384 or 257 sites). So the within benchmark is not an upper reference, and 'zero for Europe' mixes training-set size and 5-degree-block extrapolation with any continent effect.

EVIDENCE: Computed from the two E6 JSONs (docs/review/2026-11-02/critique_scripts/transfer-noise/code/penalty.py). OLS-TP, written as target: within / LOCO / pairwise. Asia: 0.163 / 0.125 / Europe->Asia 0.086, NA->Asia -0.015. Europe: 0.058 / 0.088 / Asia->Europe 0.079, NA->Europe 0.088. NA: 0.451 / 0.363 / Asia->NA 0.348, Europe->NA 0.471. XGB, same layout. Asia: -0.001 / -0.049 / Europe->Asia -0.221, NA->Asia -0.034. Europe: -0.157 / -0.044 / -0.053, -0.119. NA: 0.375 / 0.327 / 0.361, 0.137. In RMSE (log), the OLS-TP pairwise penalties are at most +0.059 (NA->Asia, about +10% of within RMSE) and +0.045 (Asia->NA).

AFFECTED: README E6 headline; prep_log §14 'Reading'; PROMPT §1 'The transfer penalty between continents is small'; planned Figure 5 (transfer matrix with within-continent benchmark)

FIX: Restrict the statement to LOCO, or report the full pairwise penalty table including the NA->Asia failure. Compute penalties as paired differences on the same test sites, with spatial-block bootstrap CIs and >= 3 fold seeds, in both R2 and RMSE. Control for training-set size (subsample transfer training sets to the within-CV training size) before calling any penalty 'zero'.

VERIFIER: The '<= 0.09 R2 / zero for Europe' reading matches leave-one-continent-out (LOCO) exactly. OLS-TP LOCO penalties are Asia +0.038, Europe -0.030, NA +0.088. It does not hold for the pairwise matrix that the README E6 headline labels. For the selected OLS-TP model, Asia->NA is +0.103 and NA->Asia is +0.178 (NA->Asia R2 -0.015, so no skill in Asia). Asia->NA 0.348 is quoted on prep_log line 184 itself, two lines above the '<= 0.09' reading on line 186, so the log contradicts itself. XGB: Europe->NA +0.238, Europe->Asia +0.220. There is no uncertainty on any of these numbers. exp_matrix.py:53 calls folds(u) with the default seed 42 (line 30). The benchmark is a single pooled out-of-fold R2, and no bootstrap exists anywhere in the script. Sub-point (b) also holds. Europe within-CV trains on about 4/5 of 235 sites and must extrapolate to held-out 5-degree blocks. Models trained on 384 or 257 sites from another continent beat it (OLS -0.021/-0.030; XGB -0.104/-0.038; XGB LOCO -0.113). So 'zero for Europe' mixes training size and block extrapolation with any continent effect. Mitigating facts: in RMSE the OLS-TP pairwise penalties are at most +0.059 (+10.0%) and +0.045 (+9.0%), and the LOCO statement is literally correct. Within-CV and transfer are already scored on identical test-site sets, so only the paired uncertainty is missing. Severity: E6 is labelled supporting/exploratory, so medium would be defensible if the claim were dropped. As written, it is the README headline and PROMPT §1's 'transfer penalty between continents is small', and the paper's own planned Figure 5 contradicts it. I keep high.

VERIFIER EVIDENCE: Script docs/review/2026-11-02/critique_scripts/verify-transfer-noise/code/v_penalty.py reads both E6 JSONs.

OLS-TP (within R2 / LOCO penalty / pairwise penalties):
- Asia: within 0.163, LOCO pen +0.038. Europe->Asia +0.077 (dRMSE +4.4%), NA->Asia +0.178 (dRMSE +0.059, +10.0%).
- Europe: within 0.058, LOCO -0.030. Asia->Eu -0.021, NA->Eu -0.030.
- NA: within 0.451, LOCO +0.088. Asia->NA +0.103 (dRMSE +0.045, +9.0%), Europe->NA -0.020.

XGB:
- Asia: within -0.001, LOCO +0.048. Europe->Asia +0.220, NA->Asia +0.033.
- Europe: within -0.157, LOCO -0.113. Asia->Eu -0.104, NA->Eu -0.038.
- NA: within 0.375, LOCO +0.048. Asia->NA +0.014, Europe->NA +0.238.

Code and text checked: exp_matrix.py:30-34 and 51-57 (single fold seed 42, pooled OOF R2, no CI); prep_log.md:96 ('asymmetric and fails in that direction'); prep_log.md:184-186; README.md:39.


## [transfer-noise] transfer-noise-02 — finder medium / stats-method → VERDICT confirmed / medium
**E1 site-mean ceiling (0.84) treats records as independent replicates and pools continents; per-continent ceilings that account for study clustering are 0.66-0.85** (exp_noise_ceiling.py 25-33, 43-47)

DESCRIPTION: ceiling_r2_site_mean_target = s2b/(s2b + mean(s2w/n_i)) uses a pooled one-way ANOVA and assumes the records at a site are independent replicates. N3 shows a study-level effect (about 16% of variance) shared by all records of a study, which does not average out as records from that study accumulate. So s2w/n_i overstates how reliable site means are; for example, 10 records from one study give noise 0.0704 + 0.0684/10 = 0.077, not 0.0097. Recomputing with the 3-level REML components and each site's actual study composition (noise_i = s2_study*sum_j(m_ij/n_i)^2 + s2_rec/n_i; COSORE datasets as their own studies) gives these QC ceilings. Pooled: 0.744 (E1 reports 0.838). Asia 0.697 (E1-style 0.825), Europe 0.658 (0.732), NA 0.848 (0.896). The single-record ICC also depends on the estimator: ANOVA 0.745, one-way REML 0.778, independent-study 3-level 0.678. Pooling continents adds only about 0.015 to s2b (0.284 pooled vs a site-weighted per-continent mean of 0.269), but the pooled 0.84 does not apply to Europe, the locked-test continent. The components are fitted on multi-record sites only (605 of 971). Applied to the 366 singleton sites, they under-predict observed single-record variance: observed 0.456, vs 0.381 implied by E1 and 0.431 by the 3-level model; NA singletons 0.575 vs 0.355 / 0.443. Extending the ceiling to singletons is therefore an untested assumption. The 'noise' also includes plot-type signal: within-site pairs with different SRDB Ecosystem_type (17% of pairs) have semivariance 0.193 vs 0.092 for same-type pairs, and 76 sites mix forest and non-forest records. The ceiling therefore applies to predictors that are constant within 5 km (gridded climate); it is not a measurement-noise ceiling. That matters because the paper's main argument is that plot type carries signal. The quoted ICC range 0.62-0.82 happens to sit close to the corrected site-mean ceilings, so 'far below the ceiling' survives; the pooled 0.84 and the meaning of 'ceiling' need correcting.

EVIDENCE: Rebuilt records and sites from raw SRDB + COSORE (own run of the cosore_aggregate logic: 66 sites) + Natural Earth with the unmodified build_sites_v3.py; build_summary.json reproduced exactly. Reran exp_noise_ceiling.py and exp_reproducibility.py unmodified: all 96 and 76 JSON values reproduced exactly. Then ran docs/review/2026-11-02/critique_scripts/transfer-noise/code/probe_ceiling.py (output out/ceilings.json, also holding the repo-filter variant) and code/probe_misc.py (singleton variance and ecosystem-type pair split).

AFFECTED: prep_log §12 E1 ('ceiling R2 ≈ 0.75 single record, ≈ 0.84 site mean'); §14 'far below the noise ceiling (ICC 0.62-0.82)'; PROMPT §1; Phase 2 item 3; ceiling lines in Figure 5

FIX: Report per-continent ceilings for the actual target (site means) from a 3-level REML with each site's study composition, in both 'independent study' and 'same study' versions, with site-cluster bootstrap CIs. Do not use pooled ceilings for within-continent comparisons. State the singleton-extrapolation assumption. Define the ceiling as applying to predictors constant within a 5-km site.

VERIFIER: I fitted the models independently and every number in the finding reproduced exactly. One-way ANOVA (exp_noise_ceiling.varcomp) vs 3-level REML with each site's actual study composition, noise_i = s2_study*sum_j(m_ij/n_i)^2 + s2_rec/n_i, with COSORE datasets as their own studies. An extra check favours the 3-level model. The observed variance of the actual site-mean target across all 971 QC sites is 0.407. The 3-level components imply 0.393; E1's independence assumption implies only 0.339, so E1 under-states noise. Putting the observed variance in the denominator gives 0.752 (3-level) vs 0.865 (E1-style). The singleton comparison, the ecosystem-type pair split and the 76 mixed forest/non-forest sites all reproduce, and they hold with SRDB records only. The qualitative 'far below the ceiling' survives: within-CV R2 is 0.06-0.45 against corrected ceilings of 0.66-0.85. The pooled 0.84, its use for Europe, and the meaning of 'ceiling' need correcting. Medium is appropriate.

VERIFIER EVIDENCE: Data rebuild:
- COSORE aggregation (path-patched copy, docs/review/2026-11-02/critique_scripts/verify-transfer-noise/code/cosore_aggregate.py): 66 sites, 24 RDS unreadable; md5 identical to both other reviewers' CSVs.
- Unmodified build_sites_v3.py: build_summary.json identical to the handoff.
- Unmodified exp_noise_ceiling.py and exp_reproducibility.py: 0 differences vs E1/N3 JSON (96 and 90 leaf values).

Ceilings from docs/review/2026-11-02/critique_scripts/verify-transfer-noise/code/v_ceiling.py (all fits converged):
- Pooled: E1 0.838 vs 3-level 0.744. Mean noise 0.0549 vs 0.1007.
- Asia: 0.825 vs 0.697.
- Europe: 0.732 vs 0.658.
- NA: 0.896 vs 0.848.
- Single-record ICC: ANOVA 0.745, one-way REML 0.778, 3-level independent-study 0.678.
- 10 records from one study: noise 0.0772 vs E1 0.0097.

Singletons (366 sites): observed variance 0.4559, vs implied 0.3809 (E1) and 0.4315 (3-level). NA singletons 0.5748 vs 0.3546 / 0.4427.

From docs/review/2026-11-02/critique_scripts/verify-transfer-noise/code/v_ceiling2.py:
- Observed variance of the site-mean target 0.4067 vs implied 0.3934 (3-level) and 0.3387 (E1).
- Ecosystem-type pairs: 3,392 of 19,883 differ (17.1%); semivariance 0.1932 (different type) vs 0.0915 (same type). SRDB-only: 15.6%, 0.2004 vs 0.0916.
- 76 sites mix forest and non-forest records (75 with SRDB only).
- Site-weighted mean of per-continent s2b from the E1 JSON is 0.2685, vs pooled 0.2838.


## [transfer-noise] transfer-noise-03 — finder medium / stats-method → VERDICT confirmed / medium
**Pair-based semivariances are dominated by a few sites, and N3's iid-pair bootstrap CIs are 4-8x too narrow** (exp_reproducibility.py (also exp_noise_ceiling.py) exp_reproducibility.py:32-55; exp_noise_ceiling.py:49-57)

DESCRIPTION: Each site contributes n(n-1)/2 pairs. The 10 largest of the 605 multi-record sites supply 46% of all within-site pairs and 60% of N3's different-study pairs. N3 bootstraps pairs as if independent (line 53), although pairs share sites and records. With a site-cluster bootstrap, different-study semivariance is 0.136 [0.099, 0.180], against the reported [0.131, 0.141]; same-study is 0.073 [0.058, 0.088], against [0.069, 0.077]. The qualitative conclusion survives: diff-minus-same is [0.027, 0.103]; site-weighted means are 0.141 vs 0.062; among the 177 sites with both pair types, 71% have diff > same (median ratio 1.85). The sub-categories are fragile: 'diff_study_same_year_same_method_same_ecosystem' (0.098, 564 pairs) comes from 66 sites, one of which contributes 31% of the pairs (top 3: 47%). E1's 'within-site variance mostly plot-to-plot' rests on same-year vs different-year pair semivariance (0.095 vs 0.113; top 5 sites supply 38% of different-year pairs). The point estimates support it, but the site-cluster CI for the year component (diff-year minus same-year) is [-0.017, 0.051]; its upper end is about half the within-site variance. 'Same-year' pairs also mix different studies (N3: different-study same-year 0.142 vs same-study same-year 0.084).

EVIDENCE: docs/review/2026-11-02/critique_scripts/transfer-noise/code/probe_records.py, probe_pairs.py and probe_pairs2.py (1,000-draw site-cluster bootstrap, seed 0), run on the rebuilt QC records, which reproduce the N3 pair counts exactly (8,422 same-study and 11,056 different-study pairs).

AFFECTED: N3_reproducibility.json CIs (all categories); prep_log §15 N3; README N3 headline (point values are correct); prep_log §12 E1 'mostly plot-to-plot'

FIX: Report site-weighted or within-site paired contrasts with site-cluster bootstrap CIs. For each category, give the number of contributing sites and the largest single-site share. Hedge the 'plot-to-plot' wording.

VERIFIER: Every number reproduces exactly on SRDB-only QC records, which match the N3 pair counts (8,422 same-study / 11,056 different-study). exp_reproducibility.py:52-53 resamples pairs as if independent. Pairs share sites and records, so a site-cluster bootstrap is needed. The iid intervals are 3.6x (same-study) to 8.3x (different-study) too narrow. The qualitative contrast survives: the cluster CI of the difference excludes 0, site-weighted means are 0.141 vs 0.062, and 71% of the 177 sites with both pair types show diff > same. The sub-category CI widens from [0.079, 0.119] to [0.062, 0.147]. E1's 'mostly plot-to-plot' rests on a year contrast whose cluster CI includes 0 and reaches about half the within-site variance (0.051 / 0.097). The JSON CIs are wrong and one prep_log phrase needs hedging, so medium.

VERIFIER EVIDENCE: Script: docs/review/2026-11-02/critique_scripts/verify-transfer-noise/code/v_pairs.py (1,000-draw site-cluster bootstrap, seed 0).

N3 concentration:
- Different-study pairs: 206 sites; top 1 site 14.2%, top 3 33.9%, top 10 60.4%.
- Same-study pairs: 566 sites; top 10 35.0%.
- E1 data: 605 multi-record sites, 19,883 within-site pairs; top 10 sites hold 45.9%.

Site-cluster CIs vs reported iid CIs:
- Different-study: [0.0986, 0.1804] vs [0.1307, 0.1406].
- Same-study: [0.0582, 0.0880] vs [0.0690, 0.0772].
- Diff minus same: [0.027, 0.1027].

Site level: site-weighted means 0.1412 vs 0.0616. 177 sites have both pair types; 70.6% have diff > same; median ratio 1.846.

Sub-category 'diff_study_same_year_same_method_same_ecosystem': 564 pairs from 66 sites; top site 30.7%, top 3 47.3%; cluster CI [0.0621, 0.1467].

E1 year split: same-year 4,423 pairs (0.0949), different-year 14,979 pairs (0.1126); top 5 sites hold 37.8% of different-year pairs. Cluster CI for different-year minus same-year: [-0.0169, 0.0508].


## [transfer-noise] transfer-noise-04 — finder medium / reproducibility → VERDICT confirmed / medium
**XGB numbers in E2/E3/E4/E6 were not produced with the pinned xgboost 2.1.4 and change when rerun; E5's version is unrecorded** (exp_ablation.py, exp_shift.py, exp_matrix.py, exp_global_aoa.py exp_ablation.py:16-31, 60-65; exp_matrix.py:11-12)

DESCRIPTION: The README says E2/E3/E4/E6-XGB ran under xgboost 3.4.1. E5 also uses XGB, and its version is not recorded anywhere. I reran E4's 'original_sites|original_features' row verbatim under 2.1.4: same committed tables, same fit_score/ci code, with the bootstrap RNG advanced through the four earlier ci() calls (n_test 326, 240, 326, 240) so the bootstrap draws match. Result: R2 0.128 [0.000, 0.230], 5-seed mean 0.122 (seeds 0.115-0.128). The JSON has 0.131 [0.021, 0.228], seed mean 0.135, so the CI lower bound drops from clearly positive to zero. Independently, E6_matrix_XGB gives Asia->Europe = -0.053, while clean_test_europe.json (run under 2.1.4) gives -0.0506 for the same C8 XGB model, data, row order and seed. The version shift (0.003-0.013 here; 0.022 for F in prep_log §1) is as large as or larger than the differences these runs are used to interpret, e.g. E3's 0.367 vs 0.375.

EVIDENCE: docs/review/2026-11-02/critique_scripts/transfer-noise/code/e4_orig_rngsync.py run with xgboost 2.1.4 on critique_inputs/processed/training_features_v2.parquet + us_validation_features_v2.parquet; the clean_test value comes from results/clean_test_europe.json all_candidates_on_test.

AFFECTED: E2_E3_shift.json, E4_ablation.json, E4b_regions.json, E6_matrix_XGB.json, E5_global_aoa.json (version unknown); every XGB number quoted in prep_log §12/§14; Phase 2 reruns will not match the handoff values

FIX: Rerun every XGB experiment under 2.1.4 with seed ensembles. Write the package versions into each results JSON. Stop quoting the 3.4.1 numbers, and treat any comparison smaller than the seed/version spread as null.

VERIFIER: I reran the E4 'original_sites|original_features' row under the pinned xgboost 2.1.4. I used the verbatim fit_score/ci code (exp_ablation.py:16-31) and advanced the default_rng(1) bootstrap stream through the four earlier ci() calls (n 326, 240, 326, 240), so the bootstrap draws match the original run. The point estimate, the 5-seed mean and the CI lower bound all differ from the JSON. The CI lower bound falls from 0.021 to 0.000. The E6 vs clean_test mismatch (-0.053 vs -0.0506) arises for identical rows, row order, parameters and seed. I ruled out the one code difference, input dtype (float64 DataFrame in exp_matrix vs float32 ndarray in clean_test): under 2.1.4 the two give bit-identical predictions. That leaves the version difference stated in README line 26. E5 (exp_global_aoa.py:38-39) uses XGB, and no version is recorded for it in README line 26 or in any results JSON. Caveat: I cannot install 3.4.1 to show that it reproduces the JSON values; that attribution rests on the README. The shifts (0.003 point, 0.013 seed mean, 0.022 for F in prep_log §1) are comparable to differences the log interprets, such as E3's 0.367 vs 0.375. The README already discloses the 3.4.1 use, so this is reproducibility of secondary numbers: medium, not high.

VERIFIER EVIDENCE: Script docs/review/2026-11-02/critique_scripts/verify-transfer-noise/code/v_e4_orig.py, run with xgboost 2.1.4 on critique_inputs/processed/training_features_v2.parquet + us_validation_features_v2.parquet (n 600/272).
- With RNG synced: r2 0.128, CI [0.0, 0.23]; seeds 0-4 = 0.1276, 0.1228, 0.1172, 0.1272, 0.1151 (mean 0.122).
- With a fresh RNG: CI [-0.005, 0.23].
- E4_ablation.json: 0.131 [0.021, 0.228], seed mean 0.135.

Script docs/review/2026-11-02/critique_scripts/verify-transfer-noise/code/v_dtype.py: max |pred(float64 DataFrame) - pred(float32 ndarray)| = 0.0.

clean_test_europe.json all_candidates_on_test C8/XGB r2 -0.050592, vs E6_matrix_XGB Asia->Europe -0.053. Both use 384 Asia / 235 Europe rows, the same params and random_state 0 (exp_matrix.py:11-13, 19; clean_test.py:20-25, 43-49, 80-85).

grep: no xgboost version appears in any results/*.json; README.md:26 omits E5.


## [transfer-noise] transfer-noise-05 — finder medium / claim-unsupported → VERDICT confirmed / medium
**E4's 'site-mean vs single-record target: no change' holds for continents only; with boxes the target moves R2 by 0.07-0.09** (exp_ablation.py 55-58, 70-75; prep_log.md:168)

DESCRIPTION: In E4_ablation.json the target makes no difference with continents (y_mean 0.325 vs y_single 0.328). With the original bounding boxes, on the same sites and features, y_mean gives 0.069 [-0.104, 0.203] and y_single gives 0.155 [0.010, 0.258] (seed means 0.072 vs 0.122). On the original sites with v3 features, swapping to the v3 site-mean target lowers R2 from 0.113 to 0.047. The box setting is the original configuration E4 was meant to explain. There, the site-mean target lowers transfer R2, and no paired comparison was run.

EVIDENCE: Values read directly from E4_ablation.json. Both target arms use identical site rows, box membership and features (exp_ablation.py:47-58), so only the target differs.

AFFECTED: prep_log §12 E4 sentence; any paper statement that the v3 target definition does not matter or explains the improvement

FIX: Report all three target contrasts with paired bootstrap CIs and seed spread, rerun under xgboost 2.1.4, and replace 'no change' with a statement that the effect depends on the region definition.

VERIFIER: The JSON values are as stated. exp_ablation.py:47-58 builds both target arms from the same 'sites' frame: same box/continent masks and the same features sampled at the first record's coordinates. fit_score's dropna leaves identical rows (n 525/240 in both box arms). So only the target differs, and no paired test was run. prep_log line 168's 'site-mean vs single-record target: no change' therefore holds only for continents. One correction to the title: '0.07-0.09' is the seed-0 difference (0.086 for boxes, 0.066 for original sites with v3 features). The 5-seed-mean differences are 0.050 and 0.042. Seed 0 is the high draw for y_single|boxes (0.155 vs a seed mean of 0.122), and the CIs overlap broadly. The accurate wording is 'no change with continents; inconclusive with boxes (single-record target higher by about 0.05 on seed means, unpaired)'. The direction (the single-record target scores higher in boxes) does not undermine E4's main message that the test region drives R2. Medium as a description issue, at the low end.

VERIFIER EVIDENCE: E4_ablation.json:
- y_mean|continents 0.325 [0.23, 0.405], seed mean 0.318.
- y_single|continents 0.328 [0.248, 0.396], seed mean 0.322.
- y_mean|boxes 0.069 [-0.104, 0.203], seed mean 0.072.
- y_single|boxes 0.155 [0.010, 0.258], seed mean 0.122.
- original_sites|v3_features 0.113, seed mean 0.098, vs the same with site_mean_target 0.047, seed mean 0.056.

Code: exp_ablation.py:26-31 (fit_score: single seed-0 point plus 5-seed mean, unpaired CI), 47-58 (shared site rows and features for both targets); prep_log.md:168.


## [transfer-noise] transfer-noise-06 — finder medium / claim-unsupported → VERDICT confirmed / medium
**E3's 'no detectable concept shift' and 'slopes equal across continents except NPP' are not supported** (exp_shift.py 51-72; prep_log.md:167)

DESCRIPTION: (i) Asia-trained 0.367 vs NA-trained spatial CV 0.375 are single-seed point estimates with no CI, produced under xgboost 3.4.1. Seed spread for comparable XGB transfer R2 was about 0.05 in prep_log §1. The NA-trained model is fit on about 4/5 of 256 sites and is itself extrapolating across 5-degree blocks, while the Asia model uses 380 sites, so similar R2 values do not isolate P(y|x). (ii) Non-significance is not equality: the interaction CIs are wide relative to the slopes. For lnP, the Asia slope is 0.185 and the NA-minus-Asia difference is [-0.168, 0.206], so the NA slope could be anywhere from 0.02 to 0.39. For bio01, 0.156 with a difference of [-0.091, 0.179]. (iii) 'Except NPP (p = 0.02)' is the smallest of five interaction p-values (0.022) and fails a Bonferroni/Holm threshold of 0.01.

EVIDENCE: E2_E3_shift.json E3_pooled_interactions (HC3 OLS, n = 635); exp_shift.py:58-63 (single fold seed 42, one XGB seed).

AFFECTED: prep_log §12 E3; README E2/E3 headline 'Asia-trained 0.367 vs NA-trained 0.375'

FIX: Bootstrap the Asia-trained minus NA-trained difference on the same NA sites with a seed ensemble. Report slope ratios with CIs, or an equivalence test, and apply a multiplicity correction. Say 'no evidence of concept shift, but low power to detect slope differences up to about 2x'.

VERIFIER: (i) Confirmed from code. The NA benchmark (exp_shift.py:59-62) uses one fold assignment, folds(u) with default seed 42 (line 25), and one XGB seed (P random_state 0, line 16), with no CI. The Asia-trained value (line 53) is likewise a single seed. README:26 says these ran under 3.4.1. The comparison mixes training size: Asia 380 sites vs NA-CV about 4/5 of 256 sites, which must extrapolate across held-out blocks. prep_log §1 shows 20-seed XGB ranges of 0.044-0.058. (iii) Confirmed: the five interaction p-values are 0.523, 0.839, 0.351, 0.619 and 0.022, and the Holm/Bonferroni first threshold is 0.05/5 = 0.01, so NPP does not survive. (ii) Correct in substance, with one overstatement. The formula is fully interacted, so the pooled fit equals separate per-continent fits and HC3 makes b_NA and b_Asia independent. SE(b_NA) = sqrt(SE_int^2 - SE_Asia^2) = sqrt(0.0954^2 - 0.0732^2) = 0.061, so the NA lnP slope is 0.204 [about 0.08, 0.32], not 'anywhere from 0.02 to 0.39'. Still, the difference CI [-0.168, 0.206] does not exclude the slopes differing by up to about 100% of the Asia slope. 'Slopes equal' is not supported, and 'no evidence of a difference, low power' is the right wording. This is how a secondary result must be described, so medium.

VERIFIER EVIDENCE: E2_E3_shift.json E3_pooled_interactions:
- lnP_z 0.185 [0.041, 0.328]; lnP_z:C(cont)[T.NA] 0.019 [-0.168, 0.206].
- bio01_z 0.156; interaction [-0.091, 0.179].
- lnNPP interaction p = 0.022; other interaction p-values 0.523, 0.839, 0.351, 0.619.
- E3_unweighted 0.367 vs E3_NA_within_spatialCV 0.375.

NA-slope SE derived from the reported HC3 CIs (half-width / 1.96).

Code: exp_shift.py:16, 25-29, 53, 59-62, 69. prep_log.md:35 (seed ranges) and :167.


## [transfer-noise] transfer-noise-07 — finder medium / stats-method → VERDICT confirmed / medium
**Skill vs the training-mean baseline credits transfer models for fixing the between-continent mean offset, so it is not comparable with within-continent skill** (exp_matrix.py 25-27, 46, 50, 55-57; prep_log.md:168)

DESCRIPTION: skill = 1 - RMSE/RMSE(training-mean prediction). In within-CV, the baseline is the target continent's own training-fold mean. In transfer, it is another continent's mean, which is biased for the target. Skill can therefore be positive while R2 is strongly negative: OLS-TP South America->Europe has R2 -0.308 and skill +0.072; South America->Asia -0.013 and +0.083. Four OLS-TP pairs disagree in sign between R2 and skill. For Europe, transfer skill (0.059-0.089) is up to 2.6x the within-CV skill (0.034), while the R2 values differ by <= 0.03. With a target-mean baseline (= 1 - sqrt(1 - R2)), NA->Europe skill would be 0.045, not 0.089. prep_log line 168 recommends 'always report RMSE + skill vs constant' as the comparable metric; with this baseline it is not comparable across settings.

EVIDENCE: Computed from E6_matrix_OLS-TP.json (docs/review/2026-11-02/critique_scripts/transfer-noise/code/penalty.py and the inline skill comparison).

AFFECTED: E6 skill columns; any within-vs-transfer comparison made in skill units (Phase 2 item 1 mandates training-mean skill)

FIX: Keep training-mean skill as an operational baseline, but also report target-mean skill (1 - sqrt(1 - R2)) or an MSE decomposition into bias^2 and the rest. Never compare training-mean skill between within-CV and transfer.

VERIFIER: Code confirmed. In transfer, the skill baseline is the training continent's mean (exp_matrix.py:25-27, called with a.log_rs.mean() at lines 46 and 50). In within-CV it is the target continent's own training-fold mean (lines 55-56). In transfer, the baseline RMSE therefore includes the between-continent mean offset, and skill rewards removing it. I enumerated all OLS-TP entries: exactly four have R2 and skill of opposite sign. The target-mean conversion 1 - sqrt(1 - R2) is exact for an R2 computed around the target mean. One minor imprecision: 'R2 values differ by <= 0.03' holds for Asia->Europe, NA->Europe and LOCO, but not SA->Europe (skill 0.072, R2 -0.308), which sits inside the quoted 0.059-0.089 skill range. No current headline compares skill across settings. The issue affects the E6 skill column and the prep_log:168 / Phase-2 item 1 recommendation to use training-mean skill as the comparable metric. Medium, not high.

VERIFIER EVIDENCE: Script docs/review/2026-11-02/critique_scripts/verify-transfer-noise/code/v_penalty.py on E6_matrix_OLS-TP.json.

Sign disagreements (R2, skill): Europe->Africa (-0.005, +0.001), NA->Africa (-0.013, +0.005), SA->Asia (-0.013, +0.083), SA->Europe (-0.308, +0.072). No LOCO or within-CV entries disagree.

Target-mean vs training-mean skill:
- NA->Europe: 0.045 vs 0.089.
- Asia->Europe: 0.040 vs 0.059.
- Europe within-CV: 0.029 vs 0.034.

Europe NA->Europe skill / within skill = 0.089 / 0.034 = 2.6.


## [transfer-noise] transfer-noise-08 — finder medium / stats-method → VERDICT confirmed / medium
**E5's 87.3 Pg C/yr is exp(log prediction) with no retransformation correction, and the grid includes ice-sheet and barren cells** (exp_global_aoa.py 18-26, 42-43, 60-61, 75-77)

DESCRIPTION: rs = exp(pred) is a median/geometric-mean prediction from a log-space model; a total needs the mean, i.e. a smearing factor (Duan; exp(sigma^2/2) for lognormal residuals). With out-of-sample log RMSE for the same XGB-C8 model of 0.535-0.643 (E6 within-CV), that factor is 1.15-1.23, i.e. roughly 100-107 Pg instead of 87.3 [estimate; assumes lognormal residuals of that size; an in-sample Duan factor would be smaller]. Area and flux fractions are unaffected only if residual variance is homogeneous. The grid is every WorldClim land cell from -60 to 84 N with no mask; line 26 (bio05 > -50) removes nothing physically plausible. Greenland alone is 1.6% of the grid's land and 23.1% of the Arctic band (66.5-84 N), using Natural Earth 1:50m as a proxy for the WorldClim mask. Barren land is 14.8% of land in the MODIS IGBP footprint. These cells receive predictions and count in the total and in the area denominators. The 'Arctic 24% outside the AOA' may therefore be largely ice sheet [inference; DI cannot be recomputed without WorldClim]. DI is also only weakly tied to error in the one test available: NA RMSE by DI tercile is 0.536 / 0.513 / 0.573; outside the AOA, RMSE is 0.749 vs 0.517 (n = 22) but R2 is 0.461 vs 0.307. The xgboost version for E5 is unrecorded.

EVIDENCE: Code reading (lines cited); E5_global_aoa.json; docs/review/2026-11-02/critique_scripts/transfer-noise/code/probe_misc.py step (5) for the Greenland shares; IGBP shares from critique_inputs/modis/landcover_igbp_2023.tif (area-weighted class 16 / land cells).

AFFECTED: prep_log §12 E5 '87.3 Pg C/yr', 'Arctic 24%'; README E5 headline (fractions)

FIX: Apply and report a smearing correction (out-of-fold residuals) or label the total as median-based; mask permanent ice and report barren land separately; give area fractions both with and without ice. Do not quote 87.3 Pg as a global Rs estimate. Record the xgboost version.

VERIFIER: Code confirmed. exp_global_aoa.py:60 sets rs = exp(pred) from a log-space model and sums it at line 61 with no retransformation, so the total is median-based. The grid (lines 18-24) is every WorldClim cell from -59.75 to 83.75 N with valid values. Line 26 (bio05 > -50) cannot remove ice sheets, because bio05 is the warmest-month maximum and is far above -50 C on Greenland. I reproduced the Greenland and IGBP barren shares exactly. The smearing arithmetic is right. The finding labels the range as an assumption-laden estimate: the right sigma^2 lies between the in-sample residual variance and the OOS MSE. The DI/error numbers are as in the JSON. I could not test the 'Arctic 24% outside is largely ice sheet' inference without WorldClim, and the finding labels it as inference. A possible extra impact, unverified: PROMPT §1's '3-13 Pg C/yr' equals 4.3-15% of about 87 Pg (15.0% x 87.3 = 13.1). If it was derived from this total, the missing correction biases that headline too, but no script computes it. Medium as stated.

VERIFIER EVIDENCE: Script docs/review/2026-11-02/critique_scripts/verify-transfer-noise/code/v_e5grid.py: 0.5-degree centres as in line 18, cos-lat area as in line 25, Natural Earth 1:50m countries as the land proxy, Antarctica excluded.
- 61,534 land cells.
- Greenland: 0.0160 of grid land area, 0.2313 of the Arctic band (66.5-84], 2.16 M km2.
- The Arctic band is 5.9% of land.

landcover_igbp_2023.tif (0.05 deg, cos-lat weighted):
- Class 16 (barren) = 0.1482 of classes 1-16.
- Class 15 (snow/ice) = 0.0017; Greenland lies outside this footprint.

Smearing factor: exp(0.535^2/2) = 1.154 and exp(0.643^2/2) = 1.230, giving 87.3 Pg -> 100.7-107.4 Pg. RMSE values from E6_matrix_XGB within_cv: NA 0.535, Europe 0.600, Asia 0.643.

E5_global_aoa.json: NA_rmse_by_DI_tercile [0.536, 0.513, 0.573]; inside AOA r2 0.307 / rmse 0.517 (n 235); outside AOA r2 0.461 / rmse 0.749 (n 22).


## [transfer-noise] transfer-noise-09 — finder low / stats-method → VERDICT confirmed / low
**N3's 3-level model is correctly coded as nested, but 70 of 889 studies span several sites; a crossed model moves about 4 points of variance share from site to study** (exp_reproducibility.py 58-66)

DESCRIPTION: The statsmodels usage is correct: groups = site with re_formula '1' gives the site intercept (cov_re); vc_formula 'study' gives study-within-site (vcomp[0]); scale is the record level. The fit converges, and Nelder-Mead/BFGS give identical estimates. Nesting, however, is imposed by labelling studies as site_Study_number, and 70 of 889 Study_numbers have records at two or more 5-km sites. Their shared study effect is therefore counted as site variance. A crossed fit (one group per connected site-study component; vc for site and for Study_number) gives site 0.260 / study 0.082 / record 0.068, i.e. shares 0.634 / 0.200 / 0.166, vs N3's 0.678 / 0.163 / 0.159. The independent-study ceiling falls to 0.634.

EVIDENCE: docs/review/2026-11-02/critique_scripts/transfer-noise/code/probe_n3.py (spec, convergence, optimizer check) and code/probe_crossed.py (crossed REML, 486 independent blocks).

AFFECTED: N3 variance shares and ceilings; prep_log §15 'site 68% / study 16% / record 16%'

FIX: Report the crossed model (or both) and name the primary one; use the crossed site variance in the ceilings of transfer-noise-02.

VERIFIER: The statsmodels specification in exp_reproducibility.py:58-66 is correct and robust: four optimizers give the same estimates and log-likelihood. Nesting is imposed by the label site_Study_number. In the multi-record-site data the model is fit on, 70 of 889 Study_numbers span two or more sites (116 of 1,125 across all QC SRDB records). I fitted a crossed model with 486 independent blocks, i.e. connected components of the site-study bipartite graph. It moves about 4 points of variance share from site to study, exactly as stated. Low is right. This is a modelling choice, and a crossed model can also assign genuine regional signal shared by a multi-site study's sites to 'study', so reporting both is the appropriate fix.

VERIFIER EVIDENCE: Script: docs/review/2026-11-02/critique_scripts/verify-transfer-noise/code/v_crossed.py.

Nested fit (exactly as exp_reproducibility.py:60), optimizers lbfgs, nm, bfgs and powell: site 0.2926, study 0.0704, record 0.0684 (shares 0.678 / 0.163 / 0.159); converged; llf -1413.448 in all four.

Multi-record data: 3,269 records, 595 sites, 889 Study_numbers, 70 spanning >= 2 sites.

Crossed fit (groups = 486 blocks, re_formula '0', vc for site and Study_number): site 0.2601, study 0.0821, record 0.0683 (shares 0.634 / 0.200 / 0.166); converged.


## [transfer-noise] transfer-noise-10 — finder low / doc-mismatch → VERDICT confirmed / low
**Two different 'Asia spatial-CV R2' values for the same model (0.143 and 0.163); 'within any continent' covers three continents and OLS-TP only** (exp_matrix.py 51-57)

DESCRIPTION: E6 within-CV is the R2 of pooled out-of-fold predictions from one fold seed (42). The locked test's 0.143 is the mean of 15 per-fold R2 values (seeds 42-44), each computed around its own fold mean. Both are quoted for OLS-TP in Asia (prep_log §13: 0.143; §14: 0.163) without saying they are different metrics. PROMPT §1's 'climate explains little within any continent (R2 0.06-0.45)' is OLS-TP within-CV for Asia, Europe and NA only; within-CV was not run for South America, Africa or Oceania (n < 60). XGB within-CV spans -0.157 to 0.375. Folds balance blocks, not sites: Europe has 32-63 sites per fold with seed 42 and 22-76 with seed 43.

EVIDENCE: Code reading; clean_test.py:50-56 vs exp_matrix.py:52-57; fold sizes from docs/review/2026-11-02/critique_scripts/transfer-noise/code/probe_misc.py step (3) on the rebuilt QC sites.

AFFECTED: prep_log §13 vs §14; PROMPT §1 'R2 0.06-0.45'

FIX: Name the metric and use one definition throughout; report the spread across fold seeds; write 'in the three continents with >= 60 sites' and give the learner.

VERIFIER: Code reading confirms the two metrics. clean_test.py:51-56 averages 15 per-fold R2 values over fold seeds 42-44, each R2 computed around its own fold mean. exp_matrix.py:52-57 computes one pooled out-of-fold R2 with seed 42. On the same Asia rows, these give 0.143 (prep_log §13) and 0.163 (§14), with no note that they differ. exp_matrix.py:51 runs within-CV only for n >= 60, so the 'R2 0.06-0.45' range covers OLS-TP in three continents; XGB spans -0.157 to 0.375. The fold sizes I reproduced are for the 236-site QC table. E6 uses 235 Europe sites, and dropping any single site can change the block list and therefore the shuffle, so the exact E6 sizes are uncertain. The point that folds balance blocks, not sites, holds in every variant.

VERIFIER EVIDENCE: Script: docs/review/2026-11-02/critique_scripts/verify-transfer-noise/code/v_folds.py (the fold function copied from exp_matrix.py:30-34, run on the rebuilt sites_v3_qc).

Europe, n = 236:
- Seed 42: [39, 63, 32, 63, 39].
- Seed 43: [44, 64, 22, 30, 76].
- Seed 44: [46, 47, 49, 36, 58].

Dropping each Europe site in turn:
- Seed 42: min fold size 31-42, max 54-63.
- Seed 43: min 14-27, max 75-102.

Asia, seed 43: [94, 125, 61, 78, 29].


## [transfer-noise] transfer-noise-11 — finder low / claim-unsupported → VERDICT confirmed / low
**E2's 'soil lowers, NPP ≈ no change' comes from unpaired single-seed differences of similar size** (exp_shift.py 33-38; prep_log.md:166)

DESCRIPTION: QC: C8+SOIL 0.329 vs C8 0.361 (-0.032); C8+NPP 0.367 (+0.006). Repo filters: SOIL 0.276 vs 0.314 (-0.038); NPP 0.346 (+0.032). Under repo filters, the NPP gain equals the soil loss in size. The test sets differ slightly (n 255-257 and 320-326) and there is no paired CI, which is the error prep_log §1.1 corrected for the original pipeline. The repo-vs-QC comparison (0.31 vs 0.36) uses different NA test sets (326 vs 257 sites), so by E4b's own lesson the R2 values are not comparable.

EVIDENCE: E2_E3_shift.json E2_* entries.

AFFECTED: prep_log §12 E2; README 'Asia->NA 0.36 (QC)' if presented as an effect of data hygiene

FIX: Use a paired bootstrap on common sites, with seed ensembles under xgboost 2.1.4. Drop directional wording unless the CI excludes 0, and compare QC vs repo filters on common test sites or by RMSE.

VERIFIER: The JSON values are as stated. The differences are single-seed (P random_state 0, exp_shift.py:16) and unpaired, on slightly different test sets (dropna per feature set at exp_shift.py:36), with only per-model CIs (lines 20-22, 38). Under repo filters, the NPP change (+0.032) is about as large as the soil change (-0.038); 'equals' is approximate. So 'soil lowers, NPP ~ no change' describes QC only and is not tested. The repo vs QC comparison uses different NA site sets (326 vs 257). Low is appropriate.

VERIFIER EVIDENCE: E2_E3_shift.json:
- QC: C8 0.361 (n_test 257), C8+NPP 0.367 (256), C8+SOIL 0.329 (255).
- Repo filters: C8 0.314 (326), C8+NPP 0.346 (325), C8+SOIL 0.276 (320).

Differences: QC SOIL -0.032, NPP +0.006; repo SOIL -0.038, NPP +0.032.

Code: exp_shift.py:33-38. prep_log.md:166.


## [transfer-noise] transfer-noise-12 — finder low / doc-mismatch → VERDICT confirmed / low
**E4/E4b do not reproduce the original configuration, and are labelled 'CONUS box' without saying which filter set they use** (exp_ablation.py, exp_ablation2.py exp_ablation.py:41-58; exp_ablation2.py:7-9)

DESCRIPTION: The single-record rule itself is faithful: COSORE first, then the lowest SRDB row. In all 523 original 0.05-degree cells with more than one eligible SRDB record, the original pipeline kept the lowest row, and my replication of build_target.deduplicate_spatial reproduces 889 of 889 original Asia+US site_ids. But E4 applies the rule per v3 5-km cluster. Inside the boxes, its 534 (Asia) and 240 (US) clusters correspond to 602 and 271 original-style cells, so 'y_single|boxes' (n 525/240) is not the original 615/274 sample, and the ablation leaves out the site-unit factor. Both target arms also use features sampled at the first record's coordinates (lines 49-51), not at the site mean as in features_v3.py:26, so 'y_mean|continents' (0.325) is not the v3 pipeline value (0.314). E4b runs on features_v3_repo (NA n = 326), while the E2/E6 numbers next to it are QC; prep_log line 168 does not say so. 'CONUS box' is the -125..-66, 24..50 bounding box, which contains southern-Canada and Mexico sites (§3 found 22 such sites in the original US box).

EVIDENCE: docs/review/2026-11-02/critique_scripts/transfer-noise/code/dedup_check.py (original dedup replication) and code/probe_misc.py step (4) (cluster vs cell counts), both on raw SRDB with legacy/src/build_target.py logic.

AFFECTED: prep_log §12 E4 ('CONUS box 0.13 ... all NA 0.31'); README E4 headline

FIX: Rename to 'US bounding box'; state that E4b uses repo filters; add the site-unit factor (0.05-degree cell vs 5-km cluster) and site-mean-coordinate features to the ablation.

VERIFIER: My own replication of legacy/src/build_target.py:149-161 confirms the faithful part: the 0.05-degree round-and-dedup rule, COSORE first, keep first. It gives 1,393 sites, matching prep_log §3, and reproduces 889 of 889 original Asia+US site_ids. All 523 multi-record cells kept the lowest SRDB row. E4 instead applies the rule per 5-km cluster, with box membership by cluster-mean coordinates. Features are sampled at the first record's coordinates (exp_ablation.py:48-51), not at the site mean as in features_v3.py:26-28. y_mean|continents (0.325) has the same n as E2_repo_C8 / E4b (0.314; 473/326), consistent with that being the only difference. E4b's n of 326 identifies the repo-filter table. One nit: counting cells by cell coordinates I get 601 Asia-box cells, not 602. The reviewer's 602 counts distinct cells inside in-box clusters, so the difference is definitional and immaterial.

VERIFIER EVIDENCE: Script: docs/review/2026-11-02/critique_scripts/verify-transfer-noise/code/v_dedup.py.

Original dedup replication:
- 4,771 repo-filter SRDB records; dedup keeps 1,393.
- Original site_ids reproduced: 889 of 889.
- 523 original SRDB sites in multi-record cells; kept == lowest row in 523.

E4 site units (v3 base records, 5-km clusters):
- 534 clusters in the Asia box, 240 in the US box.
- Same records as 0.05-degree cells: 601 / 271.
- US-box clusters by country: USA 221, Canada 18, Mexico 1.

E4_ablation.json: y_mean|continents 0.325 (473/326). E4b_regions.json: Asia continent -> NA continent 0.314 (n 326).


## [transfer-noise] transfer-noise-13 — finder low / reproducibility → VERDICT confirmed / low
**The clay marginal correlations quoted in prep_log §12 have no script or results file** ((none in scripts/) — prep_log.md:170 prep_log.md:170)

DESCRIPTION: No script in the bundle computes a marginal clay correlation for 'Clay: v3 marginal r Asia +0.30 (n 383), NA +0.13 (n 257)', and no JSON contains these values. exp_shift.py provides only the conditional clay effect: clay_z -0.035 [-0.136, 0.067], interaction +0.03 [-0.088, 0.147], which does support 'no conditional effect'.

EVIDENCE: grep for 'clay' across scripts/exp_*.py and results/*.json finds only exp_shift.py:14, 65-69 and the E3_pooled_interactions entries.

AFFECTED: prep_log §12 clay line; any paper statement on the clay sign flip

FIX: Add the computation (with bootstrap CIs, as in prep_log §5) and its output file, or drop the numbers.

VERIFIER: The only marginal clay-correlation code in the bundle is audit.py:74-82. It runs on the original committed tables (training_features_v2 / us_validation_features_v2, n 594 / 272) and produces the prep_log §5 values (+0.294 / -0.036) in checkpoint1/audit.json. No script or results file produces the v3 values in prep_log line 170 (Asia +0.30, n 383; NA +0.13, n 257). exp_shift.py gives only the conditional HC3 coefficients, which do support 'no conditional effect'. Low is appropriate.

VERIFIER EVIDENCE: grep -i clay over scripts/*.py: audit.py:74-82 (reads data/processed/*_v2.parquet, lines 19-20); exp_shift.py:14, 65-69; the rest are feature lists.

checkpoint1/audit.json clay_vs_logrs: Asia pearson r 0.2943 (n 594); US r -0.0358 (n 272).

No occurrence of n 383 or r 0.13 for clay in results/*.json or checkpoint1/*.json.

E2_E3_shift.json: clay_z -0.035 [-0.136, 0.067]; interaction +0.03 [-0.088, 0.147].


### checked_ok for transfer-noise
- Rebuilt the v3 record/site tables from raw SRDB + COSORE (own run of the cosore_aggregate logic: 66 sites, 24 unreadable RDS files, 1 without a qualifying port) + Natural Earth, using the unmodified build_sites_v3.py; build_summary.json reproduced exactly, every key.
- Reran exp_noise_ceiling.py and exp_reproducibility.py unmodified on the rebuilt records: E1_noise_ceiling.json (96 values) and N3_reproducibility.json (76 values) reproduced exactly.
- E1's one-way unbalanced ANOVA estimator is the standard one (n0 = (N - sum n^2/N)/(k-1), s2b = (MSB - MSW)/n0, truncated at 0), and the site-mean ceiling formula is algebraically right given its assumptions. Per-continent ICCs (Asia 0.727, Europe 0.623, NA 0.820) match a site-level recomputation.
- The 5-km connected-component merging does not chain: the largest QC cluster spans 15.7 km (99th percentile 6.6 km).
- Pooling continents inflates between-site variance only slightly (pooled s2b 0.284 vs a site-weighted per-continent mean of 0.269).
- N3 MixedLM: groups = site plus vc_formula for study-within-site is a valid nested specification in statsmodels; the variances map correctly (cov_re = site, vcomp[0] = study, scale = record); the fit converges and two optimizers agree; the 'independent study' and 'same study' ceiling formulas are right for single records.
- Records with missing Study_midyear or Meas_method (19 and 27 of 3,631 QC SRDB records) are counted as 'different' in the N3/E1 pair splits; the effect is negligible.
- E6 code: the pairwise, LOCO and within-CV loops, the training-mean baselines and the folds() guard are correct, and the n's agree with the site tables (Asia 384, Europe 235, NA 257).
- Where within-CV runs, there are enough 5-degree blocks (Asia 69, Europe 41, NA 63); continents with < 60 sites (13-22 blocks) are correctly excluded.
- The E4 single-record rule (COSORE first, then lowest SRDB row) matches the original dedup: 523/523 multi-record cells kept the lowest row, and 889/889 original Asia+US site_ids are reproduced.
- E4b's conclusion that R2 is not comparable across test regions is correct: US-box test SD is 0.60 vs 0.95 outside the box, and RMSE is worse outside (0.664 vs 0.562) even though R2 is higher.
- E5 AOA implementation: the threshold is the outlier-removed maximum (Q3 + 1.5 IQR whisker) of the CV training DI, which uses spatial-block folds as in Meyer & Pebesma and the locked plan. For dbar, n <= 1500 in both runs so nothing is subsampled; the [:400000] truncation drops 67k of 467k pairs (all-sites run only) taken from a random permutation, so it is unbiased in expectation and negligible.
- E3: the importance weights (p/(1-p) from the cross-validated classifier, normalised, clipped at 20) and the ESS formula are correct.
- Every number quoted in prep_log §12/§14, the README results index and PROMPT §1 matches its JSON (E1, E2, E3, E4/E4b, E5, both E6 learners, N3, and the repo-filter clean-test sensitivity: n 282, R2 0.052 [0.004, 0.092], block [-0.004, 0.099], RMSE 405.1 vs 405.9), apart from the claims flagged in the findings.
- 'The simple linear model transfers better than XGB nearly everywhere' is factually right on point estimates (OLS > XGB in 15/20 pairwise, 5/6 LOCO, 3/3 within-CV), though untested.

