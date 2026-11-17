"""Сканирование разрешённого корпуса и извлечение текста без исполнения источников."""

import fnmatch
import hashlib
import re
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree

import yaml
from markdown_it import MarkdownIt

TEXT = {
    ".md",
    ".txt",
    ".rst",
    ".py",
    ".go",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".csv",
    ".sql",
}
FORMATS = TEXT | {".html", ".htm", ".docx", ".pdf"}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def permitted(root, relative, cfg):
    path = Path(relative)
    if (
        path.is_absolute()
        or ".." in path.parts
        or any(p.startswith(".") for p in path.parts)
    ):
        return False
    if any(p in {"node_modules", "__pycache__", ".venv"} for p in path.parts):
        return False
    if any(
        (root / Path(*path.parts[:i])).is_symlink()
        for i in range(1, len(path.parts) + 1)
    ):
        return False
    rel = path.as_posix()
    if not any(rel == p or rel.startswith(p.rstrip("/") + "/") for p in cfg["include"]):
        return False
    return not any(
        rel == p or rel.startswith(p.rstrip("/") + "/") or fnmatch.fnmatch(rel, p)
        for p in cfg["exclude"]
    )


def inventory(root, cfg):
    result = {}
    for prefix in cfg["include"]:
        base = root / prefix
        if not base.exists():
            continue
        candidates = [base] if base.is_file() else base.rglob("*")
        for path in candidates:
            rel = path.relative_to(root).as_posix()
            if not path.is_file() or not permitted(root, rel, cfg):
                continue
            # Markdown-копия рядом заменяет HTML и PDF в индексе: у неё есть структура разделов.
            if (
                path.suffix.lower() in {".html", ".htm", ".pdf"}
                and path.with_suffix(".md").exists()
            ):
                continue
            if path.stat().st_size > cfg["max_file_bytes"]:
                raise ValueError(
                    f"Файл превышает max_file_bytes: {rel}; исключите его явно"
                )
            result[rel] = digest(path.read_bytes())
    return dict(sorted(result.items()))


class HTMLText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1
        if not self.hidden and tag in {
            "p",
            "div",
            "br",
            "li",
            "tr",
            "h1",
            "h2",
            "h3",
            "h4",
        }:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style"} and self.hidden:
            self.hidden -= 1
        if not self.hidden and tag in {"p", "div", "li", "tr", "h1", "h2", "h3", "h4"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def docx_document(path):
    with zipfile.ZipFile(path) as archive:
        if archive.getinfo("word/document.xml").file_size > 50_000_000:
            raise ValueError(f"DOCX XML слишком большой: {path.name}")
        return ElementTree.fromstring(archive.read("word/document.xml"))


def docx_headings(path):
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs = docx_document(path).findall(".//w:body//w:p", ns)
    result = []
    has_title = False
    counts = {}
    line = 1
    for paragraph in paragraphs:
        label = "".join(n.text or "" for n in paragraph.findall(".//w:t", ns))
        style = paragraph.find("w:pPr/w:pStyle", ns)
        name = style.get("{" + ns["w"] + "}val", "") if style is not None else ""
        match = re.fullmatch(r"Heading([1-9])", name)
        if name == "Title" or match:
            if name == "Title":
                has_title = True
            level = 1 if name == "Title" else int(match.group(1)) + int(has_title)
            anchor = slug(label)
            num = counts.get(anchor, 0)
            counts[anchor] = num + 1
            result.append(
                {
                    "level": level,
                    "title": label,
                    "slug": anchor if not num else f"{anchor}-{num}",
                    "line": line,
                }
            )
        line += label.count("\n") + 1
    return result


def extract(path):
    suffix = path.suffix.lower()
    if suffix in TEXT:
        return path.read_text(encoding="utf-8-sig"), "line"
    if suffix in {".html", ".htm"}:
        parser = HTMLText()
        parser.feed(path.read_text(encoding="utf-8-sig"))
        return "\n".join(
            x.strip() for x in "".join(parser.parts).splitlines() if x.strip()
        ), "extracted-line"
    if suffix == ".docx":
        document = docx_document(path)
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        return "\n".join(
            "".join(n.text or "" for n in p.findall(".//w:t", ns))
            for p in document.findall(".//w:body//w:p", ns)
        ), "extracted-line"
    if suffix == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(path)
        text = "\n".join(
            f"[page:{i}]\n{p.extract_text() or ''}"
            for i, p in enumerate(reader.pages, 1)
        )
        if not any(p.extract_text() for p in reader.pages):
            raise ValueError(f"PDF требует OCR: {path.name}")
        return text, "extracted-line"
    return "", "asset"


def scalar(value):
    """Только скалярные значения frontmatter: вложенная структура не превращается в текст."""
    return str(value)[:300] if isinstance(value, (str, int, float)) else ""


def slug(text):
    return re.sub(r"[^\w\- ]", "", text.lower()).replace(" ", "-")


def parse(root, rel, cfg):
    path = root / rel
    text, locator = extract(path)
    lines = text.splitlines()
    meta = {}
    offset = 0
    if path.suffix == ".md" and lines and lines[0] == "---":
        for i, line in enumerate(lines[1:201], 1):
            if line == "---":
                value = yaml.safe_load("\n".join(lines[1:i]))
                meta = value if isinstance(value, dict) else {}
                offset = i + 1
                break
    headings = []
    links = []
    title = scalar(meta.get("title")) or path.stem
    counts = {}
    if path.suffix.lower() == ".docx":
        headings = docx_headings(path)
        if headings:
            title = headings[0]["title"]
    if path.suffix == ".md":
        tokens = MarkdownIt("commonmark").parse("\n".join(lines[offset:]))
        for i, token in enumerate(tokens):
            if token.type == "heading_open":
                label = tokens[i + 1].content
                anchor = slug(label)
                num = counts.get(anchor, 0)
                counts[anchor] = num + 1
                anchor = anchor if not num else f"{anchor}-{num}"
                headings.append(
                    {
                        "level": int(token.tag[1:]),
                        "title": label,
                        "slug": anchor,
                        "line": token.map[0] + offset + 1,
                    }
                )
                if len(headings) == 1:
                    title = label
            if token.type == "inline":
                for child in token.children or []:
                    if child.type == "link_open":
                        links.append(
                            {
                                "target": child.attrGet("href"),
                                "line": token.map[0] + offset + 1,
                                "kind": "links",
                            }
                        )
                for child in token.children or []:
                    if child.type != "text":
                        continue
                    for match in re.finditer(
                        r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", child.content
                    ):
                        links.append(
                            {
                                "target": match.group(1),
                                "line": token.map[0] + offset + 1,
                                "kind": "wikilink",
                            }
                        )
    for source in (
        meta.get("sources", []) if isinstance(meta.get("sources", []), list) else []
    ):
        if isinstance(source, str):
            links.append({"target": source, "line": 1, "kind": "source"})
    historical = meta.get("status") in {"historical", "superseded", "archived"}
    patterns = cfg.get("history_globs", []) + cfg.get("default_history_exclude", [])
    historical |= any(
        rel == p or rel.startswith(p.rstrip("/") + "/") or fnmatch.fnmatch(rel, p)
        for p in patterns
    )
    return {
        "path": rel,
        "title": title,
        "text": text,
        "locator": locator,
        "status": "historical" if historical else "current",
        "headings": headings,
        "links": links,
        "offset": offset,
        "source_id": (
            scalar(meta.get("id"))
            or (
                re.match(r"^[SM]\d+\b", title).group()
                if re.match(r"^[SM]\d+\b", title)
                else ""
            )
        ),
    }


SENTENCE_END = re.compile(r"(?<=[.!?;:])\s+")


def pieces(line, max_chars):
    """Длинная строка режется по концу предложения, иначе по пробелу, и лишь затем жёстко."""
    result = []
    pos = 0
    while len(line) - pos > max_chars:
        window = line[pos : pos + max_chars]
        cut = max((m.end() for m in SENTENCE_END.finditer(window)), default=0)
        if cut < max_chars // 2:
            cut = window.rfind(" ") + 1
        if cut < max_chars // 2:
            cut = max_chars
        result.append((pos, line[pos : pos + cut]))
        pos += cut
    result.append((pos, line[pos:]))
    return result


def chunks(document, max_chars):
    """Фрагменты следуют структуре: раздел → абзацы; таблица не рвётся посреди строк."""
    headings = {h["line"]: h for h in document["headings"]}
    stack = []
    buffer = []
    start = 0
    size = 0
    result = []
    start_offset = 0
    last_line = 0
    has_content = False
    in_table = False

    def flush(end):
        if buffer:
            body = "\n".join(buffer)
            if body.strip() and has_content:
                context = " / ".join(h["title"] for h in stack)
                key = digest(
                    f"{document['path']}:{start}:{start_offset}:{end}:{context}:{body}".encode()
                )
                result.append(
                    {
                        "id": key,
                        "path": document["path"],
                        "start_line": start,
                        "end_line": end,
                        "heading": [h["title"] for h in stack],
                        "section": stack[-1]["slug"] if stack else "",
                        "text": body,
                    }
                )

    for line_number, line in enumerate(document["text"].splitlines(), 1):
        if line_number <= document["offset"]:
            continue
        if line_number in headings:
            flush(line_number - 1)
            buffer = []
            size = 0
            has_content = False
            h = headings[line_number]
            while stack and stack[-1]["level"] >= h["level"]:
                stack.pop()
            stack.append(h)
        table_row = line.lstrip().startswith("|")
        # Пустая строка — граница абзаца: почти полный фрагмент закрывается на ней.
        if not line.strip() and buffer and size >= max_chars * 0.6:
            flush(last_line)
            buffer = []
            size = 0
            has_content = False
        # ponytail: таблица держится целой до 3×max_chars; длиннее — режется по строкам
        # без повтора шапки. Повтор шапки добавить, если поиск по большим таблицам подведёт.
        limit = max_chars * 3 if table_row and in_table else max_chars
        for pos, piece in pieces(line, limit):
            if size + len(piece) + 1 > limit and buffer:
                flush(last_line)
                buffer = []
                size = 0
                has_content = False
            if not buffer:
                start = line_number
                start_offset = pos
            buffer.append(piece)
            has_content |= bool(piece.strip()) and line_number not in headings
            size += len(piece) + 1
            last_line = line_number
        in_table = table_row
    flush(len(document["text"].splitlines()))
    return result
