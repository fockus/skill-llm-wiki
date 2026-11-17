"""Fulltext + локальные vectors + ограниченное расширение по документным связям."""

import json
import re
from collections import defaultdict
from pathlib import Path, PurePosixPath

import numpy as np

from . import store
from .embeddings import make_embedder
from .health import fresh


def lexical(db, question):
    tokens = list(dict.fromkeys(re.findall(r"\w+", question, flags=re.UNICODE)))[:64]
    if not tokens:
        return []
    expression = " OR ".join('"' + t + '"' for t in tokens)
    return [
        r[0]
        for r in db.execute(
            "SELECT id FROM search_fts WHERE search_fts MATCH ? ORDER BY bm25(search_fts),id",
            (expression,),
        )
    ]


def semantic(chunks, vectors, model, question):
    q = np.asarray(model.question(question), dtype=float)
    if q.ndim != 1 or not q.size or not np.isfinite(q).all() or np.linalg.norm(q) == 0:
        raise ValueError("Некорректный query embedding")
    if not chunks:
        return []
    matrix = np.asarray([vectors[c] for c in chunks], dtype=float)
    if matrix.ndim != 2 or matrix.shape[1] != len(q):
        raise ValueError("Embedding dimension mismatch; перестройте индекс")
    scores = matrix @ (q / np.linalg.norm(q))
    values = dict(zip(chunks, scores))
    return sorted(chunks, key=lambda c: (-float(values[c]), c))


def related(db, path, hops):
    edges = [
        dict(r)
        for r in db.execute("SELECT * FROM edges WHERE kind IN ('links','source')")
        if r["src"].startswith(("file:", "section:"))
        and r["dst"].startswith(("file:", "section:"))
    ]

    def file_of(node):
        return node.split(":", 1)[1].split("#", 1)[0]

    seen = {path}
    frontier = [(path, [])]
    for _ in range(hops):
        nxt = []
        for current, chain in frontier:
            prioritized = sorted(
                edges,
                key=lambda e: (
                    file_of(e["src"]) != current,
                    e["kind"] != "source",
                    e["src"],
                    e["dst"],
                ),
            )
            for edge in prioritized:
                a, b = file_of(edge["src"]), file_of(edge["dst"])
                target = b if a == current else a if b == current else None
                if not target or target in seen:
                    continue
                seen.add(target)
                trace = chain + [
                    dict(
                        kind=edge["kind"],
                        source=edge["src"],
                        target=edge["dst"],
                        evidence_path=edge["source_path"],
                        evidence_line=edge["source_line"],
                    )
                ]
                yield target, trace
                nxt.append((target, trace))
                if len(seen) >= 100:
                    return
        frontier = nxt


def section_candidates(path, via, candidates, chunks, document):
    """Ссылка с anchor ограничивает контекст целевым разделом и его детьми."""
    target = next(
        (
            node
            for node in [via[-1]["target"], via[-1]["source"]]
            if node.startswith("section:" + path + "#")
        ),
        None,
    )
    if not target:
        return candidates
    anchor = target.split("#", 1)[1]
    headings = document["headings"]
    section = next(h for h in headings if h["slug"] == anchor)
    end = next(
        (
            h["line"]
            for h in headings
            if h["line"] > section["line"] and h["level"] <= section["level"]
        ),
        float("inf"),
    )
    return [c for c in candidates if section["line"] <= chunks[c]["start_line"] < end]


def query(
    root: Path,
    query: str,
    mode="hybrid",
    limit=5,
    hops=1,
    scope="",
    include_history=False,
):
    root = root.expanduser().resolve()
    if mode not in {"fulltext", "semantic", "hybrid"}:
        raise ValueError("Неизвестный режим поиска")
    if not query.strip() or len(query) > 4000:
        raise ValueError("Запрос должен содержать 1..4000 символов")
    if not 1 <= limit <= 50 or not 0 <= hops <= 3:
        raise ValueError("limit должен быть 1..50, hops — 0..3")
    if scope and (
        PurePosixPath(scope).is_absolute() or ".." in PurePosixPath(scope).parts
    ):
        raise ValueError("scope должен быть относительным путём внутри корпуса")
    scope = scope.rstrip("/")
    db = store.connect(root)
    try:
        cfg = fresh(root, db)
        docs = {
            r["path"]: {**json.loads(r["data"]), "sha256": r["hash"]}
            for r in db.execute("SELECT * FROM documents")
        }

        def allowed(path):
            return (not scope or path == scope or path.startswith(scope + "/")) and (
                include_history or docs[path]["status"] != "historical"
            )

        chunks = {}
        vectors = {}
        for row in db.execute("SELECT * FROM chunks ORDER BY id"):
            if allowed(row["path"]):
                chunks[row["id"]] = json.loads(row["data"])
                vectors[row["id"]] = (
                    json.loads(row["vector"]) if row["vector"] else None
                )
        rankings = []
        if mode in {"fulltext", "hybrid"}:
            rankings.append([c for c in lexical(db, query) if c in chunks])
        if mode in {"semantic", "hybrid"}:
            if not store.get(db, "model"):
                raise ValueError(
                    "Нет semantic embedding index; выполните index без --lexical-only"
                )
            model = make_embedder(cfg)
            if model.identity != store.get(db, "model"):
                raise ValueError("Embedding model изменилась; выполните index")
            rankings.append(semantic(chunks, vectors, model, query))
        scores = defaultdict(float)
        for ranking in rankings:
            for rank, cid in enumerate(ranking, 1):
                scores[cid] += 1 / (60 + rank)
        seeds = sorted(scores, key=lambda cid: (-scores[cid], cid))
        paths = defaultdict(list)
        for cid, c in chunks.items():
            paths[c["path"]].append(cid)
        hits = []
        used = set()

        def append(cid, via):
            c = chunks[cid]
            doc = docs[c["path"]]
            used.add(cid)
            hits.append(
                {
                    **c,
                    "title": doc["title"],
                    "locator": doc["locator"],
                    "absolute_path": str(root / c["path"]),
                    "sha256": doc["sha256"],
                    "status": doc["status"],
                    "via": via,
                    "score": scores.get(cid, 0),
                    "reason": "graph" if via else mode,
                    "directories": list(PurePosixPath(c["path"]).parts[:-1]),
                }
            )

        # Сначала лучшая находка, затем не более двух связанных документов;
        # оставшийся бюджет — другие прямые попадания.
        for seed in seeds:
            if len(hits) >= limit:
                break
            if seed in used:
                continue
            append(seed, [])
            if hops:
                added = 0
                for path, via in related(db, chunks[seed]["path"], hops):
                    candidates = [cid for cid in paths.get(path, []) if cid not in used]
                    if candidates:
                        candidates = section_candidates(
                            path, via, candidates, chunks, docs[path]
                        )
                    if not candidates or any(h["path"] == path for h in hits):
                        continue
                    cid = min(
                        candidates,
                        key=lambda c: (-scores.get(c, 0), chunks[c]["start_line"]),
                    )
                    if len(hits) >= limit or added >= 2:
                        break
                    append(cid, via)
                    added += 1
        return {
            "root": str(root),
            "query": query,
            "mode": mode,
            "generation": store.get(db, "generation"),
            "hits": hits,
            "graph_hops": hops,
            "score_kind": "reciprocal_rank_not_confidence",
        }
    finally:
        db.close()
