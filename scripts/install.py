#!/usr/bin/env python3
"""Регистрация skill в Claude Code, Codex, pi и OpenCode без перезаписи чужих файлов.

В каталог агента ставится не ссылка на весь репозиторий, а папка-витрина со ссылками
только на файлы skill. Иначе OpenCode рекурсивно находит чужие SKILL.md внутри
.venv (typer, docling) и в соседних плагинах репозитория. SKILL.md копируется:
Codex 0.170 молча пропускает SKILL.md, если это symlink на файл. После обновления
репозитория запусти install.py снова, чтобы освежить копию.
"""

import argparse
import json
import os
import shutil
from pathlib import Path

NAME = "llm-wiki"
PAYLOAD = ["SKILL.md", "LICENSE", "agents", "references", "scripts"]
AGENTS = ["claude", "codex", "pi", "opencode"]


def skill_dirs(home, codex_home=None):
    return {
        "claude": home / ".claude/skills",
        "codex": (codex_home or home / ".codex") / "skills",
        "pi": home / ".pi/agent/skills",
        "opencode": home / ".config/opencode/skills",
    }


def _ours(target, root):
    """True для прежней ссылки на весь репозиторий или витрины этого скрипта."""
    if target.is_symlink():
        return target.resolve() == root
    if not target.is_dir():
        return False
    entries = list(target.iterdir())
    links = [e for e in entries if e.name != "SKILL.md"]
    # SKILL.md — копия любой версии; принадлежность определяют ссылки на репозиторий.
    return bool(links) and all(
        e.is_symlink() and e.resolve() == root / e.name for e in links
    )


def _place(target, root):
    if target.is_symlink():
        target.unlink()
    target.mkdir(parents=True, exist_ok=True)
    for entry in target.iterdir():
        if entry.name not in PAYLOAD:
            entry.unlink()
    skill = target / "SKILL.md"
    if skill.is_symlink():
        skill.unlink()
    shutil.copyfile(root / "SKILL.md", skill)
    for name in PAYLOAD:
        link = target / name
        if not os.path.lexists(link):
            link.symlink_to(root / name, target_is_directory=(root / name).is_dir())


def install(root, home, agents, codex_home=None):
    root = Path(root).resolve()
    dirs = skill_dirs(Path(home), codex_home)
    chosen = [a for a in AGENTS if a in agents]
    # OpenCode сам читает ~/.claude/skills: вторая копия дала бы дубликат имени.
    if "claude" in chosen and "opencode" in chosen:
        chosen.remove("opencode")
    targets = {agent: dirs[agent] / NAME for agent in chosen}
    launcher = Path(home) / ".local/bin" / NAME
    conflicts = [
        str(t) for t in targets.values() if os.path.lexists(t) and not _ours(t, root)
    ]
    if os.path.lexists(launcher) and launcher.resolve() != root / "scripts/run.py":
        conflicts.append(str(launcher))
    if conflicts:
        raise SystemExit(
            f"Конфликт установки: {conflicts}; существующие файлы сохранены"
        )
    for target in targets.values():
        _place(target, root)
    (root / "scripts/run.py").chmod(0o755)
    if not os.path.lexists(launcher):
        launcher.parent.mkdir(parents=True, exist_ok=True)
        launcher.symlink_to(root / "scripts/run.py")
    return {
        "skills": {agent: str(path) for agent, path in targets.items()},
        "launcher": str(launcher),
    }


def main():
    home = Path.home()
    codex_home = Path(os.environ.get("CODEX_HOME", home / ".codex")).expanduser()
    homes = {
        "claude": home / ".claude",
        "codex": codex_home,
        "pi": home / ".pi/agent",
        "opencode": home / ".config/opencode",
    }
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--agents",
        default=",".join(a for a in AGENTS if homes[a].is_dir()),
        help="Через запятую из: " + ", ".join(AGENTS) + "; по умолчанию найденные",
    )
    agents = [a for a in parser.parse_args().agents.split(",") if a]
    if not agents or set(agents) - set(AGENTS):
        parser.error(f"Ожидаются агенты из {AGENTS}, получено {agents}")
    root = Path(__file__).resolve().parents[1]
    print(
        json.dumps(
            install(root, home, agents, codex_home), ensure_ascii=False, indent=2
        )
    )


if __name__ == "__main__":
    main()
