# Alternative metrics — Asia → US transfer

Computed on the held-out US validation set after fitting the model on the
full Asia training set. Same models as Task 2 bootstrap.

| Metric | F: climate-only | B: full features (20) | Notes |
|---|---:|---:|---|
| n_train (Asia, post-NaN drop) | 600 | 588 | F drops fewer rows because its 8-feature subset has higher coverage |
| n_us (post-NaN drop) | 272 | 270 | |
| **R² (log Rs)** | **+0.127** | **+0.020** | primary success metric |
| RMSE (log Rs) | 0.585 | 0.616 | |
| NRMSE (RMSE / range) | 0.155 | 0.163 | normalised by US observed range |
| **Spearman ρ** | **+0.277** | **+0.249** | rank correlation, robust to mean shift |
| MAE (log Rs) | 0.472 | 0.481 | |
| MAE (Rs, g C m⁻² yr⁻¹) | 359 | 364 | original units |
| Median |AE| (Rs) | 269 | 264 | robust to outliers |
| **Tertile accuracy** | **37.1%** | **40.0%** | random baseline = 33.3% |

## Interpretation

On the metrics that distinguish position-and-spread (R², RMSE, NRMSE, MAE)
F climate-only is the better model:
R² +0.127 vs +0.020, RMSE 0.585 vs 0.616.

On the rank-only Spearman test, F also wins, but the gap narrows:
ρ_F = +0.277, ρ_B = +0.249. Both models recover
the broad ordering of US sites by Rs, even though only F recovers the level.

On coarse tertile classification (a much weaker test than R² because it
discards within-tertile information), the two configurations are
essentially tied: F = 37.1%, B = 40.0% 
against a 33.3% random baseline. The confusion matrices show both models
predicting heavily into the middle tertile — the regression-to-mean
signature already documented in pred_std. Tertile accuracy is therefore
not the most decision-relevant metric here; R² and Spearman are.

MAE in original Rs units is large for both configurations
(F: 359, B: 364 g C m⁻² yr⁻¹) against a median observed Rs of
≈760 g C m⁻² yr⁻¹ — i.e. roughly 50% relative error in either case.
Continental upscaling without a vegetation-productivity covariate (MODIS NPP)
cannot resolve the absolute Rs level even when the rank ordering generalises.