"""PDF → Markdown-копия рядом с исходником. Исходный PDF не меняется."""

import importlib.metadata
import json
from pathlib import Path

from . import config, documents


def pdf_to_markdown(path: Path) -> str:
    """Docling восстанавливает заголовки, абзацы и таблицы; OCR выключен."""
    try:
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption
    except ImportError as exc:
        raise ValueError(
            "Docling не установлен: uv pip install --python .venv/bin/python docling"
        ) from exc
    options = PdfPipelineOptions()
    options.do_ocr = False
    converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
    )
    document = converter.convert(str(path)).document
    pages = sorted(document.pages) or [None]
    parts = []
    for number in pages:
        body = document.export_to_markdown(page_no=number).strip()
        if body:
            parts.append((f"[page:{number}]\n\n" if number else "") + body)
    if not parts:
        raise ValueError(f"PDF требует OCR: {path.name}")
    return "\n\n".join(parts) + "\n"


def convert(root: Path, force=False, to_markdown=pdf_to_markdown) -> dict:
    """Создаёт .md рядом с каждым PDF корпуса; готовые копии с тем же hash пропускает."""
    root = Path(root).expanduser().resolve()
    cfg = config.load(root)
    converted, skipped = [], []
    for prefix in cfg["include"]:
        base = root / prefix
        for pdf in sorted(base.rglob("*.pdf")) if base.is_dir() else []:
            rel = pdf.relative_to(root).as_posix()
            if not pdf.is_file() or not documents.permitted(root, rel, cfg):
                continue
            target = pdf.with_suffix(".md")
            sha = documents.digest(pdf.read_bytes())
            marker = f"sha256: {sha}\n"
            if (
                not force
                and target.is_file()
                and marker in target.read_text(encoding="utf-8")[:600]
            ):
                skipped.append(rel)
                continue
            if (
                target.exists()
                and "type: extracted\n" not in target.read_text(encoding="utf-8")[:200]
            ):
                raise ValueError(f"Рядом с PDF лежит чужой Markdown: {target.name}")
            header = (
                "---\ntype: extracted\n"
                f"derived_from: {json.dumps(pdf.name, ensure_ascii=False)}\n"
                f"{marker}"
                f"converter: docling {importlib.metadata.version('docling') if to_markdown is pdf_to_markdown else 'custom'}\n"
                "---\n\n"
            )
            target.write_text(header + to_markdown(pdf), encoding="utf-8")
            converted.append(rel)
    return {"ok": True, "root": str(root), "converted": converted, "skipped": skipped}
