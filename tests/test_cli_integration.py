"""Реальные CLI-процессы: путь запуска не совпадает с проектом или runtime."""

import json
from pathlib import Path
import subprocess
import sys


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/wiki.py"


def invoke(cwd, *arguments, code=0):
    process = subprocess.run(
        [sys.executable, str(SCRIPT), *map(str, arguments)],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    assert process.returncode == code, process.stdout + process.stderr
    if code:
        assert process.stdout == ""
        response = json.loads(process.stderr)
        assert response["ok"] is False
        return response
    assert process.stderr == ""
    return json.loads(process.stdout)


def test_cli_full_lifecycle_from_external_cwd_preserves_citations_and_graph(tmp_path):
    root = tmp_path / "Проект" / "llm-wiki"
    launch = tmp_path / "external-cwd"
    launch.mkdir()
    source = tmp_path / "Обзор рынка.md"
    source.write_text(
        "# Исследование\n\n## Риск ликвидности\n"
        "Редкиймаркер подтверждён первичными данными.\n",
        encoding="utf-8",
    )

    initialized = invoke(launch, "init", "--root", root, "--title", "Исследования")
    assert initialized["root"] == str(root.resolve())
    ingested = invoke(launch, "ingest", source, "--root", root)
    indexed = invoke(launch, "index", "--root", root, "--lexical-only")
    assert indexed["mode"] == "fulltext"
    assert indexed["embedded_chunks"] == 0
    found = invoke(
        launch,
        "search",
        "Редкиймаркер",
        "--root",
        root,
        "--mode",
        "fulltext",
        "--hops",
        "0",
    )
    hit = found["hits"][0]
    assert hit["path"] == ingested["source_path"]
    assert hit["heading"] == ["Исследование", "Риск ликвидности"]
    assert hit["locator"] == "line"
    read = invoke(
        launch,
        "read",
        hit["path"],
        "--root",
        root,
        "--start",
        hit["start_line"],
        "--end",
        hit["end_line"],
    )
    assert "Редкиймаркер" in read["text"]
    assert read["sha256"] == hit["sha256"]
    linked = invoke(
        launch,
        "graph",
        "--root",
        root,
        "--node",
        "file:" + ingested["note_path"],
        "--hops",
        "1",
    )
    assert any(
        edge["kind"] == "source" and edge["dst"] == "file:" + ingested["source_path"]
        for edge in linked["edges"]
    )
    assert any(node["path"] == ingested["source_path"] for node in linked["nodes"])
    state = invoke(launch, "status", "--root", root)
    assert state["indexed"] is True and state["stale"] is False
    assert state["generation"] == indexed["generation"]
    assert invoke(launch, "lint", "--root", root)["ok"] is True
    assert (root / ingested["source_path"]).read_bytes() == source.read_bytes()
    assert list(launch.iterdir()) == []


def test_cli_changed_page_fails_stale_until_reindex_then_replaces_hits(tmp_path):
    root = tmp_path / "wiki-root"
    launch = tmp_path / "outside"
    launch.mkdir()
    invoke(launch, "init", "--root", root)
    page = root / "wiki/Изменяемая.md"
    page.write_text("# Аналитика\nСтарыймаркер\n", encoding="utf-8")
    first = invoke(launch, "index", "--root", root, "--lexical-only")
    assert invoke(
        launch, "search", "Старыймаркер", "--root", root, "--mode", "fulltext"
    )["hits"]

    page.write_text("# Аналитика\nНовыймаркер\n", encoding="utf-8")
    assert invoke(launch, "status", "--root", root)["stale"] is True
    failure = invoke(
        launch, "search", "Старыймаркер", "--root", root, "--mode", "fulltext", code=2
    )
    assert "stale" in failure["error"]
    second = invoke(launch, "index", "--root", root, "--lexical-only")
    assert second["generation"] != first["generation"]
    assert invoke(launch, "status", "--root", root)["stale"] is False
    assert (
        invoke(launch, "search", "Старыймаркер", "--root", root, "--mode", "fulltext")[
            "hits"
        ]
        == []
    )
    assert (
        invoke(launch, "search", "Новыймаркер", "--root", root, "--mode", "fulltext")[
            "hits"
        ][0]["path"]
        == "wiki/Изменяемая.md"
    )


def test_cli_lexical_index_cannot_silently_satisfy_semantic_query(tmp_path):
    root = tmp_path / "wiki-root"
    invoke(tmp_path, "init", "--root", root)
    invoke(tmp_path, "index", "--root", root, "--lexical-only")
    error = invoke(
        tmp_path,
        "search",
        "Исследование рынка",
        "--root",
        root,
        "--mode",
        "semantic",
        code=2,
    )
    assert "embedding" in error["error"]


def test_cli_read_rejects_traversal_and_lint_broken_link_is_json_error(tmp_path):
    root = tmp_path / "wiki-root"
    invoke(tmp_path, "init", "--root", root)
    invoke(tmp_path, "read", "../secret.txt", "--root", root, code=2)
    (root / "wiki/links.md").write_text("# Links\n[Missing](missing.md)\n")
    invoke(tmp_path, "index", "--root", root, "--lexical-only")
    report = invoke(tmp_path, "lint", "--root", root, code=2)
    assert any(issue["kind"] == "broken_link" for issue in report["issues"])
