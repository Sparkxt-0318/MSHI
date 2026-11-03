"""mshi.figures.style.save_figure: byte-identical PNG and PDF for the same figure drawn twice (in two processes
via SOURCE_DATE_EPOCH-free environments), and no timestamps in the files."""
import hashlib, subprocess, sys, re
from pathlib import Path
out = Path(sys.argv[1])
code = r'''
import sys; sys.path.insert(0, "/home/user/MSHI")
from mshi.figures.style import save_figure, PALETTE, CONTINENT_COLOURS
import matplotlib.pyplot as plt, numpy as np
fig, ax = plt.subplots(figsize=(4, 3))
for i, (c, col) in enumerate(CONTINENT_COLOURS.items()):
    ax.errorbar([i], [0.5 + 0.05 * i], yerr=[[0.1], [0.2]], fmt="o", color=col, label=c)
ax.set_xlabel("continent (geographic)"); ax.set_ylabel("ceiling, R² ±"); ax.legend(); ax.set_title("Noise ceiling – test")
print(save_figure(fig, sys.argv[1]))
'''
for k in (1, 2):
    subprocess.run([sys.executable, "-I", "-B", "-c", code, str(out / f"fig{k}")], check=True)
for ext in ("png", "pdf"):
    a, b = (out / f"fig{k}.{ext}").read_bytes(), (out / f"fig2.{ext}").read_bytes()
    a = (out / f"fig1.{ext}").read_bytes()
    print(ext, "identical across processes:", a == b, hashlib.sha256(a).hexdigest()[:12])
pdf = (out / "fig1.pdf").read_bytes()
print("PDF date fields:", re.findall(rb"/(CreationDate|ModDate)", pdf), "; Producer/Creator:", re.findall(rb"/(Producer|Creator)", pdf))
png = (out / "fig1.png").read_bytes()
print("PNG text chunks:", re.findall(rb"tEXt([A-Za-z]+)", png))
