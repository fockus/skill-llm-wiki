#!/usr/bin/env python3
"""Мерка поиска: доля вопросов, где нужный документ / фрагмент с ответом попал в top-k.

Запуск: .venv/bin/python scripts/eval_search.py --root WIKI --questions FILE.jsonl [--scope raw]
Строка файла: {"q": вопрос, "doc": подстрока пути документа, "answer": regex текста фрагмента}.
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from llm_wiki import search


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--questions", required=True)
    ap.add_argument("--scope", default="raw")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()
    rows = [
        json.loads(x)
        for x in Path(a.questions).read_text(encoding="utf-8").splitlines()
        if x.strip()
    ]
    report = {}
    for mode in ["fulltext", "semantic", "hybrid"]:
        doc_hit = ans_hit = 0
        mrr = 0.0
        started = time.time()
        for r in rows:
            hits = search.query(
                Path(a.root), r["q"], mode=mode, limit=a.k, hops=0, scope=a.scope
            )["hits"]
            docs = [r["doc"] in h["path"] for h in hits]
            answers = [
                d and bool(re.search(r["answer"], h["text"]))
                for d, h in zip(docs, hits)
            ]
            doc_hit += any(docs)
            ans_hit += any(answers)
            mrr += next((1 / i for i, ok in enumerate(answers, 1) if ok), 0.0)
            if a.verbose and mode == "hybrid" and not any(answers):
                print(
                    "MISS:",
                    r["q"],
                    "->",
                    [h["path"][-28:] for h in hits],
                    file=sys.stderr,
                )
        n = len(rows)
        report[mode] = {
            "doc@k": round(doc_hit / n, 3),
            "answer@k": round(ans_hit / n, 3),
            "mrr": round(mrr / n, 3),
            "sec_per_query": round((time.time() - started) / n, 2),
        }
    print(
        json.dumps(
            {"n": len(rows), "k": a.k, "scope": a.scope, **report},
            ensure_ascii=False,
            indent=1,
        )
    )


if __name__ == "__main__":
    main()
