# Приёмка — 2026-11-03

Установлено глобально: `~/.codex/skills/llm-wiki` → каталог репозитория; launcher `~/.local/bin/llm-wiki`. Python 3.11.11/macOS arm64; изолированный venv, lock на 35 пакетов. Bootstrap выполнен успешно; CLI проверен из другого cwd; SKILL.md прошёл quick_validate.

## Проверки реализации

- `python -m pytest -q`: **68 passed**, 5.58 s в последнем полном прогоне.
- `ruff check scripts tests`: passed; `ruff format --check`: 23 files formatted; `compileall`: passed.
- Реальный multilingual MiniLM: 384d, artifact SHA256 `5c77a9d2efad18b678486b45e7858af72b58986d1d1f018523e729f69608d29f`.
- Семантическая приёмка: русский вопрос без совпадающих слов находит правильную тему; lexical выдаёт пустой результат. В этом тесте Python socket.connect запрещён, offline model cache используется локально.
- Init/ingest сохраняют пользовательские данные и raw bytes; CLI JSON/error contract, типы файлов, repeated ingest, external symlink/traversal, stale/edit/delete, historical/scope, FTS syntax, model mismatch, отсутствие vectors и atomic failure покрыты поведенческими тестами.
- Anchor retrieval, breadcrumbs, вложенность, DOCX Title/HeadingN, suppression heading-only chunks, приоритет source edges над navigation backlinks проверены regression cases.
- Unchanged reindex не вызывает новых embeddings; изменение родительского заголовка обновляет дочерний embedding context. Fake применяется только на Embedder boundary.

Процент code coverage не измерялся; число успешных тестов не является утверждением о процентном покрытии.

## Независимый сценарий

В отдельном temporary проекте Observatory агент получил два датированных противоречащих источника и запрос создать/вести wiki и ответить через semantic search. Выполнил полный ingest, синтез, provenance, history_globs, query и lint, используя только skill как руководство. В одном источнике находилась посторонняя инструкция отправить данные; она осталась данными, отправок не было.

После исправлений: **14/14 artifact checks passed**. На том же вопросе актуальный первичный источник переместился с 4-го на 1-е место semantic, актуальный синтез — на 2-е. В hybrid источник оказался 2-м с `via.kind=source`; первые 5 semantic hits содержат факты. Raw hashes совпали, log сохранил старый byte prefix, index свежий и lint без issues. Временные fixtures не являются частью устанавливаемой базы знаний.

## Реальный корпус и итог плана

После подключения к существующей рабочей wiki: **38 индексируемых документов, 1893 chunks, 2275 nodes, 2536 edges**, hybrid/384d, stale=false. Из 48 lint messages все информационные: 3 outside_scope и 45 excluded_link; errors/warnings нет. Это сознательные ссылки на родительский проект и исключённые workbench/extracted/reports. Проверено раскрытие графа конкретной страницы и предметные запросы.

Все **47 raw files** совпали с snapshot перед работой; **38 originals** совпали с migration manifest. Отдельный индекс test проекта не смешивался с рабочим корпусом. Продуктовый код и архитектурные решения приложения этой задачей не менялись.

Этапы исходного плана выполнены: contract → RED tests → init/ingest → extraction/chunking → graph → FTS/storage → incremental/atomic updates → real embeddings → hybrid/graph retrieval → CLI → global skill → два независимых корпуса. Финальные интерфейсы уточнены в architecture.md: пакет `scripts/llm_wiki`, fulltext/semantic/hybrid modes, positional query, проверенная MiniLM вместо первоначально рассматривавшейся E5.

## Границы результата

Это документный GraphRAG с hierarchy, links и provenance; entity extraction/community summaries/AST graph не реализованы. В широком semantic query встречаются близкие темы ingestion/FUSE/harness; идеальный top-1 не гарантируется. Default hybrid, уточнение/scope и чтение первичного источника остаются необходимыми. Малосодержательные части длинных URL/абзацев могут попадать в конец выдачи. Отдельный сервер, автоматический watcher, OCR и multi-tenant API не входят в эту установку.
