"""SQLite — производный индекс; транзакция не меняет исходные документы."""

import json
import sqlite3

SCHEMA = 2  # 2: FTS с porter-стеммингом английских слов


def connect(root, create=False):
    directory = root / ".index"
    if directory.is_symlink():
        raise ValueError("Symlink .index запрещён")
    path = directory / "wiki.sqlite3"
    if path.is_symlink():
        raise ValueError("Symlink index DB запрещён")
    if not create and not path.exists():
        raise ValueError("Индекс отсутствует; выполните index")
    directory.mkdir(exist_ok=True)
    if create and path.exists() and _stored_schema(path) != SCHEMA:
        # Индекс полностью производный: при смене схемы файл пересоздаётся командой index.
        path.unlink()
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript("""
    CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS documents(path TEXT PRIMARY KEY,hash TEXT NOT NULL,data TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS chunks(id TEXT PRIMARY KEY,path TEXT NOT NULL REFERENCES documents(path) ON DELETE CASCADE,data TEXT NOT NULL,vector TEXT);
    CREATE VIRTUAL TABLE IF NOT EXISTS search_fts USING fts5(id UNINDEXED,text,tokenize='porter unicode61');
    CREATE TABLE IF NOT EXISTS nodes(id TEXT PRIMARY KEY,kind TEXT,path TEXT,label TEXT,line INTEGER);
    CREATE TABLE IF NOT EXISTS edges(src TEXT,dst TEXT,kind TEXT,source_path TEXT,source_line INTEGER,PRIMARY KEY(src,dst,kind,source_path,source_line));
    """)
    version = get(db, "schema", SCHEMA)
    if version != SCHEMA:
        db.close()
        raise ValueError("Несовместимая схема индекса; выполните index")
    if not create:
        db.execute("BEGIN")
    return db


def _stored_schema(path):
    db = sqlite3.connect(path, timeout=10)
    try:
        row = db.execute("SELECT value FROM meta WHERE key='schema'").fetchone()
        return json.loads(row[0]) if row else SCHEMA
    except sqlite3.DatabaseError:
        return None
    finally:
        db.close()


def get(db, key, default=None):
    row = db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return json.loads(row[0]) if row else default


def put(db, key, value):
    db.execute(
        "INSERT OR REPLACE INTO meta VALUES (?,?)",
        (key, json.dumps(value, ensure_ascii=False)),
    )
