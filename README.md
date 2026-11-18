# llm-wiki

**An agent skill for source-grounded LLM wikis — Karpathy's persistent-wiki pattern plus local GraphRAG search.**

Raw sources stay immutable; the agent reads them and maintains linked Markdown pages with provenance. A local runtime indexes the wiki (SQLite FTS5 + local embeddings + a link/containment graph) so the agent can find evidence across documents and nested sections — no server, no cloud API.

Works with **Claude Code, Codex, pi and OpenCode** — any agent that loads [Agent Skills](https://agentskills.io) (`SKILL.md`).

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

Register the skill in every agent found on the machine (or pick: `--agents claude,codex,pi,opencode`):

```bash
python3 scripts/install.py
```

| Agent | Skill path |
|---|---|
| Claude Code | `~/.claude/skills/llm-wiki` |
| Codex | `$CODEX_HOME/skills/llm-wiki` (default `~/.codex`) |
| pi | `~/.pi/agent/skills/llm-wiki` |
| OpenCode | reads `~/.claude/skills`; `~/.config/opencode/skills/llm-wiki` only when Claude Code is not selected |

Each path is a small folder of symlinks to `SKILL.md`, `scripts/`, `references/`, `agents/`, `LICENSE` — not a link to the whole repo, so agents that scan recursively (OpenCode) don't pick up `SKILL.md` files from `.venv` packages. The installer never overwrites foreign files and upgrades old whole-repo symlinks. It also adds the `~/.local/bin/llm-wiki` launcher.

## Installing with a coding agent

Paste this into Claude Code, Codex, pi, OpenCode or another coding agent:

> Install the llm-wiki skill from https://github.com/fockus/skill-llm-wiki following the "Steps for agents" section of its README.

### Steps for agents

1. **Prerequisites.** Check `git` and `uv --version`. If `uv` is missing, stop and ask the user to install it (https://docs.astral.sh/uv/). `uv` fetches Python 3.11 itself if needed.
2. **Clone to a permanent location** — the skill is registered by symlink, so the clone must stay. Default: `~/.local/share/skill-llm-wiki`. If the directory exists, `git pull` instead of cloning.
   ```bash
   git clone https://github.com/fockus/skill-llm-wiki.git ~/.local/share/skill-llm-wiki
   cd ~/.local/share/skill-llm-wiki
   ```
3. **Dependencies:** `python3 scripts/bootstrap.py` — creates `.venv` inside the clone from `requirements.lock`; never touches system Python.
4. **Model** (network, ~240 MB): `.venv/bin/python scripts/prepare_model.py`. It must print `"dimension": 384`. Download the optional second model only if the user asks (see [Models](#models)).
5. **Register:** `python3 scripts/install.py` — installs into every agent whose config dir exists (Claude Code, Codex, pi, OpenCode); limit with `--agents`. If it reports `Конфликт установки` (a foreign file at the target), stop and ask the user — do not delete anything. Do not hand-symlink the whole clone into a skills dir: OpenCode would then also load the `SKILL.md` files of packages inside `.venv`.
6. **Smoke test:**
   ```bash
   T=$(mktemp -d)
   python3 scripts/run.py init --root "$T" --title Smoke
   printf '# Backups\nNightly snapshots restore data after a power failure.\n' > "$T/wiki/backups.md"
   python3 scripts/run.py index --root "$T"
   python3 scripts/run.py search "how to recover after outage" --root "$T" --mode semantic
   ```
   The search must return `wiki/backups.md`. Then delete `$T`.
7. **Tell the user** to start a new agent session — skill lists are loaded at session start.

Docling (`convert` for PDF → Markdown) adds ~1 GB (PyTorch); install it only on request: `uv pip install --python .venv/bin/python docling`.

## Models

Embeddings run locally on CPU via ONNX; document text never leaves the machine. Weights are **not** in this repo: `scripts/prepare_model.py` downloads them from Hugging Face at a revision pinned in [`embeddings.py`](scripts/llm_wiki/embeddings.py) into `~/.cache/fastembed/<model>/` (change with `cache_dir` in `.wiki.json`). Search and indexing never download anything: if the model is missing they fail with a hint instead of silently falling back to fulltext.

| Model (`model` in `.wiki.json`) | Source repo | Dim | Size | License | Download |
|---|---|---|---|---|---|
| `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (default) | [Qdrant/paraphrase-multilingual-MiniLM-L12-v2-onnx-Q](https://huggingface.co/Qdrant/paraphrase-multilingual-MiniLM-L12-v2-onnx-Q) | 384 | ~250 MB | Apache-2.0 | `prepare_model.py` |
| `perplexity-ai/pplx-embed-v1-0.6b` (optional, ONNX q4) | [perplexity-ai/pplx-embed-v1-0.6b](https://huggingface.co/perplexity-ai/pplx-embed-v1-0.6b) | 1024 | ~390 MB | MIT | `prepare_model.py --model perplexity-ai/pplx-embed-v1-0.6b` |

`prepare_model.py --offline` only checks the local copy. For an air-gapped machine, copy the model folder from `cache_dir` along with the clone. Switching models marks the index stale; run `index` to re-embed.

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
