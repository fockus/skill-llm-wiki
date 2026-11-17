#!/usr/bin/env python3
"""Явная подготовка model cache; документы проекта не читаются."""

import argparse
import json
from llm_wiki.config import DEFAULTS
from llm_wiki.embeddings import PPLX, PPLX_FILES, PPLX_REVISION, make_embedder, pplx_dir


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
    if args.model == PPLX and not args.offline:
        from huggingface_hub import hf_hub_download

        # Обычные файлы в local_dir: onnxruntime не читает внешние веса через symlink cache.
        for name in PPLX_FILES:
            hf_hub_download(PPLX, name, revision=PPLX_REVISION, local_dir=pplx_dir(cfg))
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
