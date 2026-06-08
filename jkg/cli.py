"""Console entrypoint for the JKG command line interface."""

from __future__ import annotations

import runpy
import sys
import os


def main(argv: list[str] | None = None) -> None:
    """Run the legacy module CLI through an installable console script."""
    old_argv = sys.argv[:]
    args = list(argv if argv is not None else old_argv[1:])
    if args[:1] == ["doctor"]:
        from .doctor import main as doctor_main

        raise SystemExit(doctor_main())

    if args[:1] == ["migrate"]:
        if os.environ.get("JKG_DATABASE_URL"):
            from .db import migrate_postgres

            result = migrate_postgres()
            import json

            print(json.dumps(result, indent=2, ensure_ascii=False))
            return
        print("No JKG_DATABASE_URL set; legacy SQLite schema initializes on first use.")
        return

    if args[:1] == ["serve"]:
        try:
            import uvicorn
        except ImportError as exc:
            raise SystemExit("Install server dependencies with: pip install 'jkg[server]'") from exc

        host = "0.0.0.0"
        port = int(args[1]) if len(args) > 1 else 8000
        uvicorn.run("jkg.server:app", host=host, port=port)
        return

    if args[:1] == ["mcp"]:
        try:
            from .mcp_server import main as mcp_main
        except ImportError as exc:
            raise SystemExit("Install MCP dependencies with: pip install 'jkg[mcp]'") from exc

        transport = args[1] if len(args) > 1 else "stdio"
        mcp_main(transport=transport)
        return

    sys.argv = [old_argv[0] if old_argv else "jkg", *args]
    try:
        runpy.run_module("jkg.memory", run_name="__main__")
    finally:
        sys.argv = old_argv
