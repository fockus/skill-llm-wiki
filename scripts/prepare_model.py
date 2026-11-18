#!/usr/bin/env python3
"""Явная подготовка model cache; документы проекта не читаются."""

import argparse
import json

from llm_wiki.config import DEFAULTS
from llm_wiki.embeddings import (
    MINILM,
    MINILM_FILES,
    MINILM_REPO,
    MINILM_REVISION,
    PPLX,
    PPLX_FILES,
    PPLX_REVISION,
    make_embedder,
    minilm_dir,
    pplx_dir,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--offline", action="store_true", help="Только проверить локальный cache"
    )
    parser.add_argument("--cache-dir", default=DEFAULTS["cache_dir"])
    parser.add_argument("--model", default=DEFAULTS["model"])
    args = parser.parse_args()
    cfg = {
        **DEFAULTS,
        "offline": args.offline,
        "cache_dir": args.cache_dir,
        "model": args.model,
    }
    sources = {
        PPLX: (PPLX, PPLX_REVISION, PPLX_FILES, pplx_dir),
        MINILM: (MINILM_REPO, MINILM_REVISION, MINILM_FILES, minilm_dir),
    }
    if args.model in sources and not args.offline:
        from huggingface_hub import hf_hub_download

        repo, revision, files, folder = sources[args.model]
        # Обычные файлы в local_dir по закреплённой ревизии: onnxruntime не читает
        # внешние веса через symlink cache, а fastembed сам берёт последнюю ревизию.
        for name in files:
            hf_hub_download(repo, name, revision=revision, local_dir=folder(cfg))
    model = make_embedder(cfg)
    print(
        json.dumps(
            {
                "model": json.loads(model.identity),
                "dimension": len(model.question("проверка")),
                "offline": args.offline,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
