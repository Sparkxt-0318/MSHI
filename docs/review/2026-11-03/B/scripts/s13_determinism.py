"""Determinism: two separate processes (synthA, synthB) of the same sandbox run; compare result JSONs (excluding
nothing), prediction tables and figures byte by byte; and the recorded _outputs/_inputs."""
import sys, json, hashlib
from pathlib import Path
A, B = Path(sys.argv[1]), Path(sys.argv[2])
def h(p): return hashlib.sha256(p.read_bytes()).hexdigest()
for rel in ["out/results/transfer_matrix.json", "out/results/within_continent.json",
            "out/data/interim/transfer_predictions_qc.parquet", "out/data/interim/within_predictions_qc.parquet",
            "out/figures/phase2/transfer_matrix.png", "out/figures/phase2/transfer_matrix.pdf",
            "out/figures/phase2/within_continent.png", "out/figures/phase2/within_continent.pdf"]:
    print(f"{rel:55s} identical={h(A / rel) == h(B / rel)}")
for name in ("transfer_matrix.json", "within_continent.json"):
    r = json.loads((A / "out/results" / name).read_text())
    print(name, "exploratory:", r.get("exploratory"), "_inputs:", sorted(r.get("_inputs", {})), "_outputs:", sorted(r.get("_outputs", {})))
