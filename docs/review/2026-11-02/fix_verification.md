# Verification of the package-review fixes (2026-11-02)

Second review of the v3 package, run after commit `b74e590` (which fixed the 27 findings in `package_review.md`). Three reviewers (fidelity to the handoff scripts; guards and robustness; conformance to the brief) each checked every fix they owned by re-running it in sandboxes, and looked for new problems in the fixed code. An adversarial verifier then re-ran every new finding. The repository was read-only for all of them. Decisions: `docs/DECISIONS.md` R-P1-20.

Result: **all 27 fixes hold. 20 new findings, all confirmed, all low after verification** (one was rated medium by its finder). None changes a reproduced number. All 20 are fixed in the commit that adds this file; the fix for each is given below.

Paths: `fixcheck_scripts/...` are the reviewers' scripts and small logs, archived next to this file (`<scratch>` and `<scratchpad>` refer to the build container's scratch directory; large intermediate files were not archived). Line numbers refer to commit `9e17a36`.

## 1. The 27 fixes

- **fidelity-modis-cache-stale-and-erases-failures** (fidelity): **resolved**. Code: the cache key at mshi/data/modis.py:264-268 combines SHA-256 of sources.modis, of the extraction functions and of the sorted point keys. Reuse at :303-308 happens only when the key matches exactly and n_failed_reads==0, and the original record is rewritten. Any failed read raises ModisIncompleteError at :317-321 and no values are written. load_modis_points (:275-294) refuses tables from another config or code, from failed runs, or missing points. features.py:63-64 uses it and records modis_cache_key in features.json. Ran <scratch>/modis/stage_check.py: the real modis_points, extract_points and read_windows on 965 synthetic sinusoidal GeoTIFFs behind a fake STAC catalog and token, sandbox out_root. Run 1: n_raster_reads 265, n_failed_reads 0. The stage table equals the extract_points table exactly. Run 2: cached=True, 0 extractions, results/modis_points.json byte-identical to run 1's. Ran <scratch>/modis/stage_check2.py. (a) Changing window_deg from 0.05 to 0.25: load_modis_points raises StaleModisError, modis_points re-extracts (second extract call), and npp changes. (b) An extra NPP item whose COG is unreadable: ModisIncompleteError '1 of 266 MODIS raster reads failed'. results/modis_points.json then has status 'incomplete: no values written' and n_failed_reads 1, no parquet or sidecar is written, and load_modis_points raises FileNotFoundError. Two remaining gaps in key coverage (code hash and table bytes) are reported separately as fidelity2-modis-cache-key-coverage. <scratch> = fixcheck_scripts/fidelity

- **fidelity-rf-nondeterministic-results-hash** (fidelity): **resolved**. Code: LockedTest.fit (mshi/analysis/clean_test.py:109-113) fits RF with n_jobs=2, then sets n_jobs=rf.predict_n_jobs=1 (configs/v3.yaml:203, inside the locked block) before every predict. That covers select, score, the seed spread and permutation_importance in the AOA. The determinism claims were corrected in DECISIONS.md:77-81 (D-P1-1) and in the mshi/io.py write_json docstring. Ran <scratch>/ct/run_port.py twice in separate processes on each of 4 synthetic tables (real QC-site geometry, synthetic covariates and target): S1 selects OLS-TP, S2 ALL/RF, S3 C8+SOIL/RF, S4 ALL/XGB. Each pair gave 0 differing leaves and identical JSON SHA-256s (a54b3225…, b665bf1b…, dfc6524c…, 77d3939d…). MODIS is also deterministic: two port extractions gave byte-identical parquet files (<scratch>/modis/out/port_run1.parquet vs port_run2.parquet). Prototype vs port differences are confined to RF entries (see checked_ok).

- **fidelity-npp-r-method-not-in-handoff** (fidelity): **resolved**. Code: mshi/analysis/repro_checks.py:39-40 defines NPP_METHOD ('method reconstructed [UNVERIFIED]: no handoff script computes this r; Pearson r … joined on site_key'). The row note at :181-182 appends n = n_both_valid. :183-187 adds an INFO row for prep_log's 189 recovered sites (configs/v3.yaml:251-253, info_only). DECISIONS F-P1-19 (DECISIONS.md:287-293) records the reconstruction. Ran <scratch>/npp/npp_row.py: repro_checks on a sandbox with a synthetic MODIS table for the 889 original sites and a valid sidecar key. The row was written as 'NPP r vs committed NPP (original 889 sites) | … | method reconstructed [UNVERIFIED]: … joined on site_key; n = 683', and a second row 'Original sites with NPP missing in the committed tables but present in v3 | 189 | 199 | none given | INFO'. npp_check holds method, n_both_valid, committed_missing_v3_present and committed_present_v3_missing. The synthetic r has no meaning. The method caveat appears whenever the row is computed (PASS/FAIL); NOT RUN rows show the reason instead, as in the committed results/reproduction_check.md.

- **guards-modis-cache-keeps-failed-reads** (guards): **resolved**. Ran fixcheck_scripts/guards/scripts/t5_modis.py (log: .../guards/logs/t5_modis.log). It drives the real modis_points -> extract_points -> plan_jobs -> _read_job -> read_windows -> aggregate on local sinusoidal GeoTIFFs behind a fake STAC catalog. Only the point set, the STAC client, the SAS token and the remote probes are faked. Run 1 (npp 2023/2024 unreadable): exit 1; run_log 'error: ModisIncompleteError: 2 of 29 MODIS raster reads failed'; results/modis_points.json = {status 'incomplete: no values written', n_failed_reads 2}; no parquet and no meta; load_modis_points raises FileNotFoundError. Run 2 (files restored): 29 reads; npp 620.0 (mean of 300..1000), npp_n 5; lst_day 8.17 over 12 months, as expected. Run 3: cache hit with 0 reads and 0 probes; modis_points.json byte-identical to run 2. After window_deg 0.05->0.25, load_modis_points raises StaleModisError and the stage re-extracts. Code: modis.py:305 (key and n_failed_reads==0), 309 (meta removed before extraction), 317-321 (fail, no values), 275-294 (consumer check). Two residual paths are reported as new findings: a shortfall of catalog items, and parquet bytes not bound to the cache key.

- **guards-lock-self-anchored** (guards): **resolved**. Ran .../guards/scripts/t4_lock.py (log .../guards/logs/t4_lock.log). It writes 7 alternative --config YAMLs with scratch output paths. Each edits the locked block and recomputes locked_sha256 (test_continent North America, tie_margin 0.05, C8+NPP without npp, rf.predict_n_jobs 2, bootstrap_n 200) or changes plan_sha256 / locked_results.qc.sha256. verify_lock refuses all 7. main(['--config', alt, '--stage', 'clean_test']) exits 1 and writes only results/run_log.jsonl. No refusal message contains the new hash. Anchors: clean_test.py:44-49, checked at 56-84. LockedTest verifies the lock by default (91-92); require_lock=False appears only in tests/test_smoke.py:80. A config that edits only unlocked keys (site_build) passes the lock, but its results carry a different config_sha256 and are STALE for the default config. One note: the canonical JSON sorts keys, so reordering the `sets` keys passes the lock and changes LockedTest.cands order. The selection (sorted by cv_r2, tie rule) does not depend on that order, so only output row order can change.

- **guards-repro-pass-from-stale-outputs** (guards): **resolved**. Ran .../guards/scripts/t3_runner.py (log .../guards/logs/t3_runner.log) in a full (out_root=None) sandbox with absolute scratch paths. (B) After truncating the raw SRDB file, run(['build_sites','repro_checks']) exits 1. run_log: build_sites 'error: ChecksumMismatchError', repro_checks 'ok'. Summary PASS 0, NOT RUN 26; build rows show the note 'build_sites: error (ChecksumMismatchError)' although the old build_sites.json is still on disk. (E) With the SRDB url pointed at a local 404: exit 1, row note 'fetch_srdb: error (DownloadError)'. (G) With a target outside tolerance: ReproductionFailure, exit 1. A blocked-only run exits 2 (t10 and tests/test_robustness.py case). Exit logic: run.py:135-138; row sourcing: repro_checks.py:94-115. Remaining behaviour: a later invocation of repro_checks alone (C) shows PASS again from the last successful build with the current config/code, because run_log is read only when the file is missing (repro_checks.py:105-111). STALE rows exit 0 (new finding), and stale upstream inputs are not detected (new finding).

- **guards-non-policy-failures-labelled-blocked** (guards): **resolved**. Ran .../guards/scripts/t1_download.py (logs .../guards/logs/t1_download.log and t1_download_part2.log) against a local ThreadingHTTPServer with a trust_env=False session, recording sleeps. 404, 403 and 401 raise DownloadError after 1 request with no sleep. 429, 500 and 503 make 4 requests with sleeps [2,4,8] (none after the last), then DownloadError. A redirect loop raises TooManyRedirects (an error, not a block). Content-Length larger than the body, and an RST mid-body, are 'truncated transfer (ChunkedEncodingError)': retried, then DownloadError, with no .part left. A closed port gives SourceUnavailableError(kind='unreachable') after the retries. Ran .../guards/scripts/t2_proxy.py with a fake CONNECT proxy: 403/407 -> proxy_denied with no retry; 502/503 -> unreachable after retries. check_reachable(require_ok=False) passes 404/403/500; require_ok=True raises DownloadError. Pipeline t3 (E): the row note reads 'fetch_srdb: error (DownloadError)', not 'blocked by network policy'. A non-TIFF SoilGrids response raises DownloadError (rasters.py:74-77). Residual: the substring-based proxy classifier (new finding).

- **guards-srdb-licence-breaks-offline** (guards): **resolved**. Ran .../guards/scripts/t11_offline_locked.py (log .../guards/logs/t11_offline_locked.log). The scratch raw dir holds the pinned srdb-data.csv, LICENSE (its SHA-256 equals sources.srdb.licence_sha256) and the NE files; HTTP(S)_PROXY points at a closed port and NO_PROXY is cleared. run(['fetch_srdb','fetch_naturalearth','build_sites']) exits 0 with all three 'ok'. With LICENSE deleted: fetch_srdb 'unavailable: https://raw.githubusercontent.com/...LICENSE', build_sites skipped, exit 2. fetch.py:35-36 now passes licence_sha256.

- **guards-checksum-verified-after-replace** (guards): **resolved**. t1: a wrong body for a pinned hash raises ChecksumMismatchError with nothing at dest and no .part. netutil.py:118-122 now hashes the .part before os.replace. A bad file already at the pinned path stays after a failed re-download (t1 'pre-existing bad + mismatch'), but consumers re-verify. In t3 (B, D), with a truncated srdb-data.csv, the single-stage run(['build_sites']) exits 1 with ChecksumMismatchError raised at sites.py:41. Natural Earth is verified at sites.py:85 and site_diagnostics.py:44; the COSORE checkout at cosore.py:92.

- **guards-direct-table-reads** (guards): **resolved**. grep -rn over mshi/*.py for read_(parquet|csv|feather|pickle|json|table|file|excel), np.load, genfromtxt, loadtxt and pyarrow. Tables are read only in io.py:77,79. The other readers are gpd.read_file (Natural Earth GeoJSON, hash-verified), rdata (COSORE, pinned checkout) and JSON. The MODIS cache is read via read_table (modis.py:289); the NPP check uses load_modis_points. tests/test_guards.py:95-101 enforces this, and the suite passes.

- **guards-forbidden-hash-only** (guards): **resolved**. Ran .../guards/scripts/t6_readguard.py (log .../guards/logs/t6_readguard.log). Refused: a re-saved demo parquet (content check, io.py:82); a directory dataset of a re-saved copy; a copy hive-partitioned on source; a symlink to the demo; a symlink to the legacy v1 table; '..' traversal into legacy/; the upper-case LEGACY path (fail-closed). The repo tests cover a byte-identical copy inside a directory and a CSV export (suite passed). The allow-listed v2 tables are read and are hash-pinned (v3.yaml:17-19, io.py:59-62). Residual gaps with symlinked members, legacy members and column projection are a new finding.

- **guards-git-worktree-not-verified** (guards): **resolved**. Ran .../guards/scripts/t7_git.py (log .../guards/logs/t7_git.log) against a local file:// origin. These are refused with ChecksumMismatchError 'has local changes': a modified DESCRIPTION.txt, a modified tracked data.RDS, a deleted data.RDS, and a new untracked dataset directory. cosore_annual re-verifies (cosore.py:92), and fetch_cosore records HEAD^{tree}. Fetch errors: a missing origin or a commit not in the origin gives DownloadError with no retry. Residual: gitignored additions are not seen (new finding).

- **guards-provenance-env-overwrite** (guards): **resolved**. t3 (A): a non-full run writes no environment.json; (H) run(..., full=True) writes it with git_commit, config_sha256 and code_sha256. .../guards/scripts/t10_order.py: main() with explicit stages writes none, and '--stage all' writes it. t4: a refused clean_test via main writes only run_log.jsonl. Every run_log record carries git_commit, config_sha256, code_sha256 and invocation (run.py:97). All 13 result writes go through write_result (grep). .../guards/scripts/t8_runlog.py: an untracked mshi/new_module.py gives '+dirty'. t11: result_staleness is None for all 7 committed results/*.json (config d74c6282..., code 682cad12...). Residual provenance gaps are reported as new findings (not transitive; code hash taken at write time).

- **guards-git-status-writes-index** (guards): **resolved**. .../guards/scripts/t8_runlog.py (log .../guards/logs/t8_runlog.log) uses a scratch repo, a caller environment without GIT_OPTIONAL_LOCKS, and a tracked file whose stat info is made stale. git_commit leaves .git/index unchanged; the control, a plain `git status`, rewrites it. runlog.py:22 plus --no-optional-locks; netutil.py:30 GIT_ENV covers checkout and verify. A before/after snapshot of every file under /home/user/MSHI, including the COSORE checkout's .git, shows no change from my runs.

- **guards-modis-order-nondeterministic** (guards): **resolved**. t5 step 4: deleting the cache and re-extracting with 8 threads gives a byte-identical modis_points.parquet (SHA-256 equal). aggregate sorts by (kind, date, href) (modis.py:178-194), and failed reads are sorted (modis.py:233). tests/test_robustness.py::test_aggregate_independent_of_completion_order passes.

- **guards-locked-constants-in-code** (guards): **resolved**. The learner list, the OLS-TP log transform, the AOA quantiles and multiplier, the CI quantiles, the DI groups and the RF predict thread count are now in clean_test.locked (v3.yaml:197-220), covered by LOCKED_SHA256. design() builds OLS-TP from ols_tp/ols_tp_log (clean_test.py:118-122). Every bootstrap_ci call passes q from the config (157-159, 231-232), and the AOA difference uses ci_quantiles (203). The remaining literals are mechanical (float32 cast, sd==0 guard). .../guards/scripts/t13_ast.py: the _ast_digest pin in tests/test_guards.py catches tie rule '<'->'<=', 'sd[sd == 0] = 2' and a spatial.py shuffle edit, and ignores comment and docstring edits.

- **guards-locked-result-not-verified** (guards): **resolved**. t11: a config whose locked_results.qc.file points at a copy with '"n": 235'->'236' is refused by verify_lock, both with the config's sha256 field unchanged and with it updated to the copy's hash (anchors clean_test.py:46-49, checks 76-82).

- **guards-cli-stage-order** (guards): **resolved**. .../guards/scripts/t10_order.py (log .../guards/logs/t10_order.log), stages stubbed. main(['--stage','features','--stage','modis_points','--stage','build_sites']) runs build_sites, modis_points, features. A repeated '--stage features' is deduplicated. When modis_points errors, features is 'skipped: upstream modis_points not available' and the run exits 1 (run.py:93, 114-121). features also refuses MODIS values whose config, code or points do not match (features.py:63).

- **spec-01** (spec): **resolved**. I ran fixcheck_scripts/spec/scripts/modis_probe.py. It drives the real run() -> modis_points -> extract_points -> plan_jobs -> aggregate on 1,530 points and 3,654 reads. The STAC catalog has https://modiseuwest.blob.core.windows.net hrefs and is fake, as are the token and read_windows. requests.get is patched to raise ProxyError('Tunnel connection failed: 403') for the blob host, and no blocked host was contacted. Results: (1) STAC and token reachable but blob host blocked: status 'blocked: https://modiseuwest.blob.core.windows.net/: blocked by proxy', exit 2, 0 reads, no parquet or meta. The NPP row reads 'NOT RUN | modis_points: blocked by network policy (modiseuwest.blob.core.windows.net)'; the host probe is modis.py:210-211. (2) 5 persistent read failures: 'error: ModisIncompleteError: 5 of 3654…', exit 1, parquet and meta deleted. modis_points.json has status 'incomplete: no values written' and n_failed_reads 5, and the NPP note is 'modis_points: error (ModisIncompleteError)' (modis.py:317-321). (3) 126 transient failures are recovered by the second pass (modis.py:227-232), giving ok with n_failed_reads 0. (4) A re-run is a cache hit: 0 reads, the original record is rewritten (modis.py:303-308). (5) Changing window_deg to 0.25 re-extracts all 3,654 reads. features refuses a MODIS table that has another key, failed reads or missing sites (modis.py:275-294); test_modis_points_fails_on_failed_reads_and_caches_only_complete_runs passed. Two residuals are reported as new findings: the cache key leaves out extract_points (spec-new-01), and max_failed_reads > 0 is incoherent (spec-new-04).

- **spec-02** (spec): **resolved**. The hashed locked block now holds ml_learners, ols_tp_log, ci_quantiles, aoa_whisker{quantiles, iqr_multiplier}, di_groups and rf.predict_n_jobs (configs/v3.yaml:197-220). clean_test.py reads them at 96, 120-121, 155-159, 181-182, 203, 205 and 232. The locked result files are listed in config, and their hashes are anchored in code (clean_test.py:46-49, 76-82). The selection loop and tie rule are still code, but test_locked_code_unchanged pins them by the AST of clean_test.py and spatial.py; it ran and passed on Python 3.13.18. clean_test.py:8-19 and DECISIONS D-P1-9 now say exactly what the hash covers. lst.composite is read and validated (modis.py:137-139; test_plan_jobs_rejects_unimplemented_composite_rule). To check that the re-lock changed no value, I ran ee07832 and HEAD LockedTest with run_locked.py and compared with cmp_json.py. Inputs were two synthetic tables on the real 971-site geometry, one that selects OLS-TP and one that selects XGB/ALL, with light settings. Only random-forest leaves differ: 21 of 184 (max 6.5e-16) and 19 of 185 (max 3.3e-16). Residual: the new DEVIATION threshold atol=1e-9 is a code literal (spec-new-08).

- **spec-03** (spec): **resolved**. results/environment.json has git_commit b74e59016dcd… (no +dirty), config_sha256 d74c6282… and code_sha256 682cad12…. Every results/*.json _provenance equals load_config().sha256() and runlog.code_sha256() computed at HEAD 9e17a36. `git diff b74e590 HEAD -- mshi configs tests Makefile requirements-lock.txt environment.yml` is empty. The 13:30 run_log records carry git_commit, config and code hashes, invocation and smoke (run.py:97). environment.json is written only by full runs (run.py:98-100). The committed content regenerates from HEAD: regen_repro.py gives byte-identical reproduction_check.json and .md from the committed results plus the 13:30 invocation statuses, regen_misc.py gives identical fetch_srdb, fetch_naturalearth and site_diagnostics content, and test_fresh_rebuild_matches_committed_tables passed. The run log is now consulted only when a result is missing or incomplete, and only its latest record per stage is used (repro_checks.py:83-111). Those notes are labelled '(run log, date)', and README.md:30-32 says the blocked entries describe this machine.

- **spec-04** (spec): **resolved**. This is an author decision and it is still disclosed: DECISIONS D-P0-1 (lines 14-17) and Q-3 (line 457), and CHECKPOINT1.md lines 51 and 128. `git branch -a` lists only claude/mshi-pipeline-v3-rebuild-cg0r7o and main (plus their remotes); there is no v3-rebuild branch.

- **spec-05** (spec): **resolved**. configs/v3.yaml:246 sets europe_n to {value 235, abs 0}, so _tol prints 'exact'. In repro_states.py, state H (re-run n=236) gives 'FAIL | Locked test: Europe n' and ReproductionFailure. State G (r2 0.0795, vs_locked.identical False) gives 'DEVIATION | max |diff| 0.0003 | deviation: report it; the locked result stays primary'. _row with the old {rel 0.02} would give PASS for 236; the current {abs 0} gives FAIL. test_regression.py:63 uses the same exact tolerance, and D-P1-10 is updated. Residual: the repo-sensitivity re-run is not in the table (spec-new-02).

- **spec-06** (spec): **resolved**. fail_exit.py runs run(['repro_checks']) with a non-smoke config whose srdb target is 4770. Result: exit 1, run_log 'error: ReproductionFailure: 1 reproduction target(s) outside tolerance…', and the markdown row '| SRDB records after repo filters | 4,770 | 4,771 | exact | FAIL |' is written before the raise (repro_checks.py:191-196). With target 4771 the exit is 0. README and D-P1-18 document exit 1. Residual: repro_checks is still the last stage, so modis_points, features and clean_test consume a non-reproducing site build before the FAIL is seen. Stages without an explicit dependency on repro_checks still run after it (spec-new-06).

- **spec-07** (spec): **resolved**. Every item V-P1-4 now lists has a test: plan_jobs (test_robustness.py:208-223), order-independent aggregation (226-233), the second pass and persistent failures (241-257), the cache key and stale-value refusal (260-296), WorldClim zip handling (415-434), the clean_test stage end to end (372-402), download failure classes (73-124), and features on synthetic rasters (test_smoke.py:57-71, test_units.py:170). The full suite gave 107 passed and 3 skipped (pytest_full.log). The blob-host probe and the SoilGrids non-TIFF branch are still untested, but V-P1-4 no longer claims them; I checked the probe by hand in modis_probe.py.

- **spec-08** (spec): **resolved**. requirements-lock.txt:23 is now `nvidia-nccl-cu12==2.32.3 ; platform_system == "Linux" and platform_machine != "aarch64"`, which is xgboost's own marker. Makefile:4 falls back to `python` when .venv/bin/python is missing, and README.md:20-21 says so. lock_platforms.py checked each pin against the PyPI JSON API with packaging tags. Every pin has a cp313 or pure wheel for win_amd64. On macOS, pyproj 3.8.0 wheels need macOS 14 (arm64) or 15 (x86_64), and rasterio 1.5.2 wheels need macOS 15. So the lock's 'also installs on macOS' holds for macOS 15 and later; older macOS falls back to sdist builds that need GDAL/PROJ.

- **spec-09** (spec): **resolved**. All four errors are fixed. configs/v3.yaml:125 no longer has a dangling reference. site_diagnostics.py:3 cites D-P1-8, which exists (DECISIONS:135). io.py:3 and D-P0-3 'only reader' are now true: a grep of mshi/ finds no pandas or pyarrow table reader outside io.py, and test_no_direct_table_reads_outside_io enforces it. legacy/README.md:58 lists mshi.data.modis.modis_point_set, matching modis.py:248-251. One leftover of the same kind, older than this review and not part of the finding: DECISIONS.md:23 (D-P0-2) says 'see D-P0-6' for biosensor_samples, but that entry is D-P0-7 (DEV-P0-6 is pygam).


(27 fixes checked.)

## 2. Checked and found correct

### fidelity

- Clean-test refactor vs docs/handoff/scripts/clean_test.py at reduced settings. Tables were built on the real sites_v3_qc geometry with synthetic covariates and a synthetic target (NaNs in npp, lst, soc, clay, bio12 and log_rs); the real log_rs was never used. Only 5 size literals were patched in the prototype (<scratch>/ct/make_reduced.py), and LockedTest got the same lighter L. S1 (OLS-TP): 184 leaves, 22 differ, all RF, ≤6.1e-16. S2 (ALL/RF): 44 differ, all RF-related, including primary and AOA because RF is selected; ≤5.7e-14 absolute on g C metrics. S3 (C8+SOIL/RF): 30, all RF. S4 (ALL/XGB with the locked 250 trees, seed spread, permutation-importance AOA, 190 inside / 11 outside): 17, all RF, ≤3.3e-16.
- Clean test at full locked settings with the unmodified prototype. S1 (OLS-TP): 21 leaves differ, all RF, ≤4.4e-16. S4 (ALL/XGB, seeds 0-19): 18 differ, all RF, ≤2.2e-16. Bit-identical in every run: selection table and tie rule for OLS/XGB, primary metrics (R², 2000-draw site and 2° block CIs, RMSE/MAE in g C, intercept RMSE, bias, Spearman), XGB seed spread, AOA (threshold, inside/outside metrics, difference CI, DI terciles), and all OLS/XGB all_candidates_on_test entries. The ols_tp/ols_tp_log design, ci_quantiles, aoa_whisker, di_groups and ml_learners therefore reproduce the prototype exactly.
- Re-lock check: the new clean_test.locked block minus its 6 added keys equals the ee07832 block (hash 822f2ce1… → ef029090…; both recorded hashes match). The added values equal the prototype literals with the right types: ci [0.025, 0.975] floats, whisker [0.25, 0.75] and 1.5, di_groups 3, ml_learners [XGB, RF], ols_tp_log [bio12], predict_n_jobs 1.
- Old port vs new port: at most RF leaves differ. In S4, exactly 19 RF entries differ, ≤2.2e-16, matching D-P1-9's '19 random-forest entries'.
- MODIS rewrite vs docs/handoff/scripts/modis_points_lst.py, run unmodified via runpy with a fake pystac_client and token (<scratch>/modis). Points: 43, being 33 real QC sites in 5 tiles, 8 points within 0.3-2 km of tile edges, 2 points in a tile with no items, and 1 all-fill NPP point. Rasters: 965 GeoTIFFs with NPP fill, class codes, zeros and negatives, LST zeros and cloudy composites; some items have datetime None, Aqua items are present, and the API order is shuffled. Results: identical (kind, href, points) job multisets (265 each) and identical STAC parameters; read_windows identical on all 265 rasters; identical _n counts, NaN patterns, dtypes and row order. Means differ ≤3.2e-16 relative, purely from summation order: the prototype differs from itself by the same amount between two runs, the port equals the sorted-order nanmean bit for bit, and every prototype mean lies inside the range of order permutations. The full modis_points stage writes exactly the extract_points table.
- Site build and COSORE unchanged. A fresh port run (cosore_annual, build_sites, site_diagnostics) from the pinned data/raw into a sandbox (python -I -B) gave cosore_annual.csv, records_v3, sites_v3_qc (8aef5b32…) and sites_v3_repo (1ca93390…) byte-identical to the committed data/derived, which has not changed since ee07832. build_sites/cosore_annual/site_diagnostics JSON are equal including _provenance. The handoff prototypes (cosore_aggregate.py with its 2 paths patched, build_sites_v3.py) on the same inputs gave site parquets byte-identical to the port's, COSORE equal on all prototype columns (66 rows, max Δrs 0), records equal on all 23 prototype columns, and a build_summary equal to docs/handoff/build_summary.json.
- The repository's test suite (pytest -p no:cacheprovider, --basetemp in scratch, GIT_OPTIONAL_LOCKS=0, PYTHONDONTWRITEBYTECODE=1): 107 passed, 3 skipped (locked re-run and NPP check not present), matching DECISIONS V-P1-13.
- compare_with_locked uses only keys that exist in both locked result JSONs (n, r2, rmse_rs, mae_rs, rmse_rs_intercept, bias_log, spearman, ci_site, ci_block2), so the vs_locked block cannot hit a KeyError.
- Read-only rule. A before/after snapshot of all 17,214 repository files (biosensor_samples excluded) shows no path or size change, and no mtime change outside .git; .git/index and git status are unchanged. 214 loose objects and the pack under .git/objects had their mtimes refreshed at 13:43:04 UTC with contents and object set unchanged. None of my commands ran then: my git use was read-only log/diff/show/status, plus git archive at 13:40:25 and 14:01:18. All runs wrote only under fixcheck_scripts/fidelity. The real blocked hosts and the COG-host probe were not exercised; local hrefs skip the probe.

### guards

- Repository suite run in isolation (python -I -B -m pytest /home/user/MSHI/tests -p no:cacheprovider --basetemp=<scratch>/pytest_tmp -o pythonpath=/home/user/MSHI): 107 passed, 3 skipped in 74 s, matching V-P1-13.
- netutil.download: no sleep after the last attempt; no .part left after any tested failure (404/403/401/429/5xx/truncated/RST/refused/checksum); TooManyRedirects ends as 'error', not a block; an existing pinned file with the right hash is reused without a request; reuse_existing applies only to unpinned files.
- DEV-P1-16(4): with a fake proxy that denies CONNECT to modiseuwest.blob.core.windows.net (no real host contacted), modis_points is 'blocked' and exits 2 before any read (.../guards/scripts/t12_blob_rasters.py part 1).
- MODIS values on the real read path: NPP x0.1 mean over 5 years = 620.0; LST first 8-day composite per month, including items with datetime=None, mean 8.17 over 12 months; only Terra prefixes used (t5).
- run(): requested stages run in pipeline order and duplicates are dropped; environment.json is written only with full=True ('--stage all', also in smoke runs into out_root); smoke_subset does not run in non-smoke '--stage all'; exit codes 0/1/2 as documented (t3, t10).
- git_commit: never rewrites .git/index; an untracked module in mshi/ gives '+dirty'; README.md, data/derived and ignored *.pyc do not, as D-P1-17 states (t8).
- Offline re-runs: the cached SRDB CSV + LICENSE and the Natural Earth files need no network; a missing LICENSE offline gives 'unavailable' and dependants are skipped (t11).
- Committed results/*.json have _provenance equal to the current config (d74c6282...) and code (682cad12...); environment.json names the clean commit b74e590 (t11).
- Read guard: symlinks to legacy files or the demo, '..' traversal, relative paths (resolved against the cwd; the pipeline passes absolute cfg paths), non-existent paths (FileNotFoundError, no bypass), the upper-case LEGACY path (refused) and allow-listed tables with pinned hashes all behave as documented (t6).
- Lock: refusal messages never leak a replacement hash (the plan_sha256 message prints only the anchored hash). The AST pin catches semantic edits to clean_test.py/spatial.py and ignores comments and docstrings (t13).
- The repository was left untouched. A before/after metadata snapshot of every file under /home/user/MSHI (excluding .venv and biosensor_samples) shows no working-tree change, the COSORE checkout's .git is unchanged, and no __pycache__ was created. The only top-level .git changes come from another session's docs-only commit 9e17a36 at 13:35:18. All scripts are in fixcheck_scripts/guards/scripts/ and their outputs in fixcheck_scripts/guards/logs/.

### spec

- The repository was left untouched. A snapshot of 961 files (excluding .venv and data/raw/cosore) and the .git/index mtime were identical before and after all runs. All outputs are in fixcheck_scripts/spec/. My scripts that read data/raw copies or the repo ran with python -I -B; the pytest run was not isolated (-I). The COSORE checkout's .git/config has no hooks.
- Test suite (pytest -q -p no:cacheprovider --basetemp=<scratch>, GIT_OPTIONAL_LOCKS=0, PYTHONDONTWRITEBYTECODE=1): 107 passed and 3 skipped in 56.9 s. The skips are clean_test_rerun_qc.json absent (x2) and the NPP check not run. This matches V-P1-13 and CHECKPOINT1 §4 (110 tests, 107 passed, 3 skipped, about 60 s).
- The committed results (1ab8032) are current for HEAD. Every results/*.json _provenance equals load_config().sha256() (d74c6282…) and code_sha256() (682cad12…) at HEAD 9e17a36. environment.json names b74e590 with no +dirty. b74e590..HEAD touches no file under mshi, configs or tests, nor Makefile, the lock or environment.yml.
- The committed results regenerate from HEAD. regen_repro.py, using the committed results and the 13:30 invocation statuses with the same config hash, gives byte-identical reproduction_check.json and .md. regen_misc.py gives identical fetch_srdb, fetch_naturalearth and site_diagnostics content. test_fresh_rebuild_matches_committed_tables passed, covering build_sites.json and the 4 derived tables.
- The run-time claims match results/run_log.jsonl. Stage times sum to 39.7 s (13:30:24–13:31:04): cosore_annual 33.57 s, build_sites 2.87 s, site_diagnostics 1.86 s. Cached fetches took 0.02, 0.39 and 0.02 s, and blocked stages 0.30–0.33 s.
- repro_checks reports these states correctly (repro_states.py, repro_more.py, fail_exit.py). PASS rows behave as expected. A FAIL writes the table, then raises, and run() exits 1. A stage that did not finish in this invocation gives NOT RUN with the reason ('features: error (RuntimeError)', 'skipped: upstream …') even when a current file exists. cfg.invocation None with no run log gives 'no result (stage not run)'. An incomplete modis_points.json plus a run-log error gives NOT RUN 'modis_points: error (ModisIncompleteError) (run log, 2026-11-02)'. Build rows (17) and all 7 locked rows show STALE when stale. DEVIATION appears when vs_locked.identical is False, Europe n 236 gives FAIL, and the INFO row holds the 189-site count. A repro-only invocation on the committed state gives the committed notes plus '(run log, 2026-11-02)'.
- modis_probe.py exercised the MODIS failure handling through the real runner. A blocked blob host gives blocked and exit 2. Persistent failures give error, exit 1 and no values. The second pass recovers transient failures. A cache hit makes 0 reads and keeps the record. A change to sources.modis triggers re-extraction.
- The locked-test re-lock changed no value. ee07832 and HEAD LockedTest were run on two synthetic tables, one selecting OLS-TP and one XGB/ALL, which exercises the permutation-importance AOA and the seed spread. Only RF leaves differ: 21 of 184 (max 6.5e-16) and 19 of 185 (max 3.3e-16). DEV-P1-15 says ≤5e-16, measured on its own inputs. Running HEAD twice gave byte-identical JSON (13b88d65…, c7e58ee1…), which supports D-P1-1 and DEV-P1-15.
- The pinned hashes match the files. The plan hash 9d50e120… equals the sidecar and PLAN_SHA256. The locked results b091795f… and 48aa5beb… equal the code anchors and the config. The allow-listed v2 tables 482892df… and 1fa5d930… and the SRDB LICENSE 64bd84a5… equal the config. The locked block hashes to ef029090…. EDITS has 22 entries, each tested as-is and re-hashed. The refusal message never contains the replacement hash.
- The package conforms to the brief. There is one entry point and the make targets call it. The reproduction targets in configs/v3.yaml equal PROMPT §4. Tests exist for regression, the 50-site smoke run and the plan-hash refusal. Seeds are in the config, and versions are recorded in environment.json, environment.yml and requirements-lock.txt.
- These docs match the code: the D-P0-3 amendment (io.py:49-85); the D-P1-1 and V-P1-4 corrections; D-P1-9 (verify_lock :56-84, coverage list, AST pin, plan-text and prototype comparisons); D-P1-10; DEV-P1-15; DEV-P1-16 items 1-6, except the cache-key scope (spec-new-01); the D-P1-17 run-log fields and environment.json written only on full runs; D-P1-18 status classes and exit codes (netutil.py:29-123, run.py:127-138); and F-P1-19 (NPP_METHOD note and INFO row).
- README run, exit-code and layout text matches the code. The changed config comments are accurate: legacy pins, max_failed_reads 0, composite validation, OLS-TP as the 11th candidate, ci_quantiles, europe_n exact and npp_recovered_sites as INFO. legacy/README 'Still read by v3' and the hash-pin refusal (io.py:59-62) are accurate. data/derived/README's row counts (66 / 4,837 / 971 / 1,225), licence hashes (64bd84a5…, d60376da…) and 50 primary publications match the files.
- spec-08 platform check against the PyPI JSON API: every pin has a cp313 or pure wheel for win_amd64. On macOS only pyproj 3.8.0 and rasterio 1.5.2 need macOS 14 or 15 or later for wheels.

## 3. New findings, verdicts and fixes

### [fidelity] fidelity2-modis-cache-key-coverage: finder low → verdict confirmed / low

**MODIS cache key binds neither the cached table's bytes nor all of the extraction code (extract_points), so stale values can pass as current** (mshi/data/modis.py 257-268, 275-294, 303-308)

DESCRIPTION: The key that decides cache reuse (modis_points) and acceptance (load_modis_points, used by features and repro_checks) has two gaps. (a) _extraction_code_sha256 hashes only site_key, sinusoidal_tiles, scale_values, read_windows, item_datetime, plan_jobs, _read_job and aggregate. extract_points is not hashed, yet it decides which raster results are aggregated and which kinds become columns. A value-changing edit there leaves the key unchanged: the next run is a cache hit, features accepts the old values, and the new features.json carries current _provenance, so clean_test's staleness check passes. (b) The sidecar stores no hash of modis_points.parquet. Any table written to that path after a successful run is accepted as the cached, failure-free extraction, for example by the handoff script or by an older checkout, neither of which writes a sidecar. DEV-P1-16(3) (DECISIONS.md:257-260) and docs/CHECKPOINT1.md:58-59 say the cache is keyed on 'the extraction code'. The modis.py docstring (:23-25) says load_modis_points 'refuses a table whose key does not match'. Both overstate the guarantee.

EVIDENCE: <scratch>/codehash: two git-archive copies of HEAD's mshi/. In copy b, extract_points line 224 was edited to `results.append((j[0], j[3], j[1], {k: v * 1.1 for k, v in vals.items()}))`. _extraction_code_sha256() is 308b2a41… in both copies. <scratch>/modis/stage_check.py ran the real stage in a sandbox. After the successful run 1, the parquet was overwritten with npp+100 and npp_n=1, leaving the sidecar as it was. load_modis_points(sand, all keys) returned the replaced table (max |Δnpp| 100.0, npp_n {1}). modis_points(sand) then reported 'run 3 after replacement: cached = True', with no re-extraction. (<scratch> = fixcheck_scripts/fidelity)

SUGGESTED FIX: Hash the whole mshi/data/modis.py source in _extraction_code_sha256, or add extract_points, modis_point_set and modis_points to the hashed functions. Write the parquet's SHA-256 into the sidecar after write_table. Make load_modis_points and the cache-hit branch of modis_points refuse a table whose SHA-256 differs (treat it as StaleModisError or a cache miss).

VERIFIER: Both gaps reproduce. (a) _extraction_code_sha256 (mshi/data/modis.py:257-261) hashes 8 helpers but not extract_points (:197-238) or modis_points (:297-326). extract_points decides which read results are aggregated (:224) and which kinds become columns (:236-237). A value-changing edit there leaves the cache key unchanged. The cached table is then reused (:303-308), accepted by load_modis_points (:283-294), used by features (features.py:63, 70) and repro_checks (repro_checks.py:119), and the rewritten results/modis_points.json passes result_staleness. (b) The sidecar holds only the key and the record (:324), not the parquet's hash, so any table at that path is accepted. One correction on the triggers: an older checkout (ee07832) does not overwrite a cache that is present; it reuses it. It writes a table only after someone deletes the parquet but leaves the sidecar. The handoff script writes there only if OUT is deliberately set to that path. When that does happen, the original High failure mode returns: a partial table from failed reads is accepted as failure-free, and the failure record is erased. The doc wording 'keyed on ... the extraction code' (DECISIONS.md:256-259, CHECKPOINT1.md:57-59, modis.py:23-24) overstates the key's coverage. 'load_modis_points refuses a table whose key does not match' is literally true, since it never claims to bind the table's bytes. Severity is low: every trigger is a developer-time code edit or an out-of-band write to the gitignored cache. Config, point set and all value helpers are hashed, so normal re-runs and config changes behave correctly. No cache exists in the repo (data/interim is absent) and Planetary Computer is blocked here, so no current number is affected.

VERIFIER EVIDENCE: Scratch: fixcheck_scripts/verify-fidelity2/c1. Copies a and b come from `git archive HEAD mshi configs` (HEAD 9e17a36; mshi/ is identical to b74e590) and old from `git archive ee07832 mshi configs`. In b, modis.py:224 was edited by sed to `results.append((j[0], j[3], j[1], {k: v * 1.1 for k, v in vals.items()}))`. The driver is c1/stage.py PKG SANDBOX {hash,run,load,staleness,replace}, run with /home/user/MSHI/.venv/bin/python -B and PYTHONDONTWRITEBYTECODE=1. It runs the real modis_points / extract_points / read_windows on local sinusoidal GeoTIFFs (fake STAC and token from verify-fidelity2/fake/fakepc2.py). Only the unhashed modis_point_set, TokenCache, pystac_client and check_reachable are replaced. Results: (1) `hash`: _extraction_code_sha256 is 308b2a41a02a… in both a and b; the package code_sha256 differs (682cad12… vs 70678d36…). (2) `run` with a extracts: 26 reads, 0 failed, npp 623.519298 at 45.0_10.0, parquet sha 55a073046f77, meta 0045b192ff80. (3) `run` with b returns cached=True on the same parquet; `load` under b is ACCEPTED; `staleness` under b is None. (4) A fresh extraction with b in an empty sandbox gives npp 685.871228 (x1.1) with a byte-identical sidecar (0045b192ff80). (b) `replace` (npp+100, npp_n=1, sidecar kept): `load` is accepted (npp 723.52, npp_n 1) and `run` returns cached=True. Older checkout, sandbox sb4: with the cache present, ee07832 reuses it (cached=True, parquet sha unchanged 55a073046f77). After deleting only the parquet and hiding one NPP raster, ee07832 writes a partial table (npp_n 1; its own record says n_failed_reads 1). HEAD then accepts it in `load`, `run` returns cached=True and rewrites results/modis_points.json with n_failed_reads=0, and staleness is None. `git status` in /home/user/MSHI is unchanged.

**FIXED (R-P1-20):** The key now hashes the whole `mshi/data/modis.py` source and the numpy/rasterio/GDAL/pyproj/PROJ versions; the sidecar records the cached table's SHA-256, checked on reuse and by `load_modis_points` (DEV-P1-16 (4)).

### [fidelity] fidelity2-lst-tie-break-silent: finder low → verdict confirmed / low

**The same-date LST tie-break changes values silently; DEV-P1-16 and the modis.py docstring say no difference changes a value when every read succeeds** (mshi/data/modis.py 17-27, 153-156 (docs/DECISIONS.md:249-265))

DESCRIPTION: plan_jobs sorts LST items by (date, id), so when two Terra items share the earliest date of a month the smaller id wins. The prototype sorted by date only and kept the API's order. DEV-P1-16 item (6) admits this matters 'only if the catalog held two Terra items with the same date', but its header (DECISIONS.md:249-250) and the module docstring (modis.py:17: 'none changes a value when every read succeeds') claim no difference changes a value. The docstring also omits items (5) and (6). plan_jobs records nothing when such a tie occurs, so if the real Planetary Computer catalog has one, v3 LST means for those months would differ from the handoff's with no trace in results/modis_points.json. Those LST means feed the C8+MODIS and ALL candidates of the locked selection table.

EVIDENCE: <scratch>/modis/fakepc.py with ties=True adds a second Terra item '…061.B' with the same date as day-of-year 001 of each year. In run_proto.py (the unmodified handoff script, fake STAC and token) vs run_port.py (extract_points), NPP was unaffected (≤2.3e-16 relative). lst_day was bit-identical for only 3 of 41 points, with max |Δ| 1.64 °C; lst_night max |Δ| was 1.53 °C, and the _n counts differ. ref_check.py: 70 site/kind means fall outside the range of summation-order permutations, so this is a different composite being chosen, not rounding. Without ties every mean matches (see checked_ok). The size of the differences reflects synthetic rasters whose two same-date items are independent; real duplicate granules would differ less. (<scratch> = fixcheck_scripts/fidelity)

SUGGESTED FIX: In plan_jobs, count the (tile, year, month) slots whose earliest date has more than one Terra item. Log a warning and store the count and the chosen ids in the modis_points record. Reword modis.py:17 and DECISIONS.md:249-250 to 'except (6), when two Terra items share a date', and list (5) and (6) in the module docstring.

VERIFIER: The mechanism and the documentation inconsistency both hold. plan_jobs sorts Terra LST items by (item_datetime, id), so the smallest id wins a same-date tie (modis.py:154-156). The prototype uses a stable sort on datetime only, so the API's order decides the tie (modis_points_lst.py:65-66). plan_jobs logs nothing and the modis_points record has no tie field (modis.py:130-160, 314-316). The module docstring says none of the differences changes a value and lists only 4 differences, omitting DEV-P1-16 items (5) and (6) (modis.py:17-27). The DECISIONS header (DECISIONS.md:249-250) says the same, while item (6) (:263-265) admits ties matter. In my reproduction, ties change the chosen composite, and so the LST means, only when the API does not return tied items in ascending id order. I modelled two such orders: datetime desc / id desc (pgstac-like, not verified against the real service) and shuffled. With id-ascending tie order, or with no ties, the picks and values are identical. Whether Planetary Computer holds two Terra MOD11A2 items with the same date for a tile in 2020-2024, and in which order its API returns them, cannot be checked here (blocked). The real-world effect is therefore conditional, as the reviewer says. Severity is low. DECISIONS (6) already discloses the condition. A tie would replace one of the 60 monthly composites in a site's mean, and real duplicate granules would likely differ little. LST enters only the C8+MODIS and ALL candidates. Both locked results select OLS-TP (bio01, ln bio12), which does not use LST. The remaining defect is the inaccurate 'none changes a value' wording and the lack of any runtime trace.

VERIFIER EVIDENCE: Script fixcheck_scripts/verify-fidelity2/c2/ties.py, run as `/home/user/MSHI/.venv/bin/python -B ties.py <c2>` with PYTHONDONTWRITEBYTECODE=1. It uses fake/fakepc2.py: local rasters, one tile, 2020, with a 'reprocessed' Terra item duplicating the first composite of January and June. (1) Selection, real HEAD plan_jobs vs the prototype rule. Without ties: 0 of 12 months differ under the desc, asc, date_desc_id_asc and shuffle API orders. With ties: 2 of 12 months, (2020,1) and (2020,6), differ under desc and shuffle; v3 picks id …2020010000000 and the prototype picks …2021150000000. 0 months differ under asc and date_desc_id_asc. (2) Values: the unmodified docs/handoff/scripts/modis_points_lst.py (runpy, fake pystac_client, requests.get faked, no network) vs HEAD extract_points on the same fake catalog in desc order. Without ties: npp diff 0, lst_day/lst_night max |diff| 3.55e-15 (summation order). With ties: npp 0, lst_day max |diff| 0.937 °C and lst_night 0.955 °C at 4/4 sites; the _n counts are equal. Config: LST is in C8+MODIS and ALL (configs/v3.yaml:194,196). Locked results (docs/handoff/results/clean_test_europe*.json) select TP/OLS-TP in both variants. The repo has no record of real Planetary Computer item ids (grep for MOD11A2 item-id patterns found none).

**FIXED (R-P1-20):** Ties are listed in `results/modis_points.json` (`lst_same_date_ties`) and logged; docstring and DEV-P1-16 reworded ((6) can change an LST mean) (DEV-P1-16 (6)).

### [fidelity] fidelity2-rf-bound-overstated: finder low → verdict confirmed / low

**The stated size of the RF change ('≤ 5e-16', 'no other value changes') is overstated** (docs/DECISIONS.md 179, 246-247 (also docs/CHECKPOINT1.md:55))

DESCRIPTION: DEV-P1-15 says RF entries 'move by ≤ 5e-16 relative to the previous code; no other value changes'. D-P1-9 and CHECKPOINT1.md repeat '≤ 5e-16'. The bound depends on the data and is exceeded at the locked settings. When RF is the selected model, the primary metrics, seed spread and AOA also shift. No reported number is affected: the locked result's model (OLS-TP) and every XGB value are bit-identical. Only the documentation's quantitative claim is wrong.

EVIDENCE: <scratch>/ct/run_port.py, old port (git archive ee07832) vs new port. S1 at full locked settings: 23 RF leaves differ, max 6.38e-16. S1 with 40-tree forests: max 8.88e-16. S2 (ALL/RF selected): 26 primary/AOA leaves also differ, e.g. aoa.inside.mae_rs by 5.7e-14 absolute (~4e-16 relative). In every run, all non-RF leaves are identical. (<scratch> = fixcheck_scripts/fidelity)

SUGGESTED FIX: Reword to 'by ~1e-15 (data-dependent); if RF were the selected model, its primary metrics, seed spread and AOA would shift by the same relative amount; OLS-TP and XGB values are unchanged'.

VERIFIER: The documented RF effect is not a bound, and 'no other value changes' is false when RF is the selected model. DEV-P1-15 (DECISIONS.md:246-247) says RF entries 'move by ≤ 5e-16 relative to the previous code; no other value changes'; D-P1-9 (:179) and CHECKPOINT1.md:54-55 repeat ≤ 5e-16. I ran ee07832 against HEAD LockedTest at the unmodified locked settings, with the lock verified for HEAD, on synthetic tables. Absolute differences in RF entries reach 6.66e-16. Relative differences reach 1.45e-13, because some RF R² values are near 0, so the figure fails under either reading of 'relative'. On my table V2, C8/RF is selected at the locked settings by both codes, and 29-31 primary, seed-spread and AOA leaves also change, up to 5.7e-14 absolute. The old code is not even reproducible with itself (V2: 21 + 27 leaves differ between two old runs), so the 'previous code' value is a random variable. The new code is bit-identical across runs. In every pair, all non-RF table leaves (72) and all OLS-TP selected-model leaves are bit-identical. No reported number is affected: both locked results select OLS-TP with cv_r2 0.1434 vs best RF 0.1318 (qc) and 0.0881 vs 0.0693 (repo), so ~1e-16 noise cannot change the selection. Severity is low because only the deviation log's quantitative wording is wrong.

VERIFIER EVIDENCE: Scratch: fixcheck_scripts/verify-fidelity2/c3. Old package from `git archive ee07832 mshi configs`. Synthetic tables from make_synth.py use only lat/lon/continent of data/derived/sites_v3_qc.parquet; covariates and target are synthetic. batch.sh calls run_lt.py {old,new} FEAT OUT at full locked settings (verify_lock passes for new); outputs were compared leaf by leaf with cmp.py. Results: (1) Reviewer's S1, old vs new: 19 RF leaves differ, max abs 6.66e-16 (all_candidates_on_test[9].ci_site[0]), max rel 1.45e-13 (all_candidates_on_test[1].r2 = 0.0038); 72 non-RF table leaves and 50 OLS-TP leaves identical. (2) My V1 (OLS-TP): 23 RF leaves, max abs 4.44e-16, max rel 6.3e-14 (r2 = -0.0071). (3) My V2, C8/RF selected by both codes: 21 RF-table leaves (max abs 6.66e-16) plus 31/51 selected/primary/AOA leaves (max abs 5.68e-14 at aoa.outside.rmse_rs = 188.27; max rel 3.65e-12). A second pair gives 20 + 29. (4) Old vs old on V2: 21 + 27 leaves differ. New vs new on V2: 0 differ, both SHA-256 4f3eaaca…. My new S1 output is identical to the reviewer's fidelity/ct/out/new_S1_ols_full.json. Each run took 87-131 s.

**FIXED (R-P1-20):** DEV-P1-15 and D-P1-9 corrected (size data-dependent, ~1e-16; RF-selected metrics would move by similar amounts; OLS-TP and XGB bit-identical); CHECKPOINT1 §3 likewise.

### [guards] guards-new-provenance-not-transitive: finder medium → verdict confirmed / low

**Provenance is per stage: a stage run on upstream outputs from another config is stamped current, so STALE detection fails open** (mshi/io.py 143-161 (also mshi/run.py:111-113, mshi/analysis/clean_test.py:258-261))

DESCRIPTION: write_result stamps each result with the config and code hashes current when the stage runs; result_staleness compares only those. A stage run without its upstream stage reads outputs produced under an older config, yet its result is labelled current. This is the documented single-stage workflow (run.py:4 'uses existing outputs of its inputs'); the Makefile 'features' target has no build_sites and 'clean-test' has no features. In that case repro_checks shows PASS, the regression tests accept the result, and clean_test's features.json check passes when features was itself re-run on stale site tables. This defeats D-P1-17 ('STALE if its result came from another config or code') and the earlier fix suggestion 'older than its inputs'.

EVIDENCE: Ran fixcheck_scripts/guards/scripts/t15_transitive.py (log .../guards/logs/t15_transitive.log), with config B = cosore_annual.rs_range [50, 1000]. Full chain under B (cosore_annual + build_sites): cosore_records 41, records_after_qc 3669, Asia 386, North America 256. Partial run under B, run(['build_sites','repro_checks']) with the committed (config A) data/derived/cosore_annual.csv: exit 0; cosore_records 66, records_after_qc 3694, Asia 387, North America 257. result_staleness(build_sites.json) is None; reproduction summary PASS 16, STALE 0. verify_git_checkout was stubbed and the COSORE checkout symlinked read-only.

SUGGESTED FIX: Before a stage reads an upstream stage's outputs, require the upstream result JSON to be current, as clean_test already does for features.json. For example, a helper require_current(cfg, name) that raises unless result_staleness is None: cosore_annual.json in build_sites; build_sites.json in modis_points, features and site_diagnostics; modis_points.json in features. Alternatively, record the consumed results' _provenance in each result and make result_staleness recursive.

VERIFIER: The mechanism is real. write_result (io.py:143-147) stamps the config and code hashes current at write time, and result_staleness (io.py:150-161) compares only those two. The only callers of result_staleness are clean_test.py:258 (features.json) and repro_checks.py:112 (each result file on its own). build_sites, modis_points, features and site_diagnostics never check whether their upstream results are current. repro_checks.source() (repro_checks.py:94-115) looks at upstream stages only through this invocation's statuses. So a stage run on stale upstream outputs is labelled current.

The claimed consequence is overstated for the direct single-stage case. In a sandbox that holds the committed state, cosore_annual.json is present. The reviewer's sandbox lacked it. With it present, the COSORE row is STALE (summary PASS 16, STALE 1, not STALE 0), and two regression tests would fail: test_cosore_sites (load_result raises on stale) and test_reproduction_table_has_no_fail (asserts STALE == 0).

The fail-open is complete only when separate invocations run in reverse order (downstream first, then upstream). In that case every JSON is current, the table shows PASS 17 / STALE 0, and the regression checks pass while the derived tables differ from a full run.
- For the build chain, the slow test test_fresh_rebuild_matches_committed_tables would still catch it (pyproject has no addopts excluding slow tests).
- For features -> clean_test, nothing catches it. The documented targets do this in sequence: `make features` (no build_sites, Makefile:15-16), then `make data`; clean_test's features.json check then passes on stale features.

Today there is no effect: the committed results come from one full run, and features/clean_test cannot run here. A silent wrong result needs an upstream-affecting change followed by out-of-order partial runs, and the STALE note says `make all`. Hence low.

VERIFIER EVIDENCE: Scripts: fixcheck_scripts/guards-verify/scripts/v1_transitive.py {direct,reverse,features} and v1b_freshrebuild_check.py. Logs are in .../guards-verify/logs/v1_direct.log, v1_reverse.log, v1_features.log and v1_reverse_freshrebuild.log. Run as: cd .../guards-verify/work && GIT_OPTIONAL_LOCKS=0 PYTHONDONTWRITEBYTECODE=1 /home/user/MSHI/.venv/bin/python -I -B ../scripts/v1_transitive.py <mode>. Sandboxes hold copies of the committed results/ and data/derived/; verify_git_checkout is stubbed.

(direct) Config B: cosore rs_range [50,1000]. Full chain B: cosore_records 41, records_after_qc 3669, Asia 386, NA 256. run(['build_sites','repro_checks']) on the committed csv exits 0 with 66 / 3694 / 387 / 257. Staleness: build_sites.json None, cosore_annual.json 'produced with a different config'. Summary PASS 16, STALE 1 (COSORE row). Regression emulation: test_cosore_sites fail, test_reproduction_table_has_no_fail fail.

(reverse) Config C: molar_mass_c 12.0. run(['build_sites','repro_checks']), then run(['cosore_annual','repro_checks']). Result: PASS 17, STALE 0, all three regression checks pass, cosore_annual.json/build_sites.json staleness None. Yet sites_v3_qc log_rs differs from the full chain at 46 sites (max 9.16e-4). assert_frame_equal flags sites_v3_qc/repo and records_v3 as different.

(features) Config C, synthetic rasters and a MODIS cache. run(['features']) exits 0 with features.json current while build_sites.json is stale. Then run(['cosore_annual','build_sites','repro_checks']): PASS 17, STALE 0. The clean_test.py:258-261 check passes, and features_v3_qc.log_rs differs from the current sites_v3_qc at 46 of 971 rows.

grep result_staleness: only io.py, clean_test.py:258 and repro_checks.py:112.

**FIXED (R-P1-20):** Results record `_outputs` (SHA-256 of every file written); a result is current only if its outputs are unchanged; every stage calls `require_outputs` on the results whose files it reads; status `stale` (D-P1-17 (a)-(b), D-P1-18 (a)).

### [guards] guards-new-modis-catalog-shortfall: finder low → verdict confirmed / low

**Fewer STAC items than the date range implies is not a failure: means over fewer rasters (or NaN) are written, cached and accepted** (mshi/data/modis.py 130-160, 197-238, 297-326)

DESCRIPTION: Only failed reads fail the stage. If the catalog returns fewer items for a tile (a missing NPP year, a missing LST month, or none), plan_jobs just plans fewer jobs. Those sites' NPP/LST means then come from fewer rasters, or are NaN, while n_failed_reads is 0, the status is ok, the table is cached, and load_modis_points/features accept it. This is the silent effect the high finding described, reached through a different trigger. The record holds only the total n_raster_reads. The prototype behaves the same, so handoff numbers are unaffected while the catalog is complete.

EVIDENCE: t5_modis.py step 6 (log .../guards/logs/t5_modis.log), real extraction path on local COGs. With the catalog returning 3 of 5 NPP years for the tile: exit 0, npp 400.0 (620.0 with all 5 years), npp_n 3, n_failed_reads 0, n_raster_reads 27 (vs 29), and load_modis_points accepts the table. With 0 NPP items: exit 0, npp NaN and npp_n 0 for every site, missing.npp 3, accepted.

SUGGESTED FIX: In extract_points, check per tile that NPP has one item per year of sources.modis.datetime and that each LST asset has one first-of-month composite per month. Count every shortfall as a failed read, so max_failed_reads: 0 fails the stage and nothing is cached.

VERIFIER: plan_jobs (modis.py:130-160) plans one job per item the catalog returns and never checks counts against sources.modis.datetime. extract_points (197-238) reports only failed reads. modis_points (297-326) fails only when len(failed) > max_failed_reads. load_modis_points (275-294) checks key, failed reads and coverage, not per-site raster counts.

With a short catalog, the stage is ok and n_failed_reads is 0. The partial means are written, cached and accepted. The cache also makes a transient shortfall sticky: once the catalog is complete again, a re-run is a cache hit and keeps the partial mean. That is the one difference from the prototype, which re-queries on every run.

The data are not lost: the table keeps per-site npp_n/lst_*_n and the record keeps missing counts, so 'the record holds only n_raster_reads' is slightly understated. Nothing checks them, though.

Why low:
- With a permanently incomplete catalog, v3 gives exactly the prototype's values (docs/handoff/scripts/modis_points_lst.py:37-69 averages whatever items come back), so handoff numbers are unaffected.
- pystac_client raises on failed pages rather than returning partial results, so a transient shortfall is unlikely.
- max_items_per_tile 500 is above the estimated ~460 Terra+Aqua LST items per tile for 2020-2024. That estimate is arithmetic only; the catalog is blocked here. Truncation would become a trigger only if the date range were extended.

VERIFIER EVIDENCE: Script: fixcheck_scripts/guards-verify/scripts/v2_catalog.py (log .../logs/v2_catalog.log). It drives the real modis_points/extract_points/plan_jobs/_read_job/read_windows/aggregate with the real sources.modis config on local sinusoidal GeoTIFFs. Faked: the STAC client, the token, check_reachable and the point set.
- Complete catalog: n_raster_reads 125, n_failed 0, npp 620.0, npp_n 5.
- 3 of 5 NPP years: status ok, n_raster_reads 123, n_failed_reads 0, npp 400.0, npp_n 3, accepted by load_modis_points.
- Same cache, catalog complete again: cached=True, npp still 400.0.
- 0 NPP items: ok, npp NaN, npp_n 0, missing.npp 2, accepted.
- LST for 2020 only: ok, lst_day_n 12, accepted.
max_items_per_tile 500 (configs/v3.yaml:82).

**FIXED (R-P1-20):** Catalog checked before any read: one NPP item per year, an LST composite per month, no truncated search; gaps fail the stage unless listed in `accepted_catalog_gaps` (DEV-P1-16 (2)).

### [guards] guards-new-rasters-unverified-and-config-ignored: finder low → verdict confirmed / low

**WorldClim/SoilGrids rasters are not verified at read time and ignore config edits once on disk; io.py says they are hash-checked** (mshi/io.py io.py:11-12; rasters.py:41, 64, 79-80; features.py:26-53)

DESCRIPTION: io.py:11-12 claims rasters 'are checked against pinned hashes or commits by the stages that read them'. No raster hash is pinned (worldclim.sha256 is null; SoilGrids has none), and features samples the files without comparing them with the hashes that fetch_worldclim and fetch_soilgrids record. In addition, fetch_soilgrids skips any existing file larger than min_valid_bytes, and fetch_worldclim skips when the tifs exist. So edits to sources.soilgrids (statistic, depth, size, lon/lat, wcs_url) or to worldclim.url never take effect, yet fetch_soilgrids.json echoes the new config values. Because the config hash changes, the resulting features and clean_test outputs look current.

EVIDENCE: .../guards/scripts/t12_blob_rasters.py part (2): with synthetic rasters present, fetch_worldclim/fetch_soilgrids run ok; bio01 is then replaced, so its hash differs from fetch_worldclim.json tif_sha256. features exits 0 and uses bio01 = 99.0. .../guards/scripts/t14_soilgrids_cfg.py: setting statistic 'mean'->'Q0.5', size->[3600,1387] and lat->[-60,84] with rasters on disk gives exit 0 and 0 HTTP requests. fetch_soilgrids.json records statistic 'Q0.5' and size [3600,1387] while the files are the old 360x180 rasters.

SUGGESTED FIX: Store canonical_sha256(sources.soilgrids) and canonical_sha256(sources.worldclim) next to the files, as for the MODIS cache, and re-fetch when they differ. In features, verify every raster against tif_sha256/files_sha256 in results/fetch_worldclim.json and fetch_soilgrids.json and refuse if missing or different. Otherwise, correct the io.py docstring.

VERIFIER: The docstring at io.py:11-12 says rasters are 'checked against pinned hashes or commits by the stages that read them'. That is false for rasters:
- worldclim.sha256 is null (configs/v3.yaml:56), and soilgrids has no hash.
- features.sample_raster/attach_features (features.py:26-53) open the files with no hash comparison.
- fetch_worldclim skips work when all tifs exist (rasters.py:41). It then never compares even a pinned sha256 (zip_sha256 is None when there is no zip).
- fetch_soilgrids skips any file larger than min_valid_bytes (rasters.py:64). The path depends only on version and the literal file_pattern '{var}_5-15cm_global_0p05.tif', so edits to statistic, depth, size, lon/lat or wcs_url never trigger a fetch. The result JSON echoes the new values anyway (rasters.py:79-80) and gets the new config hash, so downstream results look current.

All of this reproduces. Severity is low: data/raw/worldclim/2.1 and soilgrids/2.0/0p05 are empty (blocked), so no current result depends on these rasters. The harm needs a deliberate SoilGrids/WorldClim config edit, or a replaced raster, on a machine that has the files.

VERIFIER EVIDENCE: Script: fixcheck_scripts/guards-verify/scripts/v3_rasters.py (log .../logs/v3_rasters.log). It runs the real fetch_worldclim, fetch_soilgrids and features on synthetic rasters in scratch; HTTP goes only to a local counting server.
(1) With rasters present, both fetches are ok with 0 downloads. bio01 is then replaced (hash differs from fetch_worldclim.json tif_sha256). features runs, shape [971,46], and uses bio01 99..100.
(2) Editing soilgrids statistic Q0.5, depth 0-5cm, size [3600,1387], lat [-60,84] and wcs_url to the local server gives 0 download calls and 0 HTTP requests. fetch_soilgrids.json records the new values while files_sha256 is unchanged (True).
(3) worldclim url set to the local server and sha256 pinned to 000…0: ok, 0 downloads, zip_sha256 None, the pin is never compared.
(4) Neither features.py nor rasters.py calls verify_sha256 or reads the fetch_* JSONs.

**FIXED (R-P1-20):** Per-file `*.source.json` sidecars record the request; a changed request or file is fetched again; fetch results record the rasters as outputs and `features` requires them; SoilGrids file name includes depth and statistic (D-P1-17 (b), (d)).

### [guards] guards-new-proxy-denial-substring: finder low → verdict confirmed / low

**A dead proxy is reported as 'blocked by network policy' when '403'/'407' occurs anywhere in the exception text** (mshi/netutil.py 49-51 (also 185))

DESCRIPTION: _is_proxy_denial returns True for any ProxyError whose str contains '403' or '407'. The text includes the proxy host:port and the request URL. A proxy that is down (connection refused) is therefore classified proxy_denied, without retries, whenever its port or the URL contains those digits. The run log then says 'blocked' and the reproduction note says 'blocked by network policy', contrary to D-P1-18. The git branch at line 185 has the same weakness: any '403' in the stderr counts once 'tunnel failed' appears.

EVIDENCE: Ran .../guards/scripts/t2b_proxy_port.py (log .../guards/logs/t2b_proxy_port.log). Dead proxy on port 1403 or 1407: kind=proxy_denied, sleeps [], message '...NewConnectionError("HTTPSConnection(host=127.0.0.1, port=1403): Failed to establish a new connection: [Errno 111] Connection refused")'. Dead proxy on port 35669 with URL path '/MOD11A2.A2020407_LST.tif': proxy_denied. check_reachable through a dead proxy on port 1403: proxy_denied. Control (t2_proxy.py): 3000 attempts through a dead proxy on a port without those digits gave 3000 x 'unreachable'.

SUGGESTED FIX: Match the tunnel status only, e.g. re.search(r'Tunnel connection failed: 40[37]\\b', str(e)) for requests, and re.search(r'CONNECT tunnel failed, response 40[37]\\b', last) for git.

VERIFIER: _is_proxy_denial (netutil.py:49-51) is a substring test on str(ProxyError). That string contains the proxy host:port and the request URL path, so a dead proxy (connection refused) is labelled proxy_denied, without retries, whenever '403' or '407' appears in either. The same happens to a CONNECT 502 for a URL containing those digits. The git branch (netutil.py:185) does the same once 'tunnel failed' appears.

The result is a 'blocked' run-log status (run.py:128) and the note 'blocked by network policy' (repro_checks.py:74-75). That contradicts the netutil docstring and D-P1-18 ('CONNECT answered 403/407').

The consequence is limited, hence low:
- The status label and the skipped retries are wrong, but the exit code is 2 either way.
- In this environment the proxy port is 42367, and none of the configured URLs contain 403 or 407 (grep of configs/v3.yaml), so nothing is misclassified today.

VERIFIER EVIDENCE: Script: fixcheck_scripts/guards-verify/scripts/v4_proxy.py (log .../logs/v4_proxy.log). Loopback only, *.invalid targets, sleeps recorded.
- download() via a dead proxy on :1403 or :1407: kind=proxy_denied, sleeps [].
- Control, dead :1408: unreachable, sleeps [2,4,8].
- Dead :1408 with URL path 'MOD11A2.A2020403.tif': proxy_denied.
- Fake proxy answering CONNECT 502: unreachable after retries; with URL path containing '407': proxy_denied, sleeps [].
- CONNECT 403 control: proxy_denied (correct).
- check_reachable with HTTPS_PROXY dead :1403: proxy_denied; control :1408: unreachable.
- git_checkout_commit through CONNECT 502: URL without the digits gives DownloadError; URL with 'repo403' gives SourceUnavailableError kind=proxy_denied.
The environment's HTTPS_PROXY is http://127.0.0.1:42367.

**FIXED (R-P1-20):** Only the tunnel status is matched (`Tunnel connection failed: 40[37]`, git `CONNECT tunnel failed, response 40[37]`), checked against this container's proxy (D-P1-18 (c)).

### [guards] guards-new-stale-rows-exit-0: finder low → verdict confirmed / low

**A reproduction table in which every row is STALE exits 0 ('all ok')** (mshi/analysis/repro_checks.py 189-197 (run.py:12-13, 135-138))

DESCRIPTION: repro_checks raises only for FAIL. After a config or code change, running it without its producers (make repro) marks every row STALE, yet the stage status is ok and the run exits 0, which run.py's docstring defines as 'all ok'. Only `make test` catches this.

EVIDENCE: t3_runner.py (F) (log .../guards/logs/t3_runner.log): after an unrelated config edit (smoke.seed), run(['repro_checks']) exits 0 with summary PASS 0, STALE 16, NOT RUN 10.

SUGGESTED FIX: When summary['STALE'] > 0, do not report the stage as ok. For example, raise a dedicated exception that run() records as 'stale: ...' and counts toward exit code 2, or simply raise ReproductionFailure for STALE rows as well.

VERIFIER: repro_checks raises only when summary['FAIL'] is non-zero (repro_checks.py:193-196). run() derives the exit code purely from stage statuses (run.py:135-138). A table whose rows are all STALE therefore gives stage status 'ok', console 'repro_checks OK' and exit 0, which run.py:12 calls 'all ok'. The output is the same as for a table of 17 PASS rows. The CLI path behaves the same way.

This matches the documented contract: exit codes reflect stage statuses, and D-P1-18 says only FAIL fails. It is misleading for anyone relying on the exit code or the console. `make test` does catch it: test_reproduction_table_has_no_fail asserts STALE == 0. No current stage depends on repro_checks. Hence low.

VERIFIER EVIDENCE: Scripts: fixcheck_scripts/guards-verify/scripts/v5_stale_exit.py and v5b_stale_exit_control.py (logs .../logs/v5_stale_exit.log and v5b_stale_exit_control.log).
- Control (results stamped by the sandbox config): exit 0, PASS 17, console 'repro_checks OK'.
- After the unrelated smoke.seed edit: run(['repro_checks']) exits 0, PASS 0, STALE 17, NOT RUN 9, run_log status 'ok', console 'repro_checks OK'.
- CLI main(['--stage','repro_checks','--config',<edited yaml>]) exits 0 with STALE 17.
Code: repro_checks.py:189-197; run.py:12-13 and 135-138.

**FIXED (R-P1-20):** `repro_checks` raises `StaleInputError` after writing the table when a row is STALE: status `stale`, exit code 2 (D-P1-18 (a)).

### [guards] guards-new-modis-cache-bytes-unbound: finder low → verdict confirmed / low

**MODIS cache meta does not bind the parquet bytes; an edited or replaced modis_points.parquet is accepted** (mshi/data/modis.py 275-294, 303-308, 323-324)

DESCRIPTION: modis_points.meta.json records the key (config, code, points) and the run record, but not the SHA-256 of modis_points.parquet. A parquet changed after the run (another tool, or another code version writing the same path) is accepted as a cache hit by modis_points and by load_modis_points, which feeds features and the NPP check.

EVIDENCE: t5_modis.py step 7: after a complete run, npp in modis_points.parquet was multiplied by 2 with the meta left untouched. load_modis_points then returns npp 1240.0 (true value 620.0), and modis_points() reports a cache hit.

SUGGESTED FIX: Write parquet_sha256 = sha256_file(out_path) into the meta at modis.py:324, and compare it in load_modis_points and on the cache-hit path at modis.py:305.

VERIFIER: modis_points.meta.json holds {key: {modis_config_sha256, code_sha256, points_sha256, n_points}, record} (modis.py:264-268, 314-316, 324). It holds no hash of the parquet bytes. load_modis_points (275-294) and the cache-hit path (303-308) never re-hash the parquet. A parquet edited or replaced after the run is therefore accepted, and modis_points reports a cache hit.

This reproduces. The realistic triggers are all out-of-band writes to a gitignored intermediate:
- a manual edit;
- another tool writing the same path, for example the pre-fix ee07832 code, which writes the parquet without any meta (git show ee07832:mshi/data/modis.py:205-206);
- two concurrent ~45-minute extractions interleaving their parquet and meta writes.
The other derived tables are not byte-bound to their result JSONs either. Hence low.

VERIFIER EVIDENCE: Script: fixcheck_scripts/guards-verify/scripts/v6_modis_bytes.py (log .../logs/v6_modis_bytes.log). It uses the real modis_points/load_modis_points with the extraction faked as complete.
- Run 1: n_failed_reads 0, one extraction call. The meta keys are [key, record]; key fields are [code_sha256, modis_config_sha256, n_points, points_sha256]; the meta does not contain the parquet sha256.
- After npp *= 2 in the parquet: load_modis_points accepts it with npp [1240.0, 1240.0] (true 620). modis_points returns cached=True, and the extraction calls stay at 1.

**FIXED (R-P1-20):** Sidecar records the parquet SHA-256 (see fidelity2-modis-cache-key-coverage); `modis_points.json` records the parquet as an output.

### [guards] guards-new-code-hash-at-write-time: finder low → verdict confirmed / low

**Results are stamped with the hash of code on disk at write time, not the code that ran** (mshi/io.py 143-147 (runlog.py:62-72))

DESCRIPTION: write_result calls provenance(cfg) when it writes, hashing mshi/*.py as they are on disk at that moment. If another session edits mshi/ while a stage runs (several sessions work in this repo; MODIS takes about 45 min), the result carries the new code hash and result_staleness reports it current, although the old code produced it. The run_log record of the same stage carries the start-of-run hash, but nothing compares the two.

EVIDENCE: Ran .../guards/scripts/t9_codehash.py on a scratch copy of the package. A stage edits mshi/analysis/repro_checks.py of the copy and then calls write_result. run_log code_sha256 is 682cad12..., the result's _provenance.code_sha256 is 745d0932..., and result_staleness(cfg, result) is None.

SUGGESTED FIX: Compute provenance once at the start of run(), store it in cfg.invocation, and have write_result use that snapshot (falling back to provenance(cfg) outside run()). Alternatively, snapshot code_sha256 when mshi is imported.

VERIFIER: write_result (io.py:143-147) calls provenance(cfg) at write time, and code_sha256 (runlog.py:62-66) hashes mshi/*.py as they are on disk then. Its lru_cache is keyed on mtime and size, so an edit is picked up. Every mshi module is imported at the start of run() (run.py:41-50). A concurrent edit therefore changes the stamped hash but not the code that runs.

The run_log record carries the start-of-run hash (run.py:97), but nothing compares the two hashes: the only code_sha256 comparison is io.py:160. A result produced by the old code then reads as current against the edited code. This reproduces. It needs a concurrent edit that changes the stage's behaviour during its run window; the code expects concurrent sessions (runlog.py:22). Hence low.

VERIFIER EVIDENCE: Script: fixcheck_scripts/guards-verify/scripts/v7_codehash.py (log .../logs/v7_codehash.log). It works on a scratch copy of mshi/ and configs/, imported from the copy. A fake stage registered through mshi.run._stages edits analysis/repro_checks.py of the copy, then calls write_result.
Result: exit 0. The start hash and the run_log code_sha256 are both 682cad124635. The result's _provenance.code_sha256 is b50e30b2a395, equal to the on-disk hash afterwards. result_staleness(result) is None.
grep shows code_sha256 compared only at io.py:160 (and the separate MODIS extraction hash).

**FIXED (R-P1-20):** `run()` takes the config/code snapshot at start; `write_result` uses it (D-P1-17 (c)).

### [guards] guards-new-git-ignored-files: finder low → verdict confirmed / low

**The clean-worktree check misses gitignored files; at the pinned COSORE commit an added dataset directory named 'doc' or 'Meta' is read** (mshi/netutil.py 158 (cosore.py:94))

DESCRIPTION: `git status --porcelain --untracked-files=all` omits ignored files. The pinned COSORE commit's top-level .gitignore has the unanchored patterns 'Meta' and 'doc', and RENCHON/data/.gitignore has '*.RDS'; these match new paths under inst/extdata/datasets/. A dataset directory added with such a name passes verify_git_checkout, and cosore_annual iterates every directory (cosore.py:94). The docstring says 'no ... untracked files'.

EVIDENCE: .../guards/scripts/t7_git.py: a local origin with the same ignore rules. Modified, deleted and untracked files are refused, but a new inst/extdata/datasets/doc/ with DESCRIPTION.txt and data/data.RDS is accepted as clean, and the dataset loop becomes ['dA','doc']. In the real checkout, `git check-ignore -v --no-index` maps datasets/doc/DESCRIPTION.txt to .gitignore:2:doc and datasets/Meta/data/data.RDS to .gitignore:1:Meta. The real checkout has 0 ignored files today (`git status --porcelain --untracked-files=all --ignored` prints nothing), so the fix is safe.

SUGGESTED FIX: Add '--ignored' to the status call at netutil.py:158, or require that `git ls-files --others --ignored --exclude-standard` prints nothing.

VERIFIER: verify_git_checkout (netutil.py:158) runs `git status --porcelain --untracked-files=all` without --ignored. At the pinned COSORE commit, the top-level .gitignore has the unanchored patterns 'Meta' and 'doc', and inst/extdata/datasets/d20200228_RENCHON/data/.gitignore has '*.RDS' (comment: 'This dataset is embargoed'). So the following are accepted as clean, and cosore_annual's loop (cosore.py:94) then reads them:
- a new dataset directory named doc or Meta;
- a data.RDS added to the embargoed RENCHON dataset. This trigger is a little more realistic than the reviewer's examples.

This reproduces. The real checkout has no ignored files today (status --ignored prints nothing), and every trigger requires deliberate writes into gitignored data/raw. Hence low.

VERIFIER EVIDENCE: Read-only on the real checkout:
- `git --no-optional-locks ls-tree/show HEAD:.gitignore` gives 'Meta' and 'doc' at lines 1-2. HEAD:inst/extdata/datasets/d20200228_RENCHON/data/.gitignore is '*.RDS'.
- `git check-ignore -v --no-index` maps datasets/doc/DESCRIPTION.txt to .gitignore:2:doc, datasets/Meta/DESCRIPTION.txt to .gitignore:1:Meta, and RENCHON/data/extra.RDS to its *.RDS rule.
- `status --porcelain --untracked-files=all --ignored` is empty.
- .git/index mtime is unchanged (1793619797).
Script: fixcheck_scripts/guards-verify/scripts/v8_git_ignored.py (log .../logs/v8_git_ignored.log). It builds a scratch origin with the same three .gitignore files and uses the real git_checkout_commit and verify_git_checkout.
- Control: untracked 'dB' is refused.
- 'doc' with DESCRIPTION.txt and data/data.RDS: ACCEPTED, loop ['d20200228_RENCHON','dA','doc'].
- 'Meta': ACCEPTED.
- RENCHON data/data.RDS: ACCEPTED.
- `--ignored` lists it as '!!'.

**FIXED (R-P1-20):** `verify_git_checkout` uses `--ignored=matching`; the real COSORE checkout has no ignored files (D-P1-18 (d)).

### [guards] guards-new-directory-dataset-members: finder low → verdict confirmed / low

**Members of a directory dataset are only hashed: no legacy/ rule, symlinked sub-directories skipped, and the content check sees only projected columns** (mshi/io.py 49-85 (64, 82))

DESCRIPTION: check_readable applies the legacy/ rule only to the resolved top path. Files inside a directory dataset are only compared with forbidden_sha256, and Path.rglob (Python 3.13) does not descend into symlinked sub-directories, while pyarrow reads through them. The 'source' content check runs on the loaded frame, so a columns= projection that omits 'source' skips it. The io.py docstring (2) claims 'any file inside a directory dataset' is hash-checked. No pipeline call uses such paths or projections today.

EVIDENCE: .../guards/scripts/t6_readguard.py and t6b_readguard.py (logs in .../guards/logs/). 'dirlink.parquet/part-0.parquet' as a symlink to legacy/data/processed/training_features.parquet (not allow-listed) is READ (615, 28), while the direct symlink is refused. 'ds.parquet/sub' as a symlinked directory holding a byte-identical demo copy: rglob sees only ['sub'], and read_table(ds, columns=['longitude','latitude']) is READ (3000, 2) (refused without the projection). A re-saved demo read with columns=['longitude','latitude','soc'] is READ (3000, 3).

SUGGESTED FIX: Walk members with os.walk(followlinks=True), or refuse symlinked members, and apply the full check to each member's f.resolve(): the legacy rule and the forbidden hash. For the content check, read the 'source' column (pyarrow schema plus a one-column read) even when columns= is passed.

VERIFIER: check_readable (io.py:49-70) has three gaps:
- It applies the legacy/ rule only to the resolved top path (50-62).
- Directory members get only the forbidden-hash check (64-69), and Path.rglob in Python 3.13.18 does not descend into symlinked sub-directories, while pyarrow reads through them.
- The 'source' content check runs on the loaded frame (io.py:82), so a columns= projection that drops 'source' skips it.

All three sub-claims reproduce, and io.py docstring item (2) overstates the guard. No pipeline call reads a directory dataset. The only projected read_table call is sites.py:43 (usecols) on the SRDB CSV, which is SHA-256-verified at sites.py:41. Every trigger needs deliberately built paths. Hence low.

VERIFIER EVIDENCE: Script: fixcheck_scripts/guards-verify/scripts/v9_dirdataset.py (log .../logs/v9_dirdataset.log). Real config and read_table; scratch paths with symlinks into the repo.
- The v1 table is not allow-listed, and the demo hash is forbidden.
- A direct symlink to legacy training_features.parquet is refused. dirlink.parquet/part-0.parquet as a symlink to it: READ (615, 28).
- ds.parquet/sub as a symlinked dir holding a byte-identical demo copy: rglob sees ['ds.parquet/sub'], no file is hashed. Without projection it is refused by the content check; with columns=['longitude','latitude'] it is READ (3000, 2). Control, demo as a plain member: refused.
- Re-saved demo (hash not forbidden): refused without projection; READ (3000, 3) with columns=['longitude','latitude','soc'].
- Projected read_table calls in mshi/: only sites.py:43.

**FIXED (R-P1-20):** `read_table` refuses directories (no pipeline input is one) and checks the `source` column under any column projection (io.py docstring).

### [spec] spec-new-01: finder low → verdict confirmed / low

**MODIS cache key omits extract_points, and a cache hit re-stamps the old record with the current code hash** (mshi/data/modis.py 257-261 (key function list), 197-238 (extract_points), 303-308 (cache hit))

DESCRIPTION: DEV-P1-16(3) and the modis.py docstring say the cache is keyed on the extraction code. _extraction_code_sha256 hashes only site_key, sinusoidal_tiles, scale_values, read_windows, item_datetime, plan_jobs, _read_job and aggregate. extract_points also determines values: it builds the (kind, date, href, vals) tuples, chooses all_kinds and calls aggregate. A value-changing edit there leaves the key unchanged, so the cache is reused. The cache-hit path then rewrites results/modis_points.json with the current _provenance, so result_staleness treats the old values as current. They then flow into features, the locked-test re-run and the NPP r row with status ok or PASS. The whole-package code hash cannot catch this, because the cache hit re-stamps the record.

EVIDENCE: fixcheck_scripts/spec/scripts/cache_key_gap.py with fake reads (value 100). The HEAD package extracts npp [100, 100]. I then used a copy of HEAD with one edit inside extract_points (vals x2 at modis.py:224) on the same cache. Its key.code_sha256 stays d06e4a905e36, cached=True, and npp stays [100, 100]. results/modis_points.json _provenance.code_sha256 becomes 0ed133ad303b, the edited package's hash. A fresh sandbox with the edited code gives [200, 200].

SUGGESTED FIX: Add extract_points to _extraction_code_sha256, or hash the whole modis.py source. On a cache hit, keep the original record's _provenance instead of re-stamping it.

VERIFIER: Reproduced. _extraction_code_sha256 (mshi/data/modis.py:257-261) hashes only site_key, sinusoidal_tiles, scale_values, read_windows, item_datetime, plan_jobs, _read_job and aggregate. It leaves out extract_points (modis.py:197-238), which builds the (kind, when, href, vals) tuples at :224, chooses all_kinds and calls aggregate at :236-237. It also leaves out modis_points. That contradicts the modis.py docstring (:23-25), DEV-P1-16(3) (DECISIONS.md:256-259) and the function's own docstring ('functions that determine the extracted values').

On a key match, the cache-hit path (modis.py:303-308) calls write_result, which stamps the current provenance (io.py:143-147). result_staleness then reports the old values as current. features accepts them, because load_modis_points (modis.py:283-286; features.py:63) checks the same incomplete key.

Severity lowered to low:
- The issue is latent: data/interim does not exist in the repo, so there is no MODIS cache, and MODIS is blocked here.
- It needs a value-changing edit to extract_points or modis_points while a cache exists. Most value logic sits in the hashed functions.
- It reproduces no wrong number today.

Caveat on the suggested fix: keeping the original _provenance on a cache hit would make modis_points.json STALE after any unrelated package edit. Hashing the whole of modis.py is the cleaner fix.

VERIFIER EVIDENCE: Script: fixcheck_scripts/spec-adv/scripts/c1_cache_key.py. It is fully offline: fake STAC catalog, fake token, and read_windows returns 100.

Packages:
- pkg_head: `git archive HEAD mshi`. diff -r against the working tree shows it is identical.
- pkg_edit: the same, with one edit at modis.py:224, vals -> {k: 2*v}.

Unpatched hashes (python -B, one process per package):
- _extraction_code_sha256 is 308b2a41a02a43d7 for both packages.
- Package code_sha256 is 682cad124635 vs be7041dc3dbf.

Runs:
- Run 1 (HEAD, empty cache): 7 reads, npp [100,100].
- Run 2 (edited package, same cache): cached=True, 0 reads, npp [100,100]. results/modis_points.json _provenance.code_sha256 = be7041dc3dbf, and result_staleness = None.
- Run 3 (edited package, fresh sandbox): npp [200,200].

The repo snapshot and git status were unchanged afterwards.

**FIXED (R-P1-20):** Whole-module hash in the MODIS key (see fidelity2-modis-cache-key-coverage); the cache-hit re-stamp is then correct.

### [spec] spec-new-02: finder low → verdict confirmed / low

**A deviation in the plan-specified repo-filter sensitivity re-run is never reported** (mshi/analysis/repro_checks.py 32-38, 152-171 (and tests/test_regression.py:57-72))

DESCRIPTION: clean_test re-runs both variants and writes vs_locked for each, comparing with the hash-anchored locked files. repro_checks and the regression tests read only clean_test_rerun_qc.json. A repo-variant re-run that selects another model or moves its Europe numbers therefore gives no DEVIATION row in the Checkpoint table and fails no test. Ground rule 4 asks for such changes to be reported as deviations. clean_test.variants is also outside the lock, so dropping 'repo' goes unnoticed.

EVIDENCE: fixcheck_scripts/spec/scripts/repro_more.py. Setup: a qc re-run that is identical, and a repo re-run that selects XGB/C8 with vs_locked {identical False, selected_same False, max_abs_primary_diff 0.4}. Result: summary {'PASS': 24, 'FAIL': 0, 'DEVIATION': 0, 'STALE': 0, 'NOT RUN': 2, 'INFO': 0}. The only row containing 'repo' is 'SRDB records after repo filters'.

SUGGESTED FIX: Add the row 'Locked test (repo-filter sensitivity): re-run identical to the locked result', reading clean_test_rerun_repo.json with its own PRODUCERS entry. Check both variants' vs_locked and lock in test_locked_rerun_reported_against_locked_result.

VERIFIER: Reproduced, with one correction.

What holds:
- repro_checks reads only clean_test_rerun_qc.json. See PRODUCERS (repro_checks.py:32-38) and :153-171.
- No test reads clean_test_rerun_repo.json. tests/test_regression.py:57-72 covers qc only.
- So a deviating repo-filter re-run gives no DEVIATION row and fails nothing, although the locked plan (ANALYSIS_PLAN_LOCKED.md:18, :4) specifies this sensitivity and ground rule 4 (PROMPT_mshi_v3.md:36) asks for such deviations to be reported.
- clean_test.variants (configs/v3.yaml:221) sits outside the locked block, and verify_lock accepts variants=[qc].

Correction: 'never reported' is overstated. clean_test writes vs_locked into results/clean_test_rerun_repo.json (clean_test.py:273-274). It also returns identical_to_locked for each variant (:275-276), which run() stores in run_log.jsonl (run.py:126). So the deviation is recorded in those two files. It just never reaches the Checkpoint table or the tests.

This is the same class as spec-05 (low). It concerns a secondary sensitivity analysis.

VERIFIER EVIDENCE: Script: fixcheck_scripts/spec-adv/scripts/c2_repo_variant.py, run in a sandbox with out_root set.

Setup:
- qc re-run: a copy of the locked qc JSON with vs_locked identical.
- repo re-run: a copy of the locked repo JSON with XGB/C8 selected, r2 lowered by 0.4, and vs_locked {identical False, selected_same False, max 0.4}.

Results:
- Summary: {'PASS': 24, 'FAIL': 0, 'DEVIATION': 0, 'STALE': 0, 'NOT RUN': 2, 'INFO': 0}.
- No DEVIATION row. 'XGB' does not appear in reproduction_check.md.
- The only rows mentioning 'repo' are 'SRDB records after repo filters' and 'Repo-filter sites: total'.
- Control: when the qc re-run deviates instead, DEVIATION = 1.

Lock check: `verify_lock` with clean_test.variants=['qc'] returns accepted.

**FIXED (R-P1-20):** Reproduction-table row for the repo-filter re-run; `verify_lock` requires every locked variant; regression test covers both (D-P1-9, D-P1-10).

### [spec] spec-new-03: finder low → verdict confirmed / low

**NPP rows report NOT RUN instead of STALE or FAIL, and the 're-run identical' row reports NOT RUN with no note when vs_locked is missing** (mshi/analysis/repro_checks.py 60-63, 118-131, 165-187)

DESCRIPTION: _row maps any value of None to NOT RUN. (a) When modis_points.json comes from another config or code, the NPP and INFO rows say NOT RUN, not STALE, against the docstring, D-P1-17 and README.md:28-30. summary['STALE'] misses them, and test_npp_correlation skips with 'modis_points output missing'. (b) When the extraction is current but r cannot be computed (2 or fewer sites with NPP in both tables, e.g. all-NaN NPP or a key mismatch), the row is NOT RUN with no exception, so the run can exit 0 instead of failing. (c) A re-run JSON without vs_locked gives 'NOT RUN' with an empty note while the six other locked rows PASS. A vs_locked with identical=False and max_abs_primary_diff None raises TypeError at :167, leaving the previous table on disk. Current clean_test always writes a numeric vs_locked, so (c) is latent.

EVIDENCE: fixcheck_scripts/spec/scripts/repro_states.py. State E (modis_points.json written under another config): 'NOT RUN | NPP r … | modis_points.json produced with a different config; re-run `make all`', and the summary's STALE count is 0. State J (MODIS table current, no overlapping keys): NPP 'NOT RUN' with only the method note, no exception, INFO row 0. State F (no vs_locked): 'NOT RUN | Locked test: re-run identical … | note '''. State I: 'TypeError: unsupported format string passed to NoneType.__format__'.

SUGGESTED FIX: In the NPP block, emit STALE when st is STALE. Emit FAIL with n_both_valid when the extraction is current but r is None. Treat a missing or malformed vs_locked as FAIL (or NOT RUN with an explicit note), and format max_abs_primary_diff only when it is numeric.

VERIFIER: Reproduced. _row (repro_checks.py:60-63) maps a value of None to NOT RUN whatever the state. The NPP block (:173-187) computes r only when st == 'OK'.

(a) When modis_points.json is stale, both NPP rows read NOT RUN, not STALE. The note explains why, but summary['STALE'] misses them. This contradicts the module docstring (:11), D-P1-17 and README.md:28-30 ('regression tests fail on it'): the tests do not fail here.

(b) When the extraction is current but r cannot be computed (all-NaN NPP, or no key overlap), the row is NOT RUN, there is no exception and the stage returns ok, so run() exits 0. Partial mitigation: `make test` still fails, because test_npp_correlation raises TypeError on None.

(c) Latent:
- With no vs_locked, the row is NOT RUN with an empty note, but test_locked_rerun_reported_against_locked_result fails.
- With identical=False and max_abs_primary_diff=None, the format at :167 raises TypeError before anything is written (:191-192).
- compare_with_locked returns None only when R has no 'primary', and clean_test always scores. So (c) cannot occur with the current code.

Overall this is labelling and robustness. No wrong number is shown as PASS.

VERIFIER EVIDENCE: Script: fixcheck_scripts/spec-adv/scripts/c3_npp_states.py (sandboxes with out_root). It calls the test functions directly with the sandbox config.

(a) modis_points.json written under another config (smoke.seed=1); the MODIS table itself is current.
- NPP and INFO rows: 'NOT RUN', note 'modis_points.json produced with a different config; re-run `make all`'.
- Summary STALE = 0.
- test_reproduction_table_has_no_fail passes. test_npp_correlation is Skipped with 'NPP check not run (modis_points output missing)'.
- Control (a'): with a current json the NPP row is computed. It reads FAIL there because my synthetic r is 1.0.

(b) all-NaN NPP, and (b2) no key overlap.
- NPP 'NOT RUN' with the method note. INFO row v3 = 0.
- Summary FAIL = 0, and repro_checks returns.
- test_npp_correlation: TypeError: unsupported operand type(s) for -: 'NoneType' and 'float'.

(c) no vs_locked.
- 'NOT RUN' with note ''.
- test_locked_rerun_reported_against_locked_result: AssertionError.

(c2) identical=False, max_abs_primary_diff=None.
- TypeError: unsupported format string passed to NoneType.__format__. No table is written.
- compare_with_locked(R without primary) returns {identical False, max None}.

**FIXED (R-P1-20):** NPP rows STALE when the MODIS result is not current, FAIL when r cannot be computed from a current result; a re-run without a valid `vs_locked` is FAIL; no format error on a missing diff.

### [spec] spec-new-04: finder low → verdict confirmed / low

**max_failed_reads > 0 lets modis_points report ok with partial means that features always refuses** (mshi/data/modis.py 317, 287-288, 305 (configs/v3.yaml:90))

DESCRIPTION: The config exposes max_failed_reads as a tolerance. With a value above 0, modis_points writes partial means and returns ok. load_modis_points and the cache test, however, accept only n_failed_reads == 0. The knob therefore cannot work as a tolerance: the stage says ok while its output is unusable. A modis_points + repro_checks invocation exits 0 with NPP NOT RUN, and the cache is never reused.

EVIDENCE: modis_probe.py state 6 (max_failed_reads 5, 5 persistent failures): modis_points 'ok', exit 0, parquet written with n_failed_reads 5. The NPP row reads 'NOT RUN | modis_points output unusable: … comes from a run with failed reads'. State 7 re-extracts all 3,654 reads. features would raise StaleModisError (modis.py:287-288).

SUGGESTED FIX: Drop the knob (require 0), or make load_modis_points and the cache accept n_failed_reads <= max_failed_reads and record which sites are affected.

VERIFIER: Reproduced. With max_failed_reads > 0 and failures at or under the limit:
- modis_points writes partial means plus meta/record with n_failed_reads > 0 and returns, so the stage is ok (modis.py:317, :322-326).
- load_modis_points refuses any n_failed_reads != 0 (:287-288).
- The cache requires n_failed_reads == 0 (:305).

So a non-zero value is not a working tolerance. The stage reports ok, its output can never be used, and the cache is never reused.

Severity low, because it is latent and fails safe:
- The shipped value is 0 (configs/v3.yaml:90), and its comment describes the zero semantics.
- features would raise StaleModisError and the run would exit 1.
- The NPP row says NOT RUN with an explicit reason.
- No partial mean reaches any downstream number.

The defect is a misleading knob and a misleading 'ok' status.

VERIFIER EVIDENCE: Script: fixcheck_scripts/spec-adv/scripts/c4_max_failed.py.

Setup: absolute sandbox paths with out_root None, so this is not a smoke run. max_failed_reads 5, retries 1. Five points in five tiles. Every NPP-2023 read fails (fake read_windows, fake STAC, fake token).

Results:
- run(['modis_points','repro_checks']) gives exit code 0. run_log: modis_points 'ok', repro_checks 'ok'.
- modis_points.json has n_failed_reads = 5. The parquet exists with npp_n [4,4,4,4,4], i.e. partial means.
- NPP row: 'NOT RUN | modis_points output unusable: …comes from a run with failed reads'.
- load_modis_points(cfg, keys), which is what features calls, raises StaleModisError ('comes from a run with failed reads; re-run stage modis_points').
- A second modis_points call gives cached=False and 40 new read attempts.

**FIXED (R-P1-20):** `max_failed_reads` removed; any failed read fails the stage (DEV-P1-16 (1)).

### [spec] spec-new-05: finder low → verdict confirmed / low

**R-P1-14 misstates the review's severity counts** (docs/DECISIONS.md 219)

DESCRIPTION: R-P1-14 says the 27 findings are '1 high, 8 medium, 18 low'. The review file gives 1 high, 7 medium and 19 low; spec-04 was downgraded from medium to low.

EVIDENCE: `grep '^## \[' docs/review/2026-11-02/package_review.md | sed 's/.*verdict confirmed \/ //' | sort | uniq -c` prints '1 high', '7 medium', '19 low' (27 entries).

SUGGESTED FIX: Change it to '1 high, 7 medium, 19 low'.

VERIFIER: The review file's verdict severities are 1 high, 7 medium and 19 low. R-P1-14 says '1 high, 8 medium, 18 low' (DECISIONS.md:219 at HEAD; line 215 at b74e590). The difference is spec-04, which was downgraded from medium to low (package_review.md:347).

The finder severities would give 2 high, 10 medium and 15 low, so neither reading supports the DECISIONS figure. R-P1-14's 'Medium:' bullet also lists items that the review rates low (the NPP method, and 'FAIL did not stop the run' = spec-06).

This is a documentation-only error in the decision log.

VERIFIER EVIDENCE: Commands:
- `grep '^## \[' docs/review/2026-11-02/package_review.md | sed 's/.*verdict confirmed \/ //' | sort | uniq -c` prints 1 high, 19 low, 7 medium (27 headings).
- I also checked the 27 headings by hand: high is guards-modis-cache-keeps-failed-reads; medium are fidelity-modis-cache, guards-lock-self-anchored, guards-repro-pass-from-stale, guards-non-policy-failures, spec-01, spec-02 and spec-03; all others are low.
- `git show b74e590:docs/DECISIONS.md | grep -n '1 high'` matches line 215, and the same at HEAD matches line 219: 'confirmed (1 high, 8 medium, 18 low)'.

**FIXED (R-P1-20):** R-P1-14 counts corrected to 1 high, 7 medium, 19 low; its medium list corrected.

### [spec] spec-new-06: finder low → verdict confirmed / low

**D-P1-18 says later stages will not run after a reproduction FAIL; run() does not enforce this** (docs/DECISIONS.md 284-285 (mshi/run.py:114, 131-134))

DESCRIPTION: D-P1-18 says 'repro_checks writes the table and then fails if any row is FAIL, so later stages (Phases 2–4) will not run on non-reproducing inputs'. run() skips a stage only when one of its declared dependencies did not finish ok in this invocation. After an error it continues with the remaining stages, and no stage depends on repro_checks. In Phase 1 the consumers of the site tables (modis_points, features, clean_test) also run before repro_checks.

EVIDENCE: fixcheck_scripts/spec/scripts/later_stage.py appends a stage 'phase2_transfer' with deps [build_sites] after repro_checks and uses a failing target. run_log shows repro_checks 'error: ReproductionFailure' and then phase2_transfer 'ok', with exit 1.

SUGGESTED FIX: Make run() skip every stage ordered after a failed repro_checks, or require (and test) deps=['repro_checks'] for Phase 2–4 stages. Optionally check the site-build targets right after build_sites. Reword D-P1-18 to match.

VERIFIER: Reproduced. run() skips a stage only when one of its declared deps already has a non-ok status in this invocation (run.py:114-121). After an exception it records the error and carries on (:131-134). repro_checks has deps [] and is last (:67).

So after a ReproductionFailure, any later stage that does not declare deps=['repro_checks'] still runs. In Phase 1 the site-table consumers (modis_points, features, clean_test) also run before repro_checks (:51-68).

No document or test requires Phase 2–4 stages to depend on repro_checks: a grep of DECISIONS, README, run.py, the Makefile and CHECKPOINT1 finds none. D-P1-18's sentence (DECISIONS.md:284-285) is therefore an unenforced guarantee.

Severity low: no Phase 2–4 stage exists yet, the invocation still exits 1, and the FAIL row is written. The risk is in the future and the statement is inaccurate documentation.

VERIFIER EVIDENCE: Script: fixcheck_scripts/spec-adv/scripts/c6_later_stages.py.

Setup: absolute sandbox paths, srdb_repo_filter_records target set to 4770, and committed build_sites/cosore JSONs written into the sandbox. Three stages appended after repro_checks:
- phase2_nodep, deps []
- phase2_sites, deps [build_sites]
- phase2_gated, deps [repro_checks]

Results:
- Exit code 1.
- repro_checks: 'error: ReproductionFailure'.
- phase2_nodep: 'ok'. phase2_sites: 'ok'. phase2_gated: 'skipped: upstream repro_checks not available'.
- Stage functions that ran after the FAIL: ['phase2_nodep', 'phase2_sites'].

**FIXED (R-P1-20):** `run()` skips every stage ordered after `repro_checks` unless the reproduction gate is open (D-P1-18 (b)).

### [spec] spec-new-07: finder low → verdict confirmed / low

**Reproduction targets and tolerances are anchored only in the config they gate** (configs/v3.yaml 223-253 (tests/test_regression.py:17-24))

DESCRIPTION: The lock is now anchored outside the config. The reproduction targets are not: repro_checks and the regression tests read the same configs/v3.yaml values. The spec-05 fix (europe_n abs 0) can therefore be undone, or a target loosened, by a config edit that makes both the table and `make test` pass. Ground rule 2 forbids tuning to match. Only the site-build counts have an independent anchor (test_build_summary_identical_to_handoff). The locked-test and NPP targets have none.

EVIDENCE: A grep of tests/ for 4771, 0.982, 0.143 and 235 finds only test_regression.py:63, which reads T['europe_n'] from the config. _row('Locked test: Europe n', {'value': 235, 'rel': 0.02}, 236) returns PASS, while {'value': 235, 'abs': 0} returns FAIL.

SUGGESTED FIX: Add a test asserting that cfg['reproduction_targets'] equals a literal copy of the PROMPT §4 table, using the value and tolerance encodings from D-P1-10.

VERIFIER: The core statement holds. repro_checks and the regression tests both read cfg['reproduction_targets'] (test_regression.py:17-24, 57-66). No test holds literal target values. A config-only edit can turn a FAIL into a PASS in both the table and `make test`. I reproduced this for Europe n and for the NPP r tolerance.

Correction, partial refutation: the locked-test targets are not entirely unanchored.
- The 're-run identical to the locked result' row compares against locked result files whose hashes are pinned in code (clean_test.py:46-49, 76-82).
- With europe_n loosened, a changed n still produces a DEVIATION row. The change is therefore still reported as ground rule 4 requires. Only the FAIL/stop and the test failure are lost.
- The site-build counts are anchored independently by test_build_summary_identical_to_handoff. The handoff build_summary.json has every site-build key except cosore_sites, which feeds into the record totals.

The gate that truly has no anchor is NPP r. Exploiting this needs a deliberate config edit, which is visible in git, changes the config hash and must be logged under configs/v3.yaml:3. So severity is low, and this is hardening rather than a functional bug.

VERIFIER EVIDENCE: Searches:
- `grep -rn -E '4771|4,771|0\.982|0\.143|\b235\b|0\.079|\b971\b|1225|\b66\b' tests/*.py` finds nothing.
- The handoff build_summary.json keys are coord_mismatch_*, qc_removed_by, records_after_coord_check, records_after_qc, sites_qc, sites_repo and srdb_repo_filter_records.

Script: fixcheck_scripts/spec-adv/scripts/c7_targets.py. The re-run is a synthetic copy of the locked JSON with primary.n = 236 and vs_locked computed by compare_with_locked. No test is scored.

Results:
- Committed config (exact): ReproductionFailure; Europe n FAIL; test_locked_test_rerun and test_reproduction_table_has_no_fail fail.
- With europe_n set to rel 0.02: summary FAIL 0; Europe n PASS; all three tests pass. The 're-run identical' row is still DEVIATION (max |diff| 1).
- NPP: _row with r = 0.95 gives FAIL at abs 0.01 and PASS at abs 0.05.

**FIXED (R-P1-20):** `tests/test_guards.py::test_reproduction_targets_are_the_briefs`: literal copy of the brief's table, checked against `PROMPT_mshi_v3.md` (D-P1-10).

### [spec] spec-new-08: finder low → verdict confirmed / low

**The new PASS/DEVIATION threshold (1e-9) is a code literal, against the 'every threshold is in configs/v3.yaml' claim** (mshi/analysis/clean_test.py 236, 251 (repro_checks.py:168; README.md:25; configs/v3.yaml:2))

DESCRIPTION: b74e590 added compare_with_locked(atol=1e-9), which decides between PASS and DEVIATION for the re-run row; repro_checks also hard-codes the tolerance label '1e-9'. The value is not in configs/v3.yaml, yet README.md:25, configs/v3.yaml:2 and D-P1-1 say every threshold is in the config. This is the same class as spec-02. The AST test pins it and D-P1-9/D-P1-10 mention it, so it cannot drift silently; but the claim is literally false.

EVIDENCE: `grep -n 'atol\|1e-9' configs/v3.yaml mshi/analysis/*.py` finds only clean_test.py:236, 238, 251 and repro_checks.py:168, and nothing in the config.

SUGGESTED FIX: Move it into the config (e.g. clean_test.deviation_atol) and read it in both places, or qualify the 'every threshold' sentences.

VERIFIER: Confirmed. b74e590 added compare_with_locked(atol=1e-9) (clean_test.py:236, 251). That tolerance decides PASS vs DEVIATION for the re-run row, and repro_checks.py:168 hard-codes the label '1e-9'. configs/v3.yaml has no such key. So 'every … threshold is in configs/v3.yaml' is literally false for this value (README.md:25, configs/v3.yaml:2, D-P1-1 at DECISIONS.md:73).

The consequence is documentation only:
- The value is stated in DECISIONS.md:181 and :195.
- clean_test.py is pinned by the AST test (test_guards.py:314-315), so it cannot drift silently.
- The sentence was already approximate before b74e590: other code-literal thresholds predate the commit and were never flagged. Examples are the 1e-12 slack in _tol_ok (repro_checks.py:56-57), 'both.sum() > 2' (:125) and the download retries=4 / timeout=600 defaults (netutil.py:64).

Low is the right severity, at the lower end.

VERIFIER EVIDENCE: Commands:
- `grep -n 'atol\|1e-9\|deviation_atol\|identical' configs/v3.yaml mshi/analysis/*.py mshi/*.py` finds clean_test.py:236 and :251 and repro_checks.py:168, and nothing in configs/v3.yaml.
- `git diff ee07832 b74e590 -- mshi/analysis/clean_test.py` shows '-def compare_with_locked(R: dict, locked: dict) -> dict:' replaced by '+def compare_with_locked(R: dict, locked: dict, atol: float = 1e-9) -> dict:'.
- `git show ee07832:mshi/analysis/repro_checks.py | grep -n '1e-12\|> 2 else'` matches lines 25, 28 and 58, and the same command on netutil.py shows the retries=4 and timeout=600 defaults. These literals predate b74e590.

Repository check: after all runs, git status --porcelain is empty and the before/after file snapshot (outside .git, .venv and data/raw) is identical.

**FIXED (R-P1-20):** `clean_test.deviation_atol: 1.0e-9` in the config; the 'every threshold' sentences made precise (D-P1-1).
