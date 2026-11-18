# Runtime и перенос

Требуются Python 3.11 и `uv`. Глобальный skill устанавливается ссылкой на исходный каталог; при переносе сохрани весь каталог skill, не только SKILL.md. Virtualenv не переносится между машинами.

```sh
python3 scripts/bootstrap.py
python3 scripts/run.py --help
.venv/bin/python scripts/prepare_model.py
```

Bootstrap использует `requirements.lock` и ставит runtime в `.venv` внутри skill. `requirements.in` содержит прямые зависимости, lock фиксирует транзитивные версии. Повторный bootstrap синхронизирует только этот venv. Для другой ОС/архитектуры установка зависит от доступных wheels; текущая приёмка выполнена на macOS arm64/Python 3.11.

`prepare_model.py` явно скачивает модель по ревизии, закреплённой в `embeddings.py`, обычными файлами в `<cache_dir>/<имя модели>/` (MiniLM — `paraphrase-multilingual-MiniLM-L12-v2-onnx-Q/`); fastembed сам ничего не скачивает. Это единственный предусмотренный сетевой шаг для модели. Команда не читает проектные документы. Для проверки имеющегося cache: `prepare_model.py --offline`. На изолированную машину перенеси model cache с сохранением snapshot/blobs/symlinks и wheel mirror, затем установи зависимости из внутреннего источника `uv` и проверь модель. Не объявляй offline-готовность машины, пока реальный smoke не прошёл.

Конфигурация каждой wiki `.wiki.json` наследует defaults; можно указать только переопределения:

```json
{
  "schema_version": 1,
  "include": ["wiki", "raw"],
  "exclude": ["raw/workbench", "raw/extracted"],
  "history_globs": ["raw/history/**"],
  "offline": true,
  "threads": 2,
  "chunk_chars": 400,
  "max_file_bytes": 5000000,
  "cache_dir": "~/.cache/fastembed",
  "model": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
}
```

`include` — относительные каталоги или файлы; `exclude` — префиксы или glob. Нельзя использовать `..` для чтения соседнего code: при необходимости выбери общий root проекта и явно включи его wiki/raw/code подпути. Отсутствующий root не создаётся командами поиска. Смена config вызывает stale, затем нужен index.

Для глобального подключения используй `python3 scripts/install.py [--agents claude,codex,pi,opencode]` (по умолчанию — агенты, чьи каталоги найдены). В `~/.claude/skills`, `$CODEX_HOME/skills`, `~/.pi/agent/skills` или `~/.config/opencode/skills` создаётся папка `llm-wiki/` со ссылками только на `SKILL.md`, `LICENSE`, `agents/`, `references/`, `scripts/`: ссылка на весь репозиторий отдала бы OpenCode чужие `SKILL.md` из `.venv` и соседних плагинов. OpenCode читает и `~/.claude/skills`, поэтому при выбранном Claude Code отдельная копия для него не ставится. Также создаётся launcher `~/.local/bin/llm-wiki`. Чужие файлы не перезаписываются; прежняя ссылка на весь репозиторий заменяется витриной. Если `.local/bin` отсутствует в PATH, работает абсолютный launcher из skill. Список skills текущего чата может быть снимком: для обнаружения новой установки открой новый чат или явно укажи путь SKILL.md.

## Вторая модель и Docling (2026-11-13)

- `"model": "perplexity-ai/pplx-embed-v1-0.6b"` в `.wiki.json` включает адаптер pplx-embed (MIT, 1024 измерения, ONNX q4 ≈ 380 МБ, onnxruntime на CPU, tokenizer.json без remote code). Скачивание: `.venv/bin/python scripts/prepare_model.py --model perplexity-ai/pplx-embed-v1-0.6b`; файлы лежат обычными файлами в `<cache_dir>/pplx-embed-v1-0.6b/`, revision закреплён в `embeddings.py`. Модель по умолчанию прежняя — MiniLM.
- Скорость на Apple M1 Pro: загрузка ≈ 0.5 с, фрагмент в 1200 знаков ≈ 0.7 с при 4 потоках; первая индексация большой базы занимает минуты, далее векторы переиспользуются.
- `convert` требует Docling: `uv pip install --python .venv/bin/python docling` (тянет PyTorch, +≈1 ГБ к venv; при первом запуске скачивает свои модели разметки в cache Hugging Face). В `requirements.lock` Docling не внесён: без него работают все команды, кроме `convert`.
- Для статей разумно `"chunk_chars": 1200`: фрагмент — абзац или таблица внутри своего раздела.
