"""Packaged (PyInstaller) path resolution.

A frozen build splits one root into two: the .exe folder owns user data while
``_internal/`` owns read-only assets.  Getting this wrong is silent — the app
starts, then fails to find prompt_engineering or writes settings into a
read-only install directory — so every branch is pinned here.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from pa_agent.config import paths


@pytest.fixture
def frozen(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Pretend to run from a onedir build: <tmp>/PA_Agent/PA_Agent.exe."""
    app_dir = tmp_path / "PA_Agent"
    internal = app_dir / "_internal"
    internal.mkdir(parents=True)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(app_dir / "PA_Agent.exe"))
    monkeypatch.setattr(sys, "_MEIPASS", str(internal), raising=False)
    return app_dir


def test_source_checkout_keeps_single_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)

    assert paths._runtime_root() == paths._source_root()
    assert paths._bundle_root() == paths._source_root()
    # The repo really ships these next to the package.
    assert (paths._source_root() / "prompt_engineering").is_dir()


def test_frozen_runtime_root_is_the_exe_folder(frozen: Path) -> None:
    assert paths._is_frozen() is True
    assert paths._runtime_root() == frozen
    assert paths._bundle_root() == frozen / "_internal"


def test_prompt_dir_prefers_bundle_when_frozen(
    frozen: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundled = frozen / "_internal" / "prompt_engineering"
    bundled.mkdir()
    monkeypatch.setattr(paths, "PROJECT_ROOT", frozen)
    monkeypatch.setattr(paths, "BUNDLE_ROOT", frozen / "_internal")
    monkeypatch.delenv("PA_AGENT_PROMPT_DIR", raising=False)

    assert paths._prompt_dir() == bundled


def test_prompt_dir_prefers_loose_folder_next_to_exe(
    frozen: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Users may drop an edited prompt library beside the exe; that must win."""
    loose = frozen / "prompt_engineering"
    loose.mkdir()
    monkeypatch.setattr(paths, "PROJECT_ROOT", frozen)
    monkeypatch.setattr(paths, "BUNDLE_ROOT", frozen / "_internal")
    monkeypatch.delenv("PA_AGENT_PROMPT_DIR", raising=False)

    assert paths._prompt_dir() == loose


def test_prompt_dir_env_override(
    frozen: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    custom = tmp_path / "my-prompts"
    custom.mkdir()
    monkeypatch.setattr(paths, "PROJECT_ROOT", frozen)
    monkeypatch.setattr(paths, "BUNDLE_ROOT", frozen / "_internal")
    monkeypatch.setenv("PA_AGENT_PROMPT_DIR", str(custom))

    assert paths._prompt_dir() == custom.resolve()
