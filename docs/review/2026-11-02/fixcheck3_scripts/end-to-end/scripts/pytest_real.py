"""`make test` at HEAD, read-only: real config, cache provider off, basetemp in scratch, no bytecode written."""
import sys
sys.path.insert(0, "/home/user/MSHI")
import pytest
sys.exit(pytest.main(["-p", "no:cacheprovider", f"--basetemp={sys.argv[1]}", "-q", "-rs", "-o", "console_output_style=classic",
                      "/home/user/MSHI/tests", *sys.argv[2:]]))
