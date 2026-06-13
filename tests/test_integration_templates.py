from __future__ import annotations

import json
import py_compile
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib


ROOT = Path(__file__).resolve().parents[1]


def test_mcp_json_templates_parse() -> None:
    for path in [
        ROOT / "integrations/claude-code/.mcp.json",
        ROOT / "integrations/cursor/mcp.json",
        ROOT / "integrations/gemini-cli/settings.json",
    ]:
        data = json.loads(path.read_text())
        assert "clark" in data["mcpServers"]
        assert data["mcpServers"]["clark"]["command"] == "uv"


def test_codex_toml_template_parses() -> None:
    data = tomllib.loads((ROOT / "integrations/codex/config.toml").read_text())
    assert data["mcp_servers"]["clark"]["command"] == "uv"
    assert data["mcp_servers"]["clark"]["enabled"] is True


def test_hermes_plugin_compiles() -> None:
    py_compile.compile(
        str(ROOT / "integrations/hermes/clark/__init__.py"),
        doraise=True,
    )


def test_benchmark_runner_compiles() -> None:
    py_compile.compile(
        str(ROOT / "benchmark/run_longmemeval.py"),
        doraise=True,
    )


def test_provider_comparison_runner_compiles() -> None:
    py_compile.compile(
        str(ROOT / "benchmark/run_provider_comparison.py"),
        doraise=True,
    )


def test_mcp_http_app_compiles() -> None:
    py_compile.compile(
        str(ROOT / "clark/mcp_http.py"),
        doraise=True,
    )
