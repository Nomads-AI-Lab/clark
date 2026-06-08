import json
import os
import subprocess
import sys


def test_package_exports_hybrid_memory():
    from jkg import HybridMemory

    assert HybridMemory.__name__ == "HybridMemory"


def test_module_cli_stats_uses_configured_db_path(tmp_path):
    db_path = tmp_path / "jkg.db"
    env = {**os.environ, "JKG_DB_PATH": str(db_path)}

    result = subprocess.run(
        [sys.executable, "-m", "jkg.memory", "stats"],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )

    payload = json.loads(result.stdout)
    assert payload["entities"] == 0
    assert payload["facts"] == 0
    assert db_path.exists()


def test_console_entrypoint_stats_uses_configured_db_path(tmp_path):
    db_path = tmp_path / "jkg-console.db"
    env = {**os.environ, "JKG_DB_PATH": str(db_path)}

    result = subprocess.run(
        ["jkg", "stats"],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )

    payload = json.loads(result.stdout)
    assert payload["relations"] == 0
    assert payload["episodes"] == 0
    assert db_path.exists()


def test_console_entrypoint_doctor_reports_environment(tmp_path):
    db_path = tmp_path / "doctor.db"
    env = {**os.environ, "JKG_DB_PATH": str(db_path)}

    result = subprocess.run(
        ["jkg", "doctor"],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )

    payload = json.loads(result.stdout)
    assert payload["overall_ok"] is True
    assert payload["python"]["ok"] is True
    assert payload["package"]["version"] == "7.0.0"
    assert payload["db_path"]["path"] == str(db_path)


def test_console_entrypoint_migrate_without_database_url_reports_sqlite_mode(tmp_path):
    env = {**os.environ, "JKG_DB_PATH": str(tmp_path / "legacy.db")}
    env.pop("JKG_DATABASE_URL", None)

    result = subprocess.run(
        ["jkg", "migrate"],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )

    assert "legacy SQLite schema initializes on first use" in result.stdout
