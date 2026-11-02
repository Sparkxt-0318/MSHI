"""Run the UNMODIFIED handoff prototype modis_points_lst.py against the fake catalog (STAC + token faked).
usage: run_proto.py OUT.parquet [ties]"""
import os, runpy, sys, types
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fakepc
import requests
requests.get = lambda url, timeout=None, **k: types.SimpleNamespace(json=lambda: {"token": "tok"})
fakepc.FakeClient.tiles = eval(open(os.path.join(HERE, "tiles.txt")).read())
fakepc.FakeClient.ties = len(sys.argv) > 2 and sys.argv[2] == "ties"
mod = types.ModuleType("pystac_client")
mod.Client = fakepc.FakeClient
sys.modules["pystac_client"] = mod
out = sys.argv[1]
sys.argv = [os.path.join(HERE, "proto_modis_points_lst.py"), os.path.join(HERE, "sites.csv"), out]
runpy.run_path(sys.argv[0], run_name="__main__")
