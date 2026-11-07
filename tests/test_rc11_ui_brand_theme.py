"""MRI-RAG-HELPER N4: presentation must not alter the RAG safety boundary."""

from __future__ import annotations

import tomllib
from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]


def test_n4_public_brand_and_safety_notice():
    app = AppTest.from_file(ROOT / "streamlit_public.py", default_timeout=45).run()
    assert not app.exception and not app.error
    assert [item.value for item in app.title] == ["MRI-RAG-HELPER"]
    assert len(app.warning) == 1
    assert "No introduzca datos de pacientes" in app.warning[0].value


def test_n4_evidence_groups_remain_verifiable():
    app = AppTest.from_file(ROOT / "streamlit_public.py", default_timeout=45).run()
    app.text_input[0].input("¿Cuál es la diferencia entre T1 y T2?")
    app.button[0].click()
    app.run(timeout=45)
    assert not app.exception and not app.error
    assert "Referencias" in {item.value for item in app.subheader}
    markdown = [item.value for item in app.markdown]
    assert "**Evidencia [S1]**" in markdown
    assert "**Evidencia [S2]**" in markdown
    assert sum("](" in item for item in markdown) >= 2


def test_n4_native_light_and_dark_theme_configuration():
    config = tomllib.loads((ROOT / ".streamlit/config.toml").read_text(encoding="utf-8"))
    assert config["theme"]["base"] == "dark"
    assert set(("light", "dark")) <= set(config["theme"])
    assert config["theme"]["light"]["textColor"] != config["theme"]["dark"]["textColor"]


def test_n4_css_has_no_theme_conflict_or_remote_scripts():
    css = (ROOT / "assets/mri_helper.css").read_text(encoding="utf-8").lower()
    assert "prefers-color-scheme" not in css
    assert "color: inherit" in css
    assert "url(" not in css and "@import" not in css and "<script" not in css
