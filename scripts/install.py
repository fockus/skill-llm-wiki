#!/usr/bin/env python3
"""Глобальная регистрация без перезаписи существующих чужих файлов."""

import json
import os
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    config = Path(
        os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))
    ).expanduser()
    targets = {
        config / "skills/llm-wiki": root,
        Path.home() / ".local/bin/llm-wiki": root / "scripts/run.py",
    }
    for target, source in targets.items():
        if os.path.lexists(target) and not (
            target.is_symlink() and target.resolve() == source
        ):
            raise SystemExit(
                f"Конфликт установки: {target}; существующий файл сохранён"
            )
    (root / "scripts/run.py").chmod(0o755)
    for target, source in targets.items():
        target.parent.mkdir(parents=True, exist_ok=True)
        if not os.path.lexists(target):
            target.symlink_to(source, target_is_directory=source.is_dir())
    print(
        json.dumps(
            {
                "skill": str(next(iter(targets))),
                "launcher": str(Path.home() / ".local/bin/llm-wiki"),
            }
        )
    )


if __name__ == "__main__":
    main()
