"""Приёмка настоящей локальной модели: без сети и без fake embeddings."""

import json
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from llm_wiki import index, search
from llm_wiki.config import DEFAULTS
from llm_wiki.embeddings import make_embedder


def test_real_model_finds_russian_paraphrase_offline(tmp_path, monkeypatch):
    def no_network(*args, **kwargs):
        raise AssertionError("Offline test запрещает сетевое соединение")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    (tmp_path / "wiki").mkdir()
    (tmp_path / ".wiki.json").write_text(json.dumps({"schema_version": 1}))
    (tmp_path / "wiki/storage.md").write_text(
        "# Надёжность\nЖурнал транзакций и резервные копии обеспечивают восстановление записей после аварийного выключения питания."
    )
    (tmp_path / "wiki/food.md").write_text(
        "# Кухня\nДля выпечки пирога нужны мука, сахар, молоко и яйца."
    )
    (tmp_path / "wiki/travel.md").write_text(
        "# Отдых\nОтель расположен у морского побережья рядом с пляжем."
    )
    result = index.build(tmp_path)
    assert result["dimension"] == 384
    question = "Как пережить внезапное обесточивание компьютера?"
    assert search.query(tmp_path, question, mode="fulltext", hops=0)["hits"] == []
    hits = search.query(tmp_path, question, mode="semantic", hops=0)["hits"]
    assert hits[0]["path"] == "wiki/storage.md"
    assert hits[0]["locator"] == "line"


def test_local_model_splits_long_text_without_losing_tail():
    model = make_embedder(DEFAULTS)
    text = "Финансовое исследование инвестиционных инструментов. " * 200 + "КОНЕЦ"
    pieces = model._parts(text)
    assert len(pieces) > 1
    assert "".join(pieces) == text
    vector = model.question(text)
    assert len(vector) == 384


def test_pplx_embedder_missing_files_fail_with_prepare_hint(tmp_path):
    import pytest
    from llm_wiki import embeddings

    with pytest.raises(ValueError, match="prepare_model.py"):
        embeddings.make_embedder({"model": embeddings.PPLX, "cache_dir": str(tmp_path)})


def test_pplx_embedder_russian_question_closer_to_matching_english_text():
    import numpy as np
    import pytest
    from llm_wiki import embeddings

    cfg = {"model": embeddings.PPLX, "cache_dir": "~/.cache/fastembed", "threads": 2}
    if not (embeddings.pplx_dir(cfg) / embeddings.PPLX_FILES[0]).is_file():
        pytest.skip("pplx-embed не скачан")
    model = embeddings.make_embedder(cfg)
    q = np.array(model.question("сколько шагов среды нужно до первого алмаза"))
    good, bad = model.documents(
        [
            "The median number of environment steps until the first diamond is 74M.",
            "A recipe for beetroot soup.",
        ]
    )
    assert len(q) == 1024 and q @ np.array(good) > q @ np.array(bad) + 0.2
