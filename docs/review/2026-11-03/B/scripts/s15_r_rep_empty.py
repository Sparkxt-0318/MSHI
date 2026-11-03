"""knndm.py docstring claim: 'exactly k clusters of n/k sites and no smaller one: CAST stops (rep over an empty set of
folds), here the split is used'. CAST runs
    tabclust$clust_k[is.na(tabclust$clust_k)] <- rep(clust_i, ceiling(nk/length(clust_i)))[1:sum(is.na(...))]
with clust_i = integer(0), i.e. rep(integer(0), Inf). In R's do_rep (src/main/seq.c, R trunk, fetched from the
wch/r-source mirror) a zero-length x returns before 'times' is validated; so rep(integer(0), Inf) is integer(0),
integer(0)[c(1, 0)] is NA, and assigning NA to the empty selection is a no-op: CAST does not stop and uses the
split, as the port does. This script locates the two code paths and prints their line numbers."""
import re, sys
src = open(sys.argv[1], encoding="utf-8").read().splitlines()
start = next(i for i, l in enumerate(src) if l.startswith("attribute_hidden SEXP do_rep("))
early = next(i for i in range(start, len(src)) if re.search(r"if\(lx == 0\)", src[i]))
ret = next(i for i in range(early, len(src)) if "return a;" in src[i])
times = next(i for i in range(start, len(src)) if '_("invalid \'%s\' argument"), "times"' in src[i])
print(f"do_rep starts at line {start+1}; zero-length early return at lines {early+1}-{ret+1}; first 'times' validation error at line {times+1}")
print("early return precedes the times check:", ret < times)
for i in range(early, ret + 1):
    print(f"{i+1:5d}: {src[i]}")
