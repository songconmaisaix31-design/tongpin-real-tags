#!/usr/bin/env python3
from pathlib import Path
import os
import subprocess
import sys

root = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
hook = root / ".githooks" / "pre-commit"
if not hook.exists():
    print(f"missing hook: {hook}", file=sys.stderr)
    raise SystemExit(2)
try:
    hook.chmod(hook.stat().st_mode | 0o111)
except OSError:
    pass
subprocess.run(["git", "config", "core.hooksPath", ".githooks"], cwd=root, check=True)
print("installed repository hooks: .githooks")
