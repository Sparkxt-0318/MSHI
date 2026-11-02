# Sweep results — v1 (Run A) + v2 (Item 1 MODIS) combined

| Config | Features | n_train | n_us | CV R² | Transfer R² | 95% CI | CI excl. 0 |
|---|---:|---:|---:|---:|---:|---|---|
| A_baseline | 20 | 588 | 270 | -0.127 | -0.031 | — | — |
| B_heavier_reg | 20 | 588 | 270 | -0.083 | +0.020 | — | — |
| C_shallow_more | 20 | 588 | 270 | -0.054 | -0.001 | — | — |
| D_drop_overfit | 16 | 588 | 270 | -0.139 | -0.024 | — | — |
| E_climate_plus_transferring_soil | 13 | 588 | 270 | -0.128 | +0.008 | — | — |
| F_climate_only | 8 | 600 | 272 | -0.067 | +0.127 | — | — |
| F_NPP | 12 | 463 | 223 | -0.021 | +0.145 | (+0.026, +0.241) | **yes** |
| Full_MODIS | 34 | 463 | 223 | +0.079 | +0.072 | (-0.084, +0.189) | no |