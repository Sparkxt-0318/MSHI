"""Area D end-to-end, step 5b: direct stage calls (no runner gate) on changed inputs, restored afterwards.
R4: records_analysis.parquet changed -> noise_ceiling and us_r2 must refuse (StaleInputError).
R5: a WorldClim raster changed -> within_continent and aoa_sensitivity must refuse."""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, "/home/user/MSHI")


def mutate(p: Path, col: str) -> None:
    import pandas as pd
    d = pd.read_parquet(p)
    d.loc[d.index[0], col] = d.loc[d.index[0], col] + 0.1
    d.to_parquet(p, index=False)


def call(name, fn, cfg):
    try:
        fn(cfg)
        print(f"   {name}: RAN (no refusal)")
    except Exception as e:  # noqa: BLE001
        print(f"   {name}: {type(e).__name__}: {str(e)[:170]}")


if __name__ == "__main__":
    from mshi.config import load_config
    from mshi.analysis.noise_ceiling import noise_ceiling
    from mshi.analysis.us_r2 import us_r2
    from mshi.analysis.transfer import within_continent
    from mshi.analysis.aoa import aoa_sensitivity
    D = Path(sys.argv[1])
    cfg_path = D / "e2e/v3_sandbox.yaml"
    sb = D / "e2e/sb"
    rec = sb / "derived/records_analysis.parquet"
    shutil.copy2(rec, D / "tmp/rec2.bak")
    mutate(rec, "log_rs")
    print("R4 direct: records_analysis.parquet changed")
    for n, f in (("noise_ceiling", noise_ceiling), ("us_r2", us_r2)):
        call(n, f, load_config(cfg_path))
    shutil.copy2(D / "tmp/rec2.bak", rec)
    tif = sb / "raw/worldclim/2.1/2.5m/wc2.1_2.5m_bio_1.tif"
    shutil.copy2(tif, D / "tmp/bio1b.bak")
    with open(tif, "ab") as fh:
        fh.write(b"x")
    print("R5 direct: wc2.1_2.5m_bio_1.tif changed")
    for n, f in (("within_continent", within_continent), ("aoa_sensitivity", aoa_sensitivity)):
        call(n, f, load_config(cfg_path))
    shutil.copy2(D / "tmp/bio1b.bak", tif)
