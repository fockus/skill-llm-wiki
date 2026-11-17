"""Проверяемый граф containment, ссылок и provenance; без вымышленных relations."""

import posixpath
from collections import defaultdict
from urllib.parse import unquote, urlsplit
from pathlib import PurePosixPath

from . import store


def materialize(documents, all_chunks, root=None, cfg=None):
    nodes = {}
    edges = set()
    issues = []
    aliases = defaultdict(list)

    def node(ident, kind, path, label, line=0):
        nodes[ident] = (ident, kind, path, label, line)

    def edge(a, b, kind, path, line=0):
        edges.add((a, b, kind, path, line))

    node("dir:.", "directory", ".", "Corpus")
    for doc in documents.values():
        rel = doc["path"]
        p = PurePosixPath(rel)
        parent = "dir:."
        for ancestor in reversed(p.parents):
            if str(ancestor) == ".":
                continue
            ident = "dir:" + str(ancestor)
            node(ident, "directory", str(ancestor), ancestor.name)
            edge(parent, ident, "contains", rel)
            parent = ident
        fid = "file:" + rel
        node(fid, "file", rel, doc["title"])
        edge(parent, fid, "contains", rel)
        for alias in {p.stem, doc["title"], doc["source_id"]}:
            if alias:
                aliases[alias].append(fid)
        stack = []
        for h in doc["headings"]:
            sid = "section:" + rel + "#" + h["slug"]
            node(sid, "section", rel, h["title"], h["line"])
            while stack and stack[-1][0] >= h["level"]:
                stack.pop()
            edge(stack[-1][1] if stack else fid, sid, "contains", rel, h["line"])
            stack.append((h["level"], sid))
    for chunk in all_chunks:
        cid = "chunk:" + chunk["id"]
        node(cid, "chunk", chunk["path"], chunk["text"][:80], chunk["start_line"])
        parent = (
            "section:" + chunk["path"] + "#" + chunk["section"]
            if chunk["section"]
            else "file:" + chunk["path"]
        )
        edge(parent, cid, "contains", chunk["path"], chunk["start_line"])
    for doc in documents.values():
        for link in doc["links"]:
            target = link["target"]
            url = urlsplit(target)
            if url.scheme or url.netloc:
                continue
            rel = (
                posixpath.normpath(
                    posixpath.join(posixpath.dirname(doc["path"]), unquote(url.path))
                )
                if url.path
                else doc["path"]
            )
            candidates = []
            if rel in documents:
                candidates = ["file:" + rel]
            elif (
                rel.endswith((".html", ".htm", ".pdf"))
                and str(PurePosixPath(rel).with_suffix(".md")) in documents
            ):
                candidates = ["file:" + str(PurePosixPath(rel).with_suffix(".md"))]
            elif link["kind"] in {"source", "wikilink"}:
                if rel + ".md" in documents:
                    candidates = ["file:" + rel + ".md"]
                else:
                    candidates = aliases.get(unquote(url.path), [])
            if not candidates and root is not None:
                from .documents import permitted

                issue = {
                    "path": doc["path"],
                    "line": link["line"],
                    "target": target,
                    "severity": "info",
                }
                if rel == ".." or rel.startswith("../") or rel.startswith("/"):
                    issues.append({**issue, "kind": "outside_scope"})
                    continue
                if (root / rel).is_dir():
                    did = "dir:" + rel
                    if did in nodes:
                        edge(
                            "file:" + doc["path"],
                            did,
                            "links",
                            doc["path"],
                            link["line"],
                        )
                    else:
                        issues.append({**issue, "kind": "outside_scope"})
                    continue
                if (root / rel).exists() and not permitted(root, rel, cfg):
                    issues.append({**issue, "kind": "excluded_link"})
                    continue
            if len(candidates) != 1:
                issues.append(
                    {
                        "kind": "ambiguous_link" if candidates else "broken_link",
                        "path": doc["path"],
                        "line": link["line"],
                        "target": target,
                    }
                )
                continue
            dst = candidates[0]
            if url.fragment:
                sid = "section:" + dst[5:] + "#" + unquote(url.fragment)
                if sid in nodes:
                    dst = sid
                else:
                    issues.append(
                        {
                            "kind": "broken_anchor",
                            "path": doc["path"],
                            "line": link["line"],
                            "target": target,
                        }
                    )
                    continue
            edge(
                "file:" + doc["path"],
                dst,
                "source" if link["kind"] == "source" else "links",
                doc["path"],
                link["line"],
            )
    return list(nodes.values()), sorted(edges), issues


def inspect(root, node=None, hops=1):
    from .health import fresh

    if not 0 <= hops <= 3:
        raise ValueError("hops должен быть 0..3")
    db = store.connect(root)
    try:
        fresh(root, db)
        nodes = [dict(r) for r in db.execute("SELECT * FROM nodes ORDER BY id")]
        edges = [dict(r) for r in db.execute("SELECT * FROM edges ORDER BY src,dst")]
        if node:
            if node not in {n["id"] for n in nodes}:
                raise ValueError("Узел не найден: " + node)
            selected = {node}
            frontier = {node}
            for _ in range(hops):
                nxt = {
                    e["dst"] if e["src"] in frontier else e["src"]
                    for e in edges
                    if e["src"] in frontier or e["dst"] in frontier
                }
                nxt -= selected
                selected |= nxt
                frontier = nxt
                if len(selected) > 2000:
                    raise ValueError("Graph budget превышен; уменьшите hops")
            nodes = [n for n in nodes if n["id"] in selected]
            edges = [e for e in edges if e["src"] in selected and e["dst"] in selected]
        return {
            "nodes": nodes,
            "edges": edges,
            "generation": store.get(db, "generation"),
            "root": str(root),
        }
    finally:
        db.close()
