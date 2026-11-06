"""Restore the pre-MR348 QLI sources for the full base build only."""
from pathlib import Path
import sys
root=Path(sys.argv[1]).resolve()
for source in (Path(__file__).parent/'base-qli').glob('*.py'):
    targets=list((root/'samples').rglob(source.name))
    if len(targets)!=1:raise SystemExit('ambiguous base QLI source: '+source.name)
    targets[0].write_bytes(source.read_bytes())
