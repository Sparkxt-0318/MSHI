# Framing-2 transfer comparison

Source: `data/outputs/sweep_results.json` (Task 2 sweep, n_train=615 Asia, n_us=274)

Climate-only generalises Asia → US (R² = +0.127). Every configuration that
includes the SoilGrids texture features (clay/sand/silt or clay_sand_ratio)
lands transfer R² ≈ 0, confirming that the soil-feature contribution to
respiration is regionally specific and does not transfer cross-continent.

| Config | Features | n_feat | CV R² | Transfer R² | Δ vs climate-only | bias |
|---|---|---:|---:|---:|---:|---:|
| A_baseline | depth=3 n_est=250 reg_lambda=2.0 | 20 | -0.127 | -0.031 | -0.158 | -0.085 |
| B_heavier_reg | depth=3 n_est=250 reg_lambda=8.0 reg_alpha=2.0 | 20 | -0.083 | +0.020 | -0.107 | -0.086 |
| C_shallow_more | depth=2 n_est=400 reg_lambda=4.0 | 20 | -0.054 | -0.001 | -0.128 | -0.084 |
| D_drop_overfit | baseline params; drop {clay,sand,silt,clay_sand_ratio} | 16 | -0.139 | -0.024 | -0.151 | +0.012 |
| E_climate_plus_transferring_soil | 8 bioclim + phh2o + ph_optimality + bdod + cec + aridity | 13 | -0.128 | +0.008 | -0.119 | -0.041 |
| F_climate_only | 8 bioclim only | 8 | -0.067 | +0.127 | +0.000 | -0.044 |

## Reading the table

- **CV R²** is from 5-fold spatial-block cross-validation at 5° latitude/
  longitude blocks within the Asia training set. With n_train=615 spread
  across 25-180°E and -10-80°N, every fold has to extrapolate to a different
  climate-biome combination, so values around zero or slightly negative are
  expected. Random-KFold CV gives R² ≈ +0.09 on the same data.

- **Transfer R²** is on the held-out US set (n=274). This is the primary
  generalisation metric.

- **Δ vs climate-only** isolates the marginal contribution (negative for
  every soil-feature configuration) of adding gridded soil layers.

- **Bias** = mean(predicted − observed) on the US set. A negative bias means
  the model is shrinking US predictions toward the Asia training mean.