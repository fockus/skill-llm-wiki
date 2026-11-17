"""Настоящие локальные форматы и ссылки; fixtures без офисных приложений."""

from pathlib import Path
import sys
from urllib.parse import quote
import zipfile

import pytest
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from llm_wiki import config, documents, graph, health, index, project, search


@pytest.fixture
def wiki_root(tmp_path):
    root = tmp_path / "llm-wiki"
    project.init(root, "Форматы")
    return root


def write_docx(path):
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="xml" ContentType="application/xml"/></Types>',
        )
        archive.writestr(
            "word/document.xml",
            '<w:document xmlns:w="http://schemas.openxmlformats.org/'
            'wordprocessingml/2006/main"><w:body>'
            "<w:p><w:r><w:t>Исследование облигаций</w:t></w:r></w:p>"
            "<w:p><w:r><w:t>Доходностьмаркер </w:t></w:r>"
            "<w:r><w:t>и риск погашения.</w:t></w:r></w:p>"
            "</w:body></w:document>",
        )


def write_pdf(path, text=True):
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    if text:
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
        )
        stream = DecodedStreamObject()
        stream.set_data(
            b"BT /F1 12 Tf 72 720 Td (Researchmarker market evidence) Tj ET"
        )
        page[NameObject("/Contents")] = stream
    with path.open("wb") as output:
        writer.write(output)


@pytest.mark.parametrize(
    ("suffix", "keyword", "expected"),
    [
        (".html", "Доходностьмаркер", "Доходностьмаркер и риск"),
        (".docx", "Доходностьмаркер", "Доходностьмаркер и риск погашения."),
        (".pdf", "Researchmarker", "Researchmarker market evidence"),
    ],
)
def test_non_markdown_formats_are_searchable_with_extraction_locators(
    wiki_root, suffix, keyword, expected
):
    relative = "raw/Рыночный обзор" + suffix
    path = wiki_root / relative
    if suffix == ".html":
        path.write_text(
            "<html><head><style>Hiddenstyle</style>"
            "<script>Hiddenscript</script></head><body>"
            "<h1>Исследование</h1><p>Доходностьмаркер и риск</p></body></html>",
            encoding="utf-8",
        )
    elif suffix == ".docx":
        write_docx(path)
    else:
        write_pdf(path)
    index.build(wiki_root, lexical_only=True)
    hit = search.query(wiki_root, keyword, mode="fulltext", hops=0)["hits"][0]
    assert hit["path"] == relative
    assert hit["locator"] == "extracted-line"
    read = health.read_document(wiki_root, relative, hit["start_line"], hit["end_line"])
    assert expected in read["text"]
    assert read["locator"] == "extracted-line"
    assert read["sha256"] == hit["sha256"]
    assert (
        search.query(wiki_root, "Hiddenscript Hiddenstyle", mode="fulltext")["hits"]
        == []
    )


def test_pdf_without_text_reports_ocr_requirement(wiki_root):
    path = wiki_root / "raw/Скан.pdf"
    write_pdf(path, text=False)
    with pytest.raises(ValueError, match="OCR"):
        documents.extract(path)


def test_markdown_fenced_examples_do_not_create_headings_or_links(wiki_root):
    relative = "wiki/Пример.md"
    (wiki_root / relative).write_text(
        "# Настоящий заголовок\n\n```md\n# Ложный заголовок\n[[Отсутствует]]\n```\n"
        "\n## Риск актива\nСодержательныймаркер\n",
        encoding="utf-8",
    )
    doc = documents.parse(wiki_root, relative, config.load(wiki_root))
    assert [heading["title"] for heading in doc["headings"]] == [
        "Настоящий заголовок",
        "Риск актива",
    ]
    assert doc["links"] == []
    index.build(wiki_root, lexical_only=True)
    hit = search.query(wiki_root, "Содержательныймаркер", mode="fulltext", hops=0)[
        "hits"
    ][0]
    assert hit["heading"] == ["Настоящий заголовок", "Риск актива"]
    assert hit["start_line"] <= 9 <= hit["end_line"]


def test_markdown_inline_code_examples_do_not_create_wikilinks(wiki_root):
    relative = "wiki/Инструкции.md"
    (wiki_root / relative).write_text(
        "# Инструкции\nСинтаксис примера: `[[Несуществующая страница]]`.\n",
        encoding="utf-8",
    )
    doc = documents.parse(wiki_root, relative, config.load(wiki_root))
    assert doc["links"] == []


def test_russian_filenames_anchors_and_nested_heading_graph_resolve(wiki_root):
    folder = wiki_root / "wiki/Рынки"
    folder.mkdir()
    target = "wiki/Рынки/Облигации РФ.md"
    (wiki_root / target).write_text(
        "# Облигации\n\n## Риск погашения\n"
        "Кредитныймаркер\n\n## Риск погашения\nДругое.\n",
        encoding="utf-8",
    )
    (wiki_root / "wiki/Ссылки.md").write_text(
        "# Ссылки\n[Прямая](Рынки/Облигации%20РФ.md#риск-погашения)\n"
        f"[Закодированная]({quote('Рынки/Облигации РФ.md#риск-погашения-1', safe='/#')})\n",
        encoding="utf-8",
    )
    index.build(wiki_root, lexical_only=True)
    data = graph.inspect(wiki_root, "file:wiki/Ссылки.md", hops=1)
    destinations = {edge["dst"] for edge in data["edges"] if edge["kind"] == "links"}
    assert destinations == {
        "section:" + target + "#риск-погашения",
        "section:" + target + "#риск-погашения-1",
    }
    assert not any(
        issue["kind"] in {"broken_link", "broken_anchor"}
        for issue in health.lint(wiki_root)["issues"]
    )
    hit = search.query(wiki_root, "Кредитныймаркер", mode="fulltext", hops=0)["hits"][0]
    assert hit["path"] == target
    assert hit["section"] == "риск-погашения"


def test_convert_pdf_gets_markdown_sibling_and_markdown_replaces_pdf_in_index(tmp_path):
    from llm_wiki import config, convert, documents, project

    project.init(tmp_path, "T")
    pdf = tmp_path / "raw/imports/paper.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    result = convert.convert(
        tmp_path, to_markdown=lambda p: "# Paper\n\n## Method\n\nBody text.\n"
    )
    assert result["converted"] == ["raw/imports/paper.pdf"]
    inventory = documents.inventory(tmp_path, config.load(tmp_path))
    assert (
        "raw/imports/paper.md" in inventory and "raw/imports/paper.pdf" not in inventory
    )
    parsed = documents.parse(tmp_path, "raw/imports/paper.md", config.load(tmp_path))
    assert [h["title"] for h in parsed["headings"]] == ["Paper", "Method"]
    again = convert.convert(tmp_path, to_markdown=lambda p: "changed")
    assert again["skipped"] == ["raw/imports/paper.pdf"] and again["converted"] == []


def test_chunks_long_paragraph_split_at_sentence_end_and_table_kept_whole():
    from llm_wiki import documents

    sentence = "Alpha beta gamma delta epsilon zeta eta theta. "
    table = "\n".join(
        ["| a | b |", "|---|---|"] + [f"| row{i} | value{i} |" for i in range(12)]
    )
    text = "# T\n\n" + sentence * 8 + "\n\n" + table + "\n"
    doc = {
        "path": "x.md",
        "text": text,
        "offset": 0,
        "headings": [{"level": 1, "title": "T", "slug": "t", "line": 1}],
    }
    result = documents.chunks(doc, 120)
    prose = [c["text"] for c in result if "Alpha" in c["text"]]
    assert len(prose) > 1 and all(t.rstrip().endswith(".") for t in prose)
    tables = [c["text"] for c in result if "| row0 |" in c["text"]]
    assert len(tables) == 1 and "| row11 |" in tables[0]


def test_fulltext_matches_english_word_forms(tmp_path):
    from llm_wiki import index, project, search

    project.init(tmp_path, "T")
    (tmp_path / "wiki/page.md").write_text(
        "---\nsources: [index.md]\n---\n# Page\n\nThe agent collects diamonds in caves.\n",
        encoding="utf-8",
    )
    index.build(tmp_path, lexical_only=True)
    hits = search.query(tmp_path, "collecting diamond", mode="fulltext", hops=0)["hits"]
    assert hits and hits[0]["path"] == "wiki/page.md"
