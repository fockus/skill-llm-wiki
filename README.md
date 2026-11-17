# llm-wiki

**An agent skill for source-grounded LLM wikis — Karpathy's persistent-wiki pattern plus local GraphRAG search.**

Raw sources stay immutable; the agent reads them and maintains linked Markdown pages with provenance. A local runtime indexes the wiki (SQLite FTS5 + local embeddings + a link/containment graph) so the agent can find evidence across documents and nested sections — no server, no cloud API.

Works with Claude Code and Codex (any agent that loads `SKILL.md` skills).

## Features

- `init` / `ingest` / `index` / `search` / `read` / `lint` / `status` / `convert` CLI with JSON output
- Search modes: `fulltext`, `semantic`, `hybrid` (default), plus graph expansion `--hops N`
- Local multilingual embeddings (MiniLM 384d by default, optional `pplx-embed-v1-0.6b`), incremental reindex
- Formats: Markdown, text, DOCX, PDF (optional Docling `convert` to structured Markdown)
- Per-wiki isolated index (`.index/wiki.sqlite3`), history scoping, lint for broken/isolated links
- Source text is treated as data, never as instructions

## Install

Requires Python 3.11 and [`uv`](https://github.com/astral-sh/uv).

```bash
git clone https://github.com/fockus/skill-llm-wiki.git
cd skill-llm-wiki
python3 scripts/bootstrap.py                 # venv from requirements.lock
.venv/bin/python scripts/prepare_model.py    # downloads the embedding model once
```

Register the skill:

```bash
ln -s "$PWD" ~/.claude/skills/llm-wiki       # Claude Code
python3 scripts/install.py                   # Codex: ~/.codex/skills/llm-wiki + ~/.local/bin/llm-wiki
```

## Usage

```bash
python3 scripts/run.py init --root ~/kb/project --title "Project knowledge"
python3 scripts/run.py ingest paper.pdf --root ~/kb/project
python3 scripts/run.py index --root ~/kb/project
python3 scripts/run.py search "how is auth handled?" --root ~/kb/project --mode hybrid --hops 1
```

In practice you just ask the agent ("add this doc to the project wiki", "what did we decide about X") and it follows [SKILL.md](SKILL.md).

## Docs

Reference docs are in Russian: [architecture](references/architecture.md), [workflows](references/workflows.md), [search](references/search.md), [runtime](references/runtime.md), [verification](references/verification.md).

## Tests

```bash
.venv/bin/python -m pytest -q
```

## License

MIT
