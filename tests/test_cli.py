import json
from pathlib import Path
import subprocess
import sys

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/wiki.py"


def run_cli(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True
    )


def test_cli_init_and_ingest_have_machine_readable_results(tmp_path):
    root = tmp_path / "knowledge"
    initialized = run_cli("init", "--root", root, "--title", "Demo")
    assert initialized.returncode == 0, initialized.stderr
    assert json.loads(initialized.stdout)["root"] == str(root)
    source = tmp_path / "note.md"
    source.write_text("A source")
    ingested = run_cli("ingest", source, "--root", root)
    assert ingested.returncode == 0, ingested.stderr
    assert (root / json.loads(ingested.stdout)["source_path"]).read_text() == "A source"


def test_cli_missing_root_does_not_create_project(tmp_path):
    result = run_cli("ingest", tmp_path / "absent.md", "--root", tmp_path / "absent")
    assert result.returncode == 2
    assert result.stdout == ""
    assert json.loads(result.stderr)["ok"] is False
    assert not (tmp_path / "absent").exists()


@pytest.mark.parametrize(
    "arguments",
    [
        ["unknown"],
        ["search", "query"],
        ["search", "query", "--root", "/tmp", "--mode", "fake"],
        ["search", "query", "--root", "/tmp", "--limit", "0"],
        ["read", "wiki/index.md", "--root", "/tmp", "--start", "0"],
    ],
)
def test_cli_invalid_arguments_return_json_error(arguments):
    result = run_cli(*arguments)
    assert result.returncode == 2
    assert result.stdout == ""
    assert json.loads(result.stderr)["ok"] is False
