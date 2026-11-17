"""Актуальность индекса, диагностика корпуса и адресное чтение источников."""

import json
from pathlib import Path

from . import config, documents, store


def fresh(root, db):
    from .index import fingerprint

    cfg = config.load(root)
    if store.get(db, "inventory") != documents.inventory(root, cfg) or store.get(
        db, "config"
    ) != fingerprint(cfg):
        raise ValueError("Индекс устарел (stale); выполните index")
    return cfg


def status(root: Path):
    root = root.expanduser().resolve()
    cfg = config.load(root)
    if not (root / ".index/wiki.sqlite3").exists():
        return {
            "root": str(root),
            "indexed": False,
            "stale": True,
            "configured_model": cfg["model"],
        }
    db = store.connect(root)
    try:
        stale = False
        try:
            fresh(root, db)
        except ValueError:
            stale = True
        counts = {
            t: db.execute("SELECT count(*) FROM " + t).fetchone()[0]
            for t in ["documents", "chunks", "nodes", "edges"]
        }
        return {
            "root": str(root),
            "indexed": True,
            "stale": stale,
            **counts,
            **{
                k: store.get(db, k)
                for k in ["generation", "mode", "model", "dimension", "updated"]
            },
        }
    finally:
        db.close()


def lint(root: Path):
    root = root.expanduser().resolve()
    db = store.connect(root)
    try:
        fresh(root, db)
        issues = store.get(db, "issues", [])
        linked = {
            r[0] for r in db.execute("SELECT dst FROM edges WHERE kind != 'contains'")
        }
        for row in db.execute("SELECT path,data FROM documents"):
            doc = json.loads(row["data"])
            if row["path"].startswith("wiki/") and row["path"] not in {
                "wiki/index.md",
                "wiki/log.md",
            }:
                if "file:" + row["path"] not in linked and not any(
                    n.startswith("section:" + row["path"] + "#") for n in linked
                ):
                    issues.append(
                        {
                            "kind": "orphan_page",
                            "path": row["path"],
                            "severity": "warning",
                        }
                    )
                if not any(link["kind"] == "source" for link in doc["links"]):
                    issues.append(
                        {
                            "kind": "missing_provenance",
                            "path": row["path"],
                            "severity": "warning",
                        }
                    )
        for issue in issues:
            issue.setdefault("severity", "error")
        return {
            "ok": not any(i["severity"] == "error" for i in issues),
            "issues": issues,
            "generation": store.get(db, "generation"),
        }
    finally:
        db.close()


def read_document(root: Path, path: str, start=1, end=100):
    root = root.expanduser().resolve()
    cfg = config.load(root)
    if not documents.permitted(root, path, cfg):
        raise ValueError("Путь вне разрешённого корпуса или содержит symlink")
    target = config.safe_path(root, path)
    if not target.is_file():
        raise ValueError("Документ не найден: " + path)
    if target.stat().st_size > cfg["max_file_bytes"]:
        raise ValueError("Файл превышает max_file_bytes")
    if start < 1 or end < start or end - start >= 500:
        raise ValueError("Допустимо читать 1..500 строк, начиная с 1")
    body, locator = documents.extract(target)
    if locator == "asset":
        raise ValueError("Формат файла не поддерживает текстовое чтение")
    lines = body.splitlines()
    return {
        "path": path,
        "absolute_path": str(target),
        "locator": locator,
        "start_line": start,
        "end_line": min(end, len(lines)),
        "total_lines": len(lines),
        "text": "\n".join(lines[start - 1 : end]),
        "sha256": documents.digest(target.read_bytes()),
    }
