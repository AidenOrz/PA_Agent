"""Settings persistence safety tests without touching the live config."""
from __future__ import annotations

import json

from pa_agent.config import settings as settings_module
from pa_agent.config.settings import Settings, load_settings, save_settings


def test_provider_key_is_encrypted_and_json_is_atomic(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(
        settings_module,
        "_dpapi_protect",
        lambda value: "dpapi:protected-" + value,
    )
    monkeypatch.setattr(
        settings_module,
        "_dpapi_unprotect",
        lambda value: value.removeprefix("dpapi:protected-"),
    )
    path = tmp_path / "settings.json"
    save_settings(Settings(provider={"api_key": "test-key"}), path)

    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["provider"]["api_key"] == ""
    assert raw["provider"]["api_key_encrypted"] == "dpapi:protected-test-key"
    assert not list(tmp_path.glob("*.tmp"))
    assert load_settings(path).provider.api_key == "test-key"


def test_invalid_settings_are_preserved_and_fall_back_to_defaults(tmp_path) -> None:
    path = tmp_path / "settings.json"
    original = "{not-json"
    path.write_text(original, encoding="utf-8")

    settings = load_settings(path)

    assert settings == Settings()
    assert path.read_text(encoding="utf-8") == original
