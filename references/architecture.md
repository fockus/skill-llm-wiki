# Архитектура и границы версии 1

Решение от 2026-11-03: Markdown/raw — первичные данные; SQLite FTS5 + vectors + типизированный граф — восстанавливаемый индекс на каждый wiki root. Отдельный graph/vector server для локального инструмента агента не требуется. Структурный GraphRAG следует реальным ссылкам и происхождению, без LLM-выдуманных рёбер. Это не Microsoft GraphRAG с entity extraction/community summaries и не AST call graph кода.

## Слои

- `contracts.py`: небольшой Embedder port (`identity`, `documents`, `question`).
- `documents.py`: инвентаризация, extraction, Markdown parsing и section chunks.
- `graph.py`: containment, links, provenance, graph inspection.
- `store.py`: SQLite schema/connection. `index.py`: построение поколения, проверка freshness, reuse vectors.
- `embeddings.py`: локальный FastEmbed/ONNX adapter.
- `search.py`: FTS + cosine + RRF + bounded document expansion.
- `project.py`: init/immutable ingest. `health.py`: status/lint/read. `cli.py`: JSON interface.

В `documents` хранятся hash и извлечённый текст; в `chunks` — locators и vectors. `nodes/edges` хранят граф; `meta` — generation, inventory, config/parser fingerprint, модель и размерность. Источник, embedding text (включая ancestors) и координаты определяют chunk ID. Рёбра имеют направление, тип, evidence path/line. Неоднозначные aliases не соединяются.

Index сначала извлекает/проверяет данные и embeddings; затем публикует всё одной SQLite-транзакцией. Ошибка оставляет предыдущее поколение. Удаления/переименования убирают старые chunks и edges. При неизменном тексте и модели vectors переиспользуются; прочая структура пересобирается. Reader использует согласованный snapshot. Конкурирующий writer с устаревшим поколением получает ошибку. Изменения corpus/config делают индекс stale; search не отвечает из заведомо устаревшего корпуса.

## Разбиение и извлечение (parser_version 5)

Фрагмент следует структуре: раздел → абзацы. Почти полный фрагмент закрывается на пустой строке; длинная строка режется по концу предложения, затем по пробелу; строки таблицы держатся вместе до 3×`chunk_chars`. PDF индексируется через Markdown-копию от `convert` (Docling), если она есть, иначе плоским текстом pypdf. FTS использует `porter unicode61` (schema 2; при смене схемы файл индекса пересоздаётся командой `index`).

## Embeddings

Проверенный adapter: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, 384 dimensions, локальный ONNX CPU через FastEmbed 0.9.1. [Официальный список моделей](https://qdrant.github.io/fastembed/examples/Supported_Models/) указывает multilingual/Apache-2.0. Длинный input делится до token limit, векторы частей усредняются и нормализуются; это компромисс маленького локального индекса. Текст не уходит в embedding API.

В identity входят имя, SHA256 файлов model snapshot, версия FastEmbed и adapter. Query проверяет совпадение с индексом. На этой версии проверены два adapter'а: MiniLM через FastEmbed и `perplexity-ai/pplx-embed-v1-0.6b` (ONNX q4, mean pooling из графа, без префиксов; identity — revision, размеры файлов и hash малых файлов); замена model string на произвольную E5/BGE не разрешена без адаптации encoding и regression. FastEmbed `_model_dir` используется для fingerprint, поэтому версия закреплена и проверяется реальным smoke.

## Scope и эксплуатация

Default include `wiki/`, `raw/`; hidden directories, symlinks и служебные paths не индексируются. Удалённый URL не скачивается indexer. Неизвестные форматы — file nodes без текста; oversized files требуют явного exclude/увеличения лимита. Markdown и соседняя HTML-копия не индексируются дважды. Иерархия извлекается из Markdown и стандартных Word Title/HeadingN; HTML/PDF дают плоский извлечённый текст. Для сканов нужен отдельный OCR ingest.

SQLite содержит копии текстов и vectors: защищай его как исходники, не коммить, включай OS/disk encryption и локальные права по требованиям проекта. Этот CLI не является multi-tenant service или sandbox и не заменяет OS ACL. Никаких credentials он не запрашивает. Установка пакетов/модели может требовать сеть; индексирование и поиск по default config работают offline. Сам агент (Claude Code, Codex, pi, OpenCode) может использовать облачный inference независимо от локального retrieval.

Vector ranking перебирает corpus в памяти: подход рассчитан на проектные вики, не миллионы chunks. Большой corpus потребует отдельного ANN adapter/сервера и нагрузочных замеров. `.index/` можно восстановить командой index; перенос проекта переносит Markdown/raw/config, cache не является единственным носителем знаний. Background watcher и автоматический коммит не запускаются.

## Расширения

Новый parser добавляется через extract/parse и contract tests с locators; новая модель — через Embedder с identity/encoding tests; новое ребро — с evidence и проверкой traversal budgets. Перед изменением parser/embedding semantics меняй version/fingerprint и перестраивай индекс. Поиск по коду сейчас текстовый и файловый; AST, entities, community summaries и MCP server — отдельные расширения, не скрытые обещания текущей версии.
