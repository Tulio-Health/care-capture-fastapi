"""T10 -- VISIT_SUMMARY_ALLOWLIST_ENABLED flag: default OFF, SSM-mapped, env-parsed."""
import pytest

from src.app.config.ssm_loader import SSMParameterLoader
from src.app.core.settings import Settings


def test_flag_defaults_to_false(monkeypatch):
    monkeypatch.delenv("VISIT_SUMMARY_ALLOWLIST_ENABLED", raising=False)
    assert Settings().VISIT_SUMMARY_ALLOWLIST_ENABLED is False


@pytest.mark.parametrize("raw,expected", [("true", True), ("True", True), ("1", True), ("false", False), ("0", False)])
def test_flag_parses_ssm_style_string_values(monkeypatch, raw, expected):
    monkeypatch.setenv("VISIT_SUMMARY_ALLOWLIST_ENABLED", raw)
    assert Settings().VISIT_SUMMARY_ALLOWLIST_ENABLED is expected


def test_flag_has_an_ssm_mapping_that_is_not_secure():
    mappings = {m.ssm_path: m for m in SSMParameterLoader.get_parameter_mappings()}
    mapping = mappings["summary/visit_summary_allowlist_enabled"]
    assert mapping.env_var == "VISIT_SUMMARY_ALLOWLIST_ENABLED"
    assert mapping.is_secure is False
    # the mapped env var is a real Settings field (a typo here would silently never apply)
    assert mapping.env_var in Settings.model_fields
