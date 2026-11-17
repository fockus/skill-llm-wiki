"""Конфигурация одной wiki и проверка её файловых границ."""

import json
from pathlib import Path, PurePosixPath


DEFAULTS = {
    "schema_version": 1,
    "include": ["wiki", "raw"],
    "exclude": [],
    "model": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    "cache_dir": "~/.cache/fastembed",
    "chunk_chars": 400,
    "max_file_bytes": 5_000_000,
    "default_history_exclude": ["raw/history"],
    "history_globs": [],
    "offline": True,
    "threads": 2,
}


def safe_path(root: Path, relative: str) -> Path:
    """Разрешает только относительный путь внутри указанного wiki root."""
    if not isinstance(relative, str) or not relative.strip() or "\\" in relative:
        raise ValueError("Путь должен быть непустым относительным POSIX-путём")
    path = PurePosixPath(relative)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"Путь выходит за пределы wiki: {relative}")
    root = Path(root).expanduser().resolve()
    candidate = root.joinpath(*path.parts)
    if not candidate.resolve().is_relative_to(root):
        raise ValueError(f"Symlink выходит за пределы wiki: {relative}")
    return candidate


def validate(root: Path, data: dict) -> dict:
    if not isinstance(data, dict):
        raise ValueError("Конфигурация должна быть JSON object")
    unknown = set(data) - set(DEFAULTS)
    if unknown:
        raise ValueError(f"Неизвестные параметры конфигурации: {sorted(unknown)}")
    values = json.loads(json.dumps(DEFAULTS))
    values.update(data)
    if type(values["schema_version"]) is not int or values["schema_version"] != 1:
        raise ValueError("Неподдерживаемая schema_version; ожидается 1")
    for key in ["include", "exclude", "default_history_exclude"]:
        paths = values[key]
        if not isinstance(paths, list) or (key == "include" and not paths):
            raise ValueError(f"{key} должен быть списком относительных путей")
        for item in paths:
            safe_path(root, item)
            if key == "include" and any(
                part in {".git", ".index"} for part in PurePosixPath(item).parts
            ):
                raise ValueError("Нельзя индексировать .git или .index")
    for key in ["model", "cache_dir"]:
        if not isinstance(values[key], str) or not values[key].strip():
            raise ValueError(f"{key} должен быть непустой строкой")
    for key in ["chunk_chars", "max_file_bytes", "threads"]:
        if type(values[key]) is not int or values[key] <= 0:
            raise ValueError(f"{key} должен быть положительным целым числом")
    if type(values["offline"]) is not bool:
        raise ValueError("offline должен быть boolean")
    if not isinstance(values["history_globs"], list) or not all(
        isinstance(item, str) and item.strip() for item in values["history_globs"]
    ):
        raise ValueError("history_globs должен быть списком непустых строк")
    return values


def load(root: Path) -> dict:
    root = Path(root).expanduser().resolve()
    path = safe_path(root, ".wiki.json")
    if not path.is_file():
        raise ValueError(f"Нет конфигурации {path}; сначала выполните init")
    return validate(root, json.loads(path.read_text(encoding="utf-8")))
