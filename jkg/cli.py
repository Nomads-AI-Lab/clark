"""Console entrypoint for the JKG command line interface."""

from __future__ import annotations

import runpy
import sys


def main(argv: list[str] | None = None) -> None:
    """Run the legacy module CLI through an installable console script."""
    old_argv = sys.argv[:]
    sys.argv = [old_argv[0] if old_argv else "jkg", *(argv if argv is not None else old_argv[1:])]
    try:
        runpy.run_module("jkg.memory", run_name="__main__")
    finally:
        sys.argv = old_argv

