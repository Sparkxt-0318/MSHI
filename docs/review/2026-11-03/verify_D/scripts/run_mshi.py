"""Run the pipeline entry point (python -m mshi.run) with the repository on sys.path (python -I -B).
Guarded by __main__: noise_ceiling starts worker processes with the spawn method, which re-imports this file."""
import sys
sys.path.insert(0, "/home/user/MSHI")

if __name__ == "__main__":
    from mshi.run import main
    sys.exit(main(sys.argv[1:]))
