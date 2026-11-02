"""Second, independent PROXY for training-sample uncertainty with REAL (original-repo) WorldClim bio01/bio12:
OLS log Rs ~ bio01 + ln(bio12), Asia box (v2) -> US box (v2). Fixed-model site bootstrap vs two-sample bootstrap
(Asia resampled with n_a = full, and n_a = 384 drawn from the Asia rows to mimic the locked training size)."""
import numpy as np, pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score
P = "/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/critique_inputs/processed/"
T = "log_rs_annual"
A = pd.read_parquet(P + "training_features_v2.parquet").dropna(subset=[T, "bio01", "bio12"]).reset_index(drop=True)
U = pd.read_parquet(P + "us_validation_features_v2.parquet").dropna(subset=[T, "bio01", "bio12"]).reset_index(drop=True)
D = lambda d: np.c_[d.bio01.values, np.log(d.bio12.values)]
Xa, ya, Xu, yu = D(A), A[T].values, D(U), U[T].values
m = LinearRegression().fit(Xa, ya); p = m.predict(Xu)
print("n_a %d n_u %d  US R2 %.4f (prep_log L47 reports +0.138 on the 463/223 common set)" % (len(ya), len(yu), r2_score(yu, p)))
def fixed(seed, B=2000):
    rng = np.random.default_rng(seed); return np.quantile([r2_score(yu[i], p[i]) for i in (rng.integers(0, len(yu), len(yu)) for _ in range(B))], [.025, .975])
def two(seed, na, B=2000):
    rng = np.random.default_rng(seed); out = []
    for _ in range(B):
        ia = rng.integers(0, len(ya), na); mm = LinearRegression().fit(Xa[ia], ya[ia])
        iu = rng.integers(0, len(yu), len(yu)); out.append(r2_score(yu[iu], mm.predict(Xu[iu])))
    return np.quantile(out, [.025, .975])
for seed in (42, 1, 2):
    f = fixed(seed); t1 = two(seed, len(ya)); t2 = two(seed, 384)
    print("seed %d fixed [%.4f, %.4f] | two-sample n_a=%d [%.4f, %.4f] drop %.4f | two-sample n_a=384 [%.4f, %.4f] drop %.4f" %
          (seed, f[0], f[1], len(ya), t1[0], t1[1], f[0] - t1[0], t2[0], t2[1], f[0] - t2[0]))
