"""The "analysis mode" setting must not pretend to exist.

``analysis_mode`` was read from ``settings.general`` by the orchestrator and
written by the GUI mode selector, but ``GeneralSettings`` never declared the
field.  Pydantic (``extra="ignore"``) rejects the assignment with ValueError,
and the orchestrator silently fell back to the default, so the two "analysis
processes" were never differentiated. These tests pin the current, honest
behaviour: the field is absent and every mode produces the same Stage 1 rules.
"""
from __future__ import annotations

import pytest

from pa_agent.ai.prompt_assembler import (
    _STAGE1_OUTPUT_REMINDER,
    _stage1_output_reminder_for_mode,
)
from pa_agent.config.settings import GeneralSettings


def test_general_settings_has_no_analysis_mode_field() -> None:
    """If this ever becomes a real field, wire the prompt variants too."""
    assert "analysis_mode" not in GeneralSettings.model_fields


def test_setting_analysis_mode_raises() -> None:
    general = GeneralSettings()
    with pytest.raises(ValueError):
        general.analysis_mode = "optimized"  # type: ignore[attr-defined]


@pytest.mark.parametrize("mode", ["original", "optimized", "", "bogus"])
def test_stage1_rules_identical_for_every_mode(mode: str) -> None:
    assert _stage1_output_reminder_for_mode(mode) == _STAGE1_OUTPUT_REMINDER