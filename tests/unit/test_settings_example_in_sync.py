"""Keep config/settings.example.json in lock-step with the pydantic defaults.

The template had drifted badly: it advertised ``deepseek-chat`` /
``context_window=128000`` (code defaults: ``deepseek-v4-flash`` / 2000000),
told users validation defaults were ``strict`` when they are ``lenient``, and
omitted seven real fields (``kline_adjust``, ``retry_max`` ...). A template
that disagrees with the code is worse than no template — the README quotes it
as the source of truth for defaults.
"""

from __future__ import annotations

import json

from pa_agent.config.paths import PROJECT_ROOT
from pa_agent.config.settings import Settings

EXAMPLE_PATH = PROJECT_ROOT / "config" / "settings.example.json"


def _example() -> dict:
    return json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))


def test_example_covers_every_setting_group() -> None:
    example = _example()
    expected = set(Settings.model_fields)
    assert (
        set(example) == expected
    ), f"settings.example.json groups {sorted(example)} != model groups {sorted(expected)}"


def test_example_has_no_unknown_keys() -> None:
    example = _example()
    settings = Settings()
    unknown: list[str] = []
    for group, values in example.items():
        fields = type(getattr(settings, group)).model_fields
        unknown.extend(f"{group}.{key}" for key in values if key not in fields)
    assert unknown == [], f"settings.example.json has unknown keys: {unknown}"


def test_example_matches_code_defaults() -> None:
    """The template must not silently disagree with the shipped defaults."""
    example = _example()
    defaults = Settings().model_dump()
    mismatched = {
        f"{group}.{key}": (values[key], defaults[group][key])
        for group, values in example.items()
        for key in values
        if values[key] != defaults[group][key]
    }
    assert mismatched == {}, f"example != defaults (example, default): {mismatched}"


def test_readme_documents_every_group() -> None:
    """config/README.md used to claim "four top-level groups" while there are seven."""
    readme = (PROJECT_ROOT / "config" / "README.md").read_text(encoding="utf-8")
    for group in Settings.model_fields:
        assert f"### {group}" in readme, f"config/README.md has no section for {group}"


def test_readme_documents_every_field() -> None:
    """Every documented-elsewhere-but-not-here field is a trap for users."""
    readme = (PROJECT_ROOT / "config" / "README.md").read_text(encoding="utf-8")
    missing = [
        f"{group}.{key}"
        for group, values in Settings().model_dump().items()
        for key in values
        if f"`{group}.{key}`" not in readme
    ]
    assert missing == [], f"config/README.md does not document: {missing}"
