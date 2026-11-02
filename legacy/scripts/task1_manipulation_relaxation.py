"""Task 1 — manipulation-flag relaxation pass (NEGATIVE RESULT, REVERTED).

This script reports the pre-dedup gain from relaxing the SRDB manipulation
filter. The current filter keeps NaN / 'Control' / 'control' / 'None' /
empty strings. The relaxed filter additionally keeps measurement-methodology
labels (Collar depth, Sampling/Trenched collars, etc.), landscape
characterizations (Hydrogeomorphic setting), and explicit absence-of-treatment
labels (No grazing, Undrained-unplanted).

Result on the 7,792 records with non-null Rs_annual after the [50, 4500]
g C m-2 yr-1 range filter:

    CURRENT filter   total 4,901   Asia 2,170   US 1,040
    RELAXED filter   total 4,931   Asia 2,177   US 1,049
                                   gain +7      gain +9

The gain is dominated by Hydrogeomorphic setting (US-only, +9) and
collar-related methodology labels (mostly outside both regions). All
pre-dedup. After the 5 km spatial dedup the surviving Asia gain is
expected to be 0–3 sites.

Per the overnight instruction ("If the result is fewer than +50 Asian
sites, this isn't worth the complexity — revert"), the relaxation is
NOT applied to src/build_target.py. We proceed with Run-A Tasks 2-6
using the existing 615-Asia / 274-US training set.
"""
import pandas as pd

df = pd.read_csv("/home/user/MSHI/data/raw/srdb/srdb-data.csv", low_memory=False)
df = df[df["Rs_annual"].notna()].copy()
df = df[(df["Rs_annual"] >= 50) & (df["Rs_annual"] <= 4500)]
df["Manipulation"] = df["Manipulation"].astype(str).str.strip()
df["is_asia"] = df["Latitude"].between(-10, 80) & df["Longitude"].between(25, 180)
df["is_us"] = df["Latitude"].between(24, 50) & df["Longitude"].between(-125, -66)

# Current filter
current_keep = (df["Manipulation"].isin(["nan", "None", "Control", "control", ""])
                | df["Manipulation"].isna())
cur = df[current_keep]

# Maximally relaxed filter — keep methodology / observational / no-treatment labels
relax_extras = {
    "Collar depth", "Shallow Collars", "Deep Collars",
    "Sampling collars, SC", "Trenched collars",
    "Hydrogeomorphic setting",
    "No grazing", "Undrained, unplanted",
    "Observational", "Monitoring", "Baseline", "Natural",
    "Reference", "Undisturbed",
}
relax_keep = current_keep | df["Manipulation"].isin(list(relax_extras))
rel = df[relax_keep]

print(f"CURRENT filter:  total {len(cur)},  Asia {cur.is_asia.sum()},  US {cur.is_us.sum()}")
print(f"RELAXED filter:  total {len(rel)},  Asia {rel.is_asia.sum()},  US {rel.is_us.sum()}")
print(f"Pre-dedup gain:  +{rel.is_asia.sum() - cur.is_asia.sum()} Asia, "
      f"+{rel.is_us.sum() - cur.is_us.sum()} US")
print("\nVerdict: gain << 50 Asia threshold. Reverted; not applied to build_target.py.")
