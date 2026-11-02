import os, shutil, sys
sys.dont_write_bytecode = True
sys.path.insert(0, "/home/user/MSHI/tests"); sys.path.insert(0, "/home/user/MSHI")
import test_guards as TG
from pathlib import Path
W = Path("/tmp/claude-0/-home-user-MSHI/efd5d835-bc76-551b-aa46-a19c5a194351/scratchpad/fixcheck/guards/work/t13"); shutil.rmtree(W, ignore_errors=True); W.mkdir(parents=True)
ct = Path("/home/user/MSHI/mshi/analysis/clean_test.py").read_text(); sp = Path("/home/user/MSHI/mshi/spatial.py").read_text()
def dig(c, s):
    (W / "c.py").write_text(c); (W / "s.py").write_text(s); return TG._ast_digest([W / "c.py", W / "s.py"])
print("unchanged == pin:", dig(ct, sp) == TG.LOCKED_CODE_AST_SHA256)
edits = {"tie rule < -> <=": ct.replace('r["n_pred"] < best["n_pred"]', 'r["n_pred"] <= best["n_pred"]'),
         "comment only": ct.replace("# upper whisker", "# whisker (edited comment)"),
         "docstring only": ct.replace("The locked analysis.", "The locked analysis (edited)."),
         "sd==0 guard": ct.replace("sd[sd == 0] = 1", "sd[sd == 0] = 2")}
for k, v in edits.items():
    print(f"{k:20s} changed text: {v != ct} | pin still matches: {dig(v, sp) == TG.LOCKED_CODE_AST_SHA256}")
print("spatial shuffle edit pin matches:", dig(ct, sp.replace("rng.shuffle(u)", "u = u[::-1]")) == TG.LOCKED_CODE_AST_SHA256)
