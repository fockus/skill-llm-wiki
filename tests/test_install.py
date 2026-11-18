import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import install

AGENTS = ["claude", "codex", "pi", "opencode"]


def _skill_files(folder):
    found = []
    for base, dirs, files in os.walk(folder, followlinks=True):
        found += [Path(base) / f for f in files if f == "SKILL.md"]
    return found


def test_install_all_agents_exposes_exactly_one_skill_each(tmp_path):
    result = install.install(REPO, home=tmp_path, agents=AGENTS)

    targets = [Path(p) for p in result["skills"].values()]
    assert set(result["skills"]) == {"claude", "codex", "pi"}
    for target in targets:
        assert _skill_files(target) == [target / "SKILL.md"]
        assert not (target / ".venv").exists()
        assert not (target / "hermes").exists()
        assert (target / "scripts/run.py").resolve() == REPO / "scripts/run.py"
        # Codex 0.170 молча пропускает SKILL.md, если это symlink на файл.
        assert not (target / "SKILL.md").is_symlink()
        assert (target / "SKILL.md").read_bytes() == (REPO / "SKILL.md").read_bytes()


def test_reinstall_refreshes_stale_skill_md_copy(tmp_path):
    result = install.install(REPO, home=tmp_path, agents=["codex"])
    skill = Path(result["skills"]["codex"]) / "SKILL.md"
    assert not skill.is_symlink()  # иначе запись ниже испортит SKILL.md репозитория
    skill.write_text("устаревшая копия")

    install.install(REPO, home=tmp_path, agents=["codex"])

    assert skill.read_bytes() == (REPO / "SKILL.md").read_bytes()


def test_install_opencode_alone_uses_its_own_skills_dir(tmp_path):
    result = install.install(REPO, home=tmp_path, agents=["opencode"])

    assert result["skills"] == {
        "opencode": str(tmp_path / ".config/opencode/skills/llm-wiki")
    }


def test_install_migrates_legacy_whole_repo_symlink(tmp_path):
    legacy = tmp_path / ".codex/skills/llm-wiki"
    legacy.parent.mkdir(parents=True)
    legacy.symlink_to(REPO, target_is_directory=True)

    install.install(REPO, home=tmp_path, agents=["codex"])

    assert legacy.is_dir() and not legacy.is_symlink()
    assert _skill_files(legacy) == [legacy / "SKILL.md"]


def test_install_twice_is_idempotent(tmp_path):
    first = install.install(REPO, home=tmp_path, agents=["pi"])
    second = install.install(REPO, home=tmp_path, agents=["pi"])
    assert first == second


def test_install_foreign_skill_dir_is_preserved_and_reported(tmp_path):
    foreign = tmp_path / ".claude/skills/llm-wiki"
    foreign.mkdir(parents=True)
    (foreign / "SKILL.md").write_text("чужой")

    with pytest.raises(SystemExit, match="Конфликт"):
        install.install(REPO, home=tmp_path, agents=["claude"])
    assert (foreign / "SKILL.md").read_text() == "чужой"


def test_installed_launcher_runs_cli_through_skill_view(tmp_path):
    result = install.install(REPO, home=tmp_path, agents=["claude"])
    run = Path(result["skills"]["claude"]) / "scripts/run.py"

    done = subprocess.run(
        [sys.executable, str(run), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    assert "search" in done.stdout
