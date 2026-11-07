"""Compatibility entry point; build the current checkout without a base wheel."""
import os
from pathlib import Path
import subprocess
import sys

if __name__ == "__main__":
    raise SystemExit(subprocess.call([
        sys.executable, str(Path(__file__).with_name("build_mr348.py")),
        "--work-root", os.environ["ARENA_BUILD_ROOT"], *sys.argv[1:]
    ]))
