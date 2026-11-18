"""Локальная ONNX модель с проверкой пространства и без скрытого fallback."""

import hashlib
import importlib.metadata
import json
from pathlib import Path

import numpy as np

MINILM = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
MINILM_REPO = "Qdrant/paraphrase-multilingual-MiniLM-L12-v2-onnx-Q"
MINILM_REVISION = "faf4aa4225822f3bc6376869cb1164e8e3feedd0"
MINILM_FILES = [
    "model_optimized.onnx",
    "tokenizer.json",
    "config.json",
    "special_tokens_map.json",
    "tokenizer_config.json",
]


def minilm_dir(cfg):
    return (
        Path(cfg["cache_dir"]).expanduser()
        / "paraphrase-multilingual-MiniLM-L12-v2-onnx-Q"
    )


class LocalEmbedder:
    def __init__(self, cfg):
        from fastembed import TextEmbedding

        if cfg["model"] != MINILM:
            raise ValueError(
                "Эта модель требует отдельного проверенного embedding adapter"
            )
        folder = minilm_dir(cfg)
        missing = [f for f in MINILM_FILES if not (folder / f).is_file()]
        if missing:
            raise ValueError(
                "Локальная embedding model недоступна; выполните scripts/prepare_model.py: "
                f"нет {missing} в {folder}"
            )
        # specific_model_path отключает собственную загрузку fastembed (всегда последняя
        # ревизия); файлы скачивает prepare_model.py по MINILM_REVISION.
        self.engine = TextEmbedding(
            model_name=cfg["model"],
            specific_model_path=str(folder),
            local_files_only=True,
            threads=cfg.get("threads", 2),
        )
        hasher = hashlib.sha256()
        for path in sorted(folder.rglob("*")):
            rel = path.relative_to(folder)
            # .cache/ — служебные метаданные huggingface_hub, не часть модели.
            if path.is_file() and rel.parts[0] != ".cache":
                hasher.update(str(rel).encode())
                with path.open("rb") as stream:
                    for block in iter(lambda: stream.read(1_048_576), b""):
                        hasher.update(block)
        self.identity = json.dumps(
            {
                "model": cfg["model"],
                "artifact_sha256": hasher.hexdigest(),
                "fastembed": importlib.metadata.version("fastembed"),
                "adapter": 1,
            },
            sort_keys=True,
        )
        self.tokenizer = self.engine.model.tokenizer
        self.max_tokens = int((self.tokenizer.truncation or {}).get("max_length", 512))

    def _parts(self, text):
        # Разбиение исключает молчаливое обрезание длинного запроса tokenizer.
        encoded = self.tokenizer.encode(text)
        if not encoded.overflowing:
            return [text]
        middle = len(text) // 2
        if middle == 0:
            raise ValueError("Не удалось разделить текст для embedding")
        return self._parts(text[:middle]) + self._parts(text[middle:])

    def documents(self, texts):
        groups = [self._parts(text) for text in texts]
        flat = [text for group in groups for text in group]
        vectors = list(self.engine.embed(flat, batch_size=32))
        result = []
        offset = 0
        for group in groups:
            value = np.mean(vectors[offset : offset + len(group)], axis=0)
            offset += len(group)
            norm = float(np.linalg.norm(value))
            if not np.isfinite(value).all() or norm <= 0:
                raise ValueError("Некорректный embedding vector")
            result.append((value / norm).tolist())
        return result

    def question(self, text):
        return self.documents([text])[0]


PPLX = "perplexity-ai/pplx-embed-v1-0.6b"
PPLX_REVISION = "2c4d510dd4a732063c31a0f70193e35067b51fd8"
PPLX_FILES = [
    "onnx/model_q4.onnx",
    "onnx/model_q4.onnx_data",
    "tokenizer.json",
    "config.json",
]


def pplx_dir(cfg):
    return Path(cfg["cache_dir"]).expanduser() / "pplx-embed-v1-0.6b"


class PplxEmbedder:
    """pplx-embed-v1-0.6b (MIT): ONNX q4 через onnxruntime, tokenizer.json без remote code."""

    MAX_TOKENS = 2048  # модель держит 32K; предел бережёт память и время на CPU
    PAD = 151643  # <|endoftext|>, pad по tokenizer_config модели

    def __init__(self, cfg):
        import onnxruntime as ort
        from tokenizers import Tokenizer

        folder = pplx_dir(cfg)
        missing = [f for f in PPLX_FILES if not (folder / f).is_file()]
        if missing:
            raise ValueError(
                "Локальная embedding model недоступна; выполните scripts/prepare_model.py "
                f"--model {PPLX}: нет {missing}"
            )
        options = ort.SessionOptions()
        options.intra_op_num_threads = cfg.get("threads", 2)
        self.session = ort.InferenceSession(
            str(folder / "onnx/model_q4.onnx"),
            options,
            providers=["CPUExecutionProvider"],
        )
        self.tokenizer = Tokenizer.from_file(str(folder / "tokenizer.json"))
        self.tokenizer.enable_truncation(max_length=self.MAX_TOKENS)
        # ponytail: в identity входят имена и размеры всех файлов и полный hash малых;
        # 380 МБ весов не хэшируются при каждом поиске. Полный hash — если веса
        # начнут подменяться при том же размере.
        hasher = hashlib.sha256()
        for name in PPLX_FILES:
            path = folder / name
            hasher.update(f"{name}:{path.stat().st_size}".encode())
            if path.stat().st_size < 20_000_000:
                hasher.update(path.read_bytes())
        self.identity = json.dumps(
            {
                "model": PPLX,
                "revision": PPLX_REVISION,
                "artifact_sha256": hasher.hexdigest(),
                "onnxruntime": importlib.metadata.version("onnxruntime"),
                "adapter": 1,
            },
            sort_keys=True,
        )

    def documents(self, texts, batch_size=8):
        encoded = [self.tokenizer.encode(text).ids or [self.PAD] for text in texts]
        order = sorted(range(len(texts)), key=lambda i: len(encoded[i]))
        result = [None] * len(texts)
        for start in range(0, len(order), batch_size):
            batch = order[start : start + batch_size]
            width = max(len(encoded[i]) for i in batch)
            ids = np.full((len(batch), width), self.PAD, dtype=np.int64)
            mask = np.zeros((len(batch), width), dtype=np.int64)
            for row, i in enumerate(batch):
                ids[row, : len(encoded[i])] = encoded[i]
                mask[row, : len(encoded[i])] = 1
            pooled = self.session.run(
                ["pooler_output"], {"input_ids": ids, "attention_mask": mask}
            )[0].astype(float)
            for row, i in enumerate(batch):
                norm = float(np.linalg.norm(pooled[row]))
                if not np.isfinite(pooled[row]).all() or norm <= 0:
                    raise ValueError("Некорректный embedding vector")
                result[i] = (pooled[row] / norm).tolist()
        return result

    def question(self, text):
        return self.documents([text])[0]


def make_embedder(cfg):
    return PplxEmbedder(cfg) if cfg["model"] == PPLX else LocalEmbedder(cfg)
