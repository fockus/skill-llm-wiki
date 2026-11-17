#!/usr/bin/env python3
"""Установка закреплённых зависимостей только в собственный virtualenv."""

from pathlib import Path
import shutil
import subprocess


def main():
    root = Path(__file__).resolve().parents[1]
    uv = shutil.which("uv")
    if not uv:
        raise SystemExit(
            "Установите uv и повторите bootstrap; системный Python не изменяется"
        )
    venv = root / ".venv"
    if not (venv / "bin/python").is_file():
        subprocess.run([uv, "venv", str(venv), "--python", "3.11"], check=True)
    subprocess.run(
        [
            uv,
            "pip",
            "sync",
            "--python",
            str(venv / "bin/python"),
            str(root / "requirements.lock"),
        ],
        check=True,
    )


if __name__ == "__main__":
    main()
