#!/usr/bin/env python3
"""Переносимый launcher: всегда использует изолированный runtime этого skill."""

import json
import os
from pathlib import Path
import sys


def main():
    root = Path(__file__).resolve().parents[1]
    python = root / ".venv/bin/python"
    if not python.is_file():
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": f"Runtime отсутствует; python3 {root}/scripts/bootstrap.py",
                }
            ),
            file=sys.stderr,
        )
        return 2
    os.execv(str(python), [str(python), str(root / "scripts/wiki.py"), *sys.argv[1:]])


if __name__ == "__main__":
    sys.exit(main())
