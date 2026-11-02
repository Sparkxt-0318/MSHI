"""Recompute the two AST pins of tests/test_guards.py at several commits (functions copied verbatim)."""
import ast, hashlib, sys
from pathlib import Path

def _strip_docstrings(tree):
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if (isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)) and body
                and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant)
                and isinstance(body[0].value.value, str)):
            node.body = body[1:] or [ast.Pass()]
    return tree

def _ast_digest(paths) -> str:
    h = hashlib.sha256()
    for p in paths:
        tree = _strip_docstrings(ast.parse(Path(p).read_text()))
        h.update(ast.dump(tree, annotate_fields=True, include_attributes=False).encode())
    return h.hexdigest()

def _class_digest(path, name) -> str:
    tree = _strip_docstrings(ast.parse(Path(path).read_text()))
    node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == name)
    return hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest()

base = Path(sys.argv[1])
print("python", sys.version.split()[0])
for rev in ["ee07832", "b74e590", "9e17a36", "a6c00bc", "de236d0"]:
    d = base / rev
    print(rev, "module+spatial", _ast_digest([d / "clean_test.py", d / "spatial.py"])[:16],
          "LockedTest", _class_digest(d / "clean_test.py", "LockedTest")[:16])
# also the live repository files
live = Path("/home/user/MSHI/mshi")
print("live    module+spatial", _ast_digest([live / "analysis" / "clean_test.py", live / "spatial.py"]),
      "LockedTest", _class_digest(live / "analysis" / "clean_test.py", "LockedTest"))
