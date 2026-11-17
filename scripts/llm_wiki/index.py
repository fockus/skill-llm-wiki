"""Инкрементальное построение атомарного, полностью производного индекса."""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from . import config, documents, graph, store
from .embeddings import make_embedder


def fingerprint(cfg):
    return documents.digest(
        json.dumps({"config": cfg, "parser_version": 5}, sort_keys=True).encode()
    )


def embedding_text(chunk):
    return " / ".join(chunk["heading"]) + "\n" + chunk["text"]


def build(root: Path, lexical_only=False):
    root = root.expanduser().resolve()
    cfg = config.load(root)
    snapshot = documents.inventory(root, cfg)
    parsed = {p: documents.parse(root, p, cfg) for p in snapshot}
    chunks = [
        c for d in parsed.values() for c in documents.chunks(d, cfg["chunk_chars"])
    ]
    nodes, edges, issues = graph.materialize(parsed, chunks, root, cfg)
    model = None if lexical_only else make_embedder(cfg)
    identity = model.identity if model else None
    db = store.connect(root, create=True)
    try:
        previous = store.get(db, "generation")
        cached = {}
        if identity and store.get(db, "model") == identity:
            cached = {
                r["id"]: json.loads(r["vector"])
                for r in db.execute(
                    "SELECT id,vector FROM chunks WHERE vector IS NOT NULL"
                )
            }
        pending = [c for c in chunks if c["id"] not in cached] if model else []
        if pending:
            vectors = model.documents([embedding_text(c) for c in pending])
            if len(vectors) != len(pending):
                raise ValueError("Embedding model вернула неверное число векторов")
            cached.update({c["id"]: v for c, v in zip(pending, vectors)})
        dimension = None
        for c in chunks if model else []:
            value = np.asarray(cached[c["id"]], dtype=float)
            if (
                value.ndim != 1
                or not value.size
                or not np.isfinite(value).all()
                or np.linalg.norm(value) == 0
            ):
                raise ValueError("Некорректный embedding vector")
            if dimension is not None and dimension != len(value):
                raise ValueError("Разные размерности embedding vectors")
            dimension = len(value)
            cached[c["id"]] = (value / np.linalg.norm(value)).tolist()
        if documents.inventory(root, cfg) != snapshot or fingerprint(
            config.load(root)
        ) != fingerprint(cfg):
            raise ValueError("Корпус изменился во время index; повторите команду")
        generation = str(uuid.uuid4())
        db.execute("BEGIN IMMEDIATE")
        try:
            if store.get(db, "generation") != previous:
                raise ValueError(
                    "Параллельный index уже обновил поколение; повторите команду"
                )
            for table in ["search_fts", "chunks", "documents", "edges", "nodes"]:
                db.execute("DELETE FROM " + table)
            db.executemany(
                "INSERT INTO documents VALUES (?,?,?)",
                [
                    (p, snapshot[p], json.dumps(d, ensure_ascii=False))
                    for p, d in parsed.items()
                ],
            )
            db.executemany(
                "INSERT INTO chunks VALUES (?,?,?,?)",
                [
                    (
                        c["id"],
                        c["path"],
                        json.dumps(c, ensure_ascii=False),
                        json.dumps(cached[c["id"]]) if model else None,
                    )
                    for c in chunks
                ],
            )
            db.executemany(
                "INSERT INTO search_fts VALUES (?,?)",
                [(c["id"], embedding_text(c)) for c in chunks],
            )
            db.executemany("INSERT INTO nodes VALUES (?,?,?,?,?)", nodes)
            db.executemany("INSERT INTO edges VALUES (?,?,?,?,?)", edges)
            metadata = dict(
                schema=store.SCHEMA,
                generation=generation,
                inventory=snapshot,
                config=fingerprint(cfg),
                model=identity,
                dimension=dimension,
                mode="hybrid" if model else "fulltext",
                issues=issues,
                updated=datetime.now(timezone.utc).isoformat(),
            )
            for key, value in metadata.items():
                store.put(db, key, value)
            db.commit()
        except BaseException:
            db.rollback()
            raise
        return {
            "root": str(root),
            "generation": generation,
            "documents": len(parsed),
            "chunks": len(chunks),
            "nodes": len(nodes),
            "edges": len(edges),
            "mode": metadata["mode"],
            "embedded_chunks": len(pending),
            "reused_vectors": len(chunks) - len(pending) if model else 0,
            "dimension": dimension,
            "issues": len(issues),
        }
    finally:
        db.close()
