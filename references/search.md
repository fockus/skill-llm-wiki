# Поиск и граф

Все команды возвращают JSON, root всегда явный. Ошибки дают код 2; lint с errors тоже. Launcher доступен как `llm-wiki` либо `python3 <skill-directory>/scripts/run.py`.

```sh
llm-wiki status --root /absolute/project/llm-wiki
llm-wiki index --root /absolute/project/llm-wiki
llm-wiki search "как сохраняются данные клиента" --root /absolute/project/llm-wiki --mode hybrid --hops 1 --limit 5
llm-wiki search "Firecracker" --root /absolute/project/llm-wiki --mode fulltext --hops 0
llm-wiki search "восстановление после сбоя" --root /absolute/project/llm-wiki --mode semantic --scope wiki
llm-wiki read wiki/index.md --root /absolute/project/llm-wiki --start 1 --end 80
llm-wiki graph --root /absolute/project/llm-wiki --node file:wiki/index.md --hops 2
llm-wiki lint --root /absolute/project/llm-wiki
```

- `fulltext`: SQLite FTS5/BM25, безопасный OR по словам; без неявного FTS-синтаксиса и русской морфологии. Английские слова приводятся к основе (porter): `diamonds` находит `diamond`. Подходит для имён и точных терминов.
- `semantic`: локальная multilingual модель, порядок по normalized cosine. Возвращаемый score, как и в hybrid, выражен reciprocal rank, а не сырым cosine. Подходит для перефразирования. Результат не означает, что ответ обязательно есть; проверяй цитаты.
- `hybrid`: объединение порядков fulltext и semantic через reciprocal rank fusion. Score не является вероятностью или confidence.
- `--hops 0..3`: добавляет контекст по `links` и `source` в обоих направлениях. До 100 посещённых документов на seed; максимум 2 связанных результата на seed и общий `--limit 1..50`. `via` показывает исходную направленную связь и evidence. Общая папка не превращает соседние документы в релевантные.
- `--scope wiki/topic` ограничивает и seed, и выдаваемые связанные документы; `--include-history` включает архив. Существование пути через исключённый документ не делает его содержимое доступным.

Каждый hit содержит relative/absolute path, SHA256 документа, диапазон строк, breadcrumbs разделов, status, text, score и причину `fulltext|semantic|hybrid|graph`. Для text/Markdown `locator=line` — строки оригинала. Для DOCX/PDF/HTML `locator=extracted-line` — строки извлечённого текста команды `read`, не страницы Word. В PDF сохранены маркеры `[page:N]`; OCR не выполняется. Для бинарных assets строится узел файла без вымышленного searchable text.

Граф содержит `directory → file → section → nested section → chunk`; `graph` раскрывает все эти типы. Для поиска breadcrumbs входят в embedding и FTS-текст. Дополнительно возвращаются явные связи между документами/разделами и их источниками. `graph` без `--node` экспортирует весь граф JSON; для большой базы указывай узел.

При пустой выдаче проверь scope/history, затем переформулируй запрос и прочитай index. При stale — `index`; при недоступной модели — восстанови локальный cache согласно runtime.md. `--lexical-only` создаёт явно полнотекстовый индекс, а semantic/hybrid после него должны завершаться ошибкой. Не представляй такой режим как работающий semantic search.

## Мерка качества

`scripts/eval_search.py --root ROOT --questions FILE.jsonl [--scope raw]` считает для каждого режима долю вопросов, где нужный документ и фрагмент с ответом попали в top-k, и MRR. Строка файла: `{"q": вопрос, "doc": подстрока пути, "answer": regex текста фрагмента}`. Меняешь модель, разбиение или извлечение — сравни числа до и после; `chunk_chars` и `model` задаются в `.wiki.json` каждой wiki.
