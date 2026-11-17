"""Поведенческие проверки хранения и retrieval; fake только на границе модели."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from llm_wiki import index, search, graph, health


@pytest.fixture
def corpus(tmp_path):
    (tmp_path / "wiki").mkdir()
    (tmp_path / "raw").mkdir()
    (tmp_path / ".wiki.json").write_text(json.dumps({"schema_version": 1}))
    (tmp_path / "wiki/storage.md").write_text(
        "# Хранилище\n\n## Восстановление\nПерезапуск после аварии сохраняет данные.\n\n[Исходник](../raw/manual.txt)\n"
    )
    (tmp_path / "raw/manual.txt").write_text(
        "Контрольная точка сохраняется на постоянном диске.\n"
    )
    (tmp_path / "wiki/cooking.md").write_text(
        "# Кулинария\nРецепт приготовления супа.\n"
    )
    return tmp_path


class Model:
    identity = "test-boundary-model-v1"
    calls = 0

    def documents(self, texts):
        self.calls += len(texts)
        return [[0.0, 1.0] if "супа" in t else [1.0, 0.0] for t in texts]

    def question(self, text):
        return [1.0, 0.0]


def test_fulltext_finds_cited_lines(corpus):
    index.build(corpus, lexical_only=True)
    result = search.query(corpus, "аварии", mode="fulltext", hops=0)
    assert result["hits"][0]["path"] == "wiki/storage.md"
    assert result["hits"][0]["start_line"] <= 4 <= result["hits"][0]["end_line"]
    assert result["hits"][0]["heading"] == ["Хранилище", "Восстановление"]


def test_graph_adds_linked_source_not_unrelated_sibling(corpus):
    index.build(corpus, lexical_only=True)
    result = search.query(corpus, "аварии", mode="fulltext", hops=1)
    related = [h for h in result["hits"] if h["path"] == "raw/manual.txt"]
    assert related and related[0]["via"][0]["kind"] == "links"
    assert all(h["path"] != "wiki/cooking.md" for h in result["hits"])
    data = graph.inspect(corpus, node="file:wiki/storage.md", hops=2)
    assert any(n["kind"] == "section" for n in data["nodes"])
    assert any(e["kind"] == "contains" for e in data["edges"])


def test_semantic_requires_real_index_not_silent_fallback(corpus):
    index.build(corpus, lexical_only=True)
    with pytest.raises(ValueError, match="semantic|embedding|вектор"):
        search.query(corpus, "аварии", mode="semantic")


def test_changed_and_deleted_sources_invalidate_then_disappear(corpus):
    index.build(corpus, lexical_only=True)
    (corpus / "wiki/storage.md").write_text("# Другое\nНовый материал.")
    with pytest.raises(ValueError, match="stale|устарел"):
        search.query(corpus, "аварии", mode="fulltext")
    (corpus / "raw/manual.txt").unlink()
    index.build(corpus, lexical_only=True)
    assert search.query(corpus, "аварии", mode="fulltext")["hits"] == []
    assert not any(
        n.get("path") == "raw/manual.txt" for n in graph.inspect(corpus)["nodes"]
    )


def test_scope_and_history_apply_to_graph_expansion(corpus):
    (corpus / "raw/manual.txt").unlink()
    (corpus / "raw/manual.md").write_text(
        "---\nstatus: historical\n---\n# Старый источник\nАрхив."
    )
    p = corpus / "wiki/storage.md"
    p.write_text(p.read_text().replace("manual.txt", "manual.md"))
    index.build(corpus, lexical_only=True)
    assert all(
        h["path"] != "raw/manual.md"
        for h in search.query(corpus, "аварии", mode="fulltext")["hits"]
    )
    assert any(
        h["path"] == "raw/manual.md"
        for h in search.query(corpus, "аварии", mode="fulltext", include_history=True)[
            "hits"
        ]
    )
    assert all(
        h["path"].startswith("wiki/")
        for h in search.query(
            corpus, "аварии", mode="fulltext", scope="wiki", include_history=True
        )["hits"]
    )


def test_read_blocks_escape_and_external_symlink(corpus, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside") / "secret.txt"
    outside.write_text("private")
    (corpus / "wiki/leak.txt").symlink_to(outside)
    index.build(corpus, lexical_only=True)
    assert search.query(corpus, "private", mode="fulltext")["hits"] == []
    with pytest.raises(ValueError):
        health.read_document(corpus, "wiki/leak.txt")
    with pytest.raises(ValueError):
        health.read_document(corpus, "../secret.txt")


def test_unchanged_update_reuses_vectors_and_model_change_rebuilds(corpus, monkeypatch):
    model = Model()
    monkeypatch.setattr(index, "make_embedder", lambda cfg: model)
    monkeypatch.setattr(search, "make_embedder", lambda cfg: model)
    index.build(corpus)
    before = model.calls
    index.build(corpus)
    assert model.calls == before
    result = search.query(
        corpus, "как пережить отключение электричества", mode="semantic", hops=0
    )
    assert result["hits"][0]["path"] != "wiki/cooking.md"
    model.identity = "changed-model"
    with pytest.raises(ValueError, match="model|модел"):
        search.query(corpus, "вопрос", mode="semantic")
    index.build(corpus)
    assert model.calls > before


def test_failure_keeps_previous_index_generation(corpus, monkeypatch):
    index.build(corpus, lexical_only=True)
    previous = health.status(corpus)["generation"]

    def broken(cfg):
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(index, "make_embedder", broken)
    with pytest.raises(RuntimeError):
        index.build(corpus)
    assert health.status(corpus)["generation"] == previous
    assert search.query(corpus, "аварии", mode="fulltext")["hits"]


def test_literal_fulltext_query_cannot_inject_fts_syntax(corpus):
    index.build(corpus, lexical_only=True)
    result = search.query(corpus, '" OR NEAR(foo) *', mode="fulltext")
    assert isinstance(result["hits"], list)


def test_lint_reports_broken_and_ambiguous_links(corpus):
    (corpus / "wiki/a").mkdir()
    (corpus / "wiki/b").mkdir()
    for folder in ["a", "b"]:
        (corpus / f"wiki/{folder}/same.md").write_text("# Same")
    (corpus / "wiki/links.md").write_text("# Links\n[[same]]\n[missing](none.md)")
    index.build(corpus, lexical_only=True)
    report = health.lint(corpus)
    assert any(i["kind"] == "ambiguous_link" for i in report["issues"])
    assert any(i["kind"] == "broken_link" for i in report["issues"])


def test_parent_heading_change_reembeds_child_context(corpus, monkeypatch):
    model = Model()
    monkeypatch.setattr(index, "make_embedder", lambda cfg: model)
    p = corpus / "wiki/storage.md"
    p.write_text(
        p.read_text().replace(
            "# Хранилище\n", "# Хранилище\nВводное описание архитектуры хранения.\n"
        )
    )
    index.build(corpus)
    before = model.calls
    p = corpus / "wiki/storage.md"
    p.write_text(p.read_text().replace("# Хранилище", "# Архивирование"))
    index.build(corpus)
    assert model.calls - before >= 2


def test_long_line_citations_have_valid_order(corpus):
    (corpus / "wiki/long.md").write_text("# Long\n" + "Ж" * 1201 + "\nСледующая строка")
    index.build(corpus, lexical_only=True)
    from llm_wiki import store

    db = store.connect(corpus)
    try:
        for row in db.execute("SELECT data FROM chunks"):
            item = json.loads(row[0])
            assert item["end_line"] >= item["start_line"]
    finally:
        db.close()


def test_wikilink_in_inline_code_is_not_a_reference(corpus):
    (corpus / "wiki/example.md").write_text(
        "# Example\nСинтаксис: `[[not-a-reference]]`."
    )
    index.build(corpus, lexical_only=True)
    assert not any(
        i.get("target") == "not-a-reference" for i in health.lint(corpus)["issues"]
    )


def test_excluded_and_external_links_are_not_broken(corpus):
    config_path = corpus / ".wiki.json"
    config_path.write_text(json.dumps({"exclude": ["raw/manual.txt"]}))
    (corpus / "wiki/navigation.md").write_text(
        "# Nav\n[Root](../../README.md)\n[Folder](../raw/)"
    )
    index.build(corpus, lexical_only=True)
    issues = health.lint(corpus)["issues"]
    assert not any(i["kind"] == "broken_link" for i in issues)
    assert any(i["kind"] == "outside_scope" for i in issues)
    assert any(i["kind"] == "excluded_link" for i in issues)


def test_graph_anchor_retrieves_target_section(corpus):
    (corpus / "wiki/storage.md").write_text(
        "# Начало\nаварии [подробнее](target.md#нужный-раздел)"
    )
    (corpus / "wiki/target.md").write_text(
        "# Цель\n## Лишний раздел\nНерелевантный текст.\n## Нужный раздел\nПравильное доказательство.\n"
    )
    index.build(corpus, lexical_only=True)
    hits = search.query(corpus, "аварии", mode="fulltext", hops=1)["hits"]
    related = [h for h in hits if h["path"] == "wiki/target.md"]
    assert related and "Правильное доказательство" in related[0]["text"]


def test_heading_only_chunks_do_not_displace_evidence(corpus):
    (corpus / "wiki/chapters.md").write_text(
        "# аварии\n## аварии\nТранзакции защищают данные после сбоя.\n"
    )
    index.build(corpus, lexical_only=True)
    hits = search.query(
        corpus, "аварии", mode="fulltext", scope="wiki/chapters.md", hops=0
    )["hits"]
    assert hits and all("Транзакции" in h["text"] for h in hits)


def test_graph_prefers_provenance_before_navigation_backlinks(corpus):
    p = corpus / "wiki/storage.md"
    p.write_text("---\nsources: [../raw/manual.txt]\n---\n" + p.read_text())
    (corpus / "wiki/aaa-index.md").write_text("# Navigation\n[Storage](storage.md)")
    index.build(corpus, lexical_only=True)
    hits = search.query(corpus, "аварии", mode="fulltext", hops=1, limit=2)["hits"]
    assert hits[1]["path"] == "raw/manual.txt"
    assert hits[1]["via"][0]["kind"] == "source"


def test_docx_headings_preserve_hierarchy_without_empty_hits(corpus):
    from zipfile import ZipFile

    text = '<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:pPr><w:pStyle w:val="Title"/></w:pPr><w:r><w:t>Система</w:t></w:r></w:p><w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Защита</w:t></w:r></w:p><w:p><w:r><w:t>Шифрование диска обязательно.</w:t></w:r></w:p></w:body></w:document>'
    with ZipFile(corpus / "raw/policy.docx", "w") as z:
        z.writestr("word/document.xml", text)
    index.build(corpus, lexical_only=True)
    hits = search.query(
        corpus, "Защита", mode="fulltext", scope="raw/policy.docx", hops=0
    )["hits"]
    assert len(hits) == 1 and hits[0]["heading"] == ["Система", "Защита"]
    assert "Шифрование" in hits[0]["text"]
