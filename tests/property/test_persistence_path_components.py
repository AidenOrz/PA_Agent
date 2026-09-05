from __future__ import annotations

from pathlib import Path

from hypothesis import given
from hypothesis import settings as h_settings
from hypothesis import strategies as st

from pa_agent.config.paths import sanitize_filename_component


@given(st.text(max_size=80))
@h_settings(max_examples=100)
def test_filename_component_is_always_one_safe_path_part(raw: str) -> None:
    safe = sanitize_filename_component(raw)
    root = Path("record-root").resolve()
    candidate = (root / f"{safe}.json").resolve()

    assert safe
    assert safe not in {".", ".."}
    assert Path(safe).name == safe
    assert candidate.parent == root
