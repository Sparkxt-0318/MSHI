"""spec-08: for every pin in requirements-lock.txt, does PyPI have a wheel installable on macOS arm64/x86_64 and
Windows amd64 for CPython 3.13 (marker-excluded lines skipped)? Uses the PyPI JSON API only (no installs)."""
import sys, json, re
import requests
from packaging.tags import Tag, cpython_tags, compatible_tags, mac_platforms
from packaging.utils import parse_wheel_filename
from packaging.requirements import Requirement

lock = open(sys.argv[1]).read().splitlines()
plats = {
    "macos-arm64": list(mac_platforms((12, 0), "arm64")),
    "macos-x86_64": list(mac_platforms((12, 0), "x86_64")),
    "win-amd64": ["win_amd64"],
}
envs = {"macos-arm64": {"platform_system": "Darwin", "platform_machine": "arm64", "sys_platform": "darwin"},
        "macos-x86_64": {"platform_system": "Darwin", "platform_machine": "x86_64", "sys_platform": "darwin"},
        "win-amd64": {"platform_system": "Windows", "platform_machine": "AMD64", "sys_platform": "win32"}}
tagsets = {k: set(cpython_tags((3, 13), platforms=v)) | set(compatible_tags((3, 13), "cp313", platforms=v)) for k, v in plats.items()}
bad = {k: [] for k in plats}
for line in lock:
    line = line.strip()
    if not line or line.startswith("#"):
        continue
    req = Requirement(line)
    ver = str(req.specifier).lstrip("=")
    js = requests.get(f"https://pypi.org/pypi/{req.name}/{ver}/json", timeout=60).json()
    files = [u["filename"] for u in js["urls"]]
    wheels = [f for f in files if f.endswith(".whl")]
    has_sdist = any(f.endswith((".tar.gz", ".zip")) for f in files)
    for k in plats:
        env = {"python_version": "3.13", "python_full_version": "3.13.0", "implementation_name": "cpython",
               "platform_python_implementation": "CPython", "os_name": "nt" if k.startswith("win") else "posix",
               **envs[k]}
        if req.marker is not None and not req.marker.evaluate(env):
            continue
        ok = any(set(parse_wheel_filename(w)[3]) & tagsets[k] for w in wheels)
        if not ok:
            bad[k].append(f"{req.name}=={ver} (sdist={'yes' if has_sdist else 'no'})")
for k, v in bad.items():
    print(k, "missing wheel:", v)
