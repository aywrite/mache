# SPDX-License-Identifier: MIT
# Copyright (C) 2022-2026 Andrew Wright

"""What the tests need to reach the package two ways: by import, and by the
command line a consumer runs.

The command line is `python3 -m mache.<tool>` with the repository root on
`PYTHONPATH`, which is what the composite action arranges for a job and so what
a caller actually runs. The path is put on both this process's `sys.path` and
the environment the tests start subprocesses with, so the tests pass from a
clone with nothing installed as well as from an install.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(ROOT))
os.environ["PYTHONPATH"] = os.pathsep.join(
    [str(ROOT), *([os.environ["PYTHONPATH"]] if os.environ.get("PYTHONPATH") else [])]
)


def command(tool: str) -> list[str]:
    """The argv a caller runs the named tool with."""
    return [sys.executable, "-m", f"mache.{tool}"]
