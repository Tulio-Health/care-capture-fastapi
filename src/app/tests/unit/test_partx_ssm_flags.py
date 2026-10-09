"""Part X flags: SSM mappings (summary/<env var lower-cased>), fail-safe value handling, the
default-OFF settings contract and the ``partx_flags`` startup log line."""

import logging
from unittest.mock import MagicMock

import pytest

from src.app.config.configuration_summary import log_partx_flags_configuration
from src.app.config.ssm_loader import (
    PARTX_BOOL_FLAGS,
    PARTX_FLOAT_SETTINGS,
    PARTX_SSM_ENV_VARS,
    SSMParameterLoader,
    sanitize_partx_value,
)
from src.app.core.settings import reset_settings
from src.app.core.settings import Settings

PREFIX = "/tuliohealth/test"

EXPECTED_BOOL_FLAGS = {
    "EXTRACTION_TRUNCATION_SPLIT_ENABLED",
    "EXTRACTION_INVALID_SPLIT_ENABLED",
    "PROCEDURE_STATUS_V2_ENABLED",
    "DROP_UNGROUNDED_DIAGNOSIS_ENABLED",
    "DROP_UNGROUNDED_ANCHORS_ENABLED",
    "EVIDENCE_REPAIR_HINTS_ENABLED",
    "EVIDENCE_FALLBACK_ENABLED",
    "SUMMARY_CLUTTER_FILTER_ENABLED",
    "SUMMARY_LABEL_FIXES_ENABLED",
    "MEDICATION_RETENTION_ENABLED",
    "MEDICATION_DOSE_CHECK_ENABLED",
    "MEDICATION_DOSE_CHECK_V2_ENABLED",
    "MEDICATION_NAME_CHECK_ENABLED",
    "SUMMARY_DATE_CHECK_ENABLED",
    "CDA_COMPACT_EXTRACTION_ENABLED",
}


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in PARTX_SSM_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    reset_settings()
    yield
    reset_settings()


def _loader(params):
    loader = SSMParameterLoader.__new__(SSMParameterLoader)
    loader.parameter_prefix = PREFIX
    loader._ssm_available = True
    client = MagicMock()
    client.get_parameters_by_path.return_value = {
        "Parameters": [{"Name": f"{PREFIX}/{k}", "Value": v} for k, v in params.items()]
    }
    loader.ssm_client = client
    return loader


def test_flag_set_is_complete_and_every_flag_defaults_off():
    assert set(PARTX_BOOL_FLAGS) == EXPECTED_BOOL_FLAGS
    assert PARTX_FLOAT_SETTINGS == ("EXTRACTION_CALL_TIMEOUT_S",)
    s = Settings()
    for name in PARTX_BOOL_FLAGS:
        assert getattr(s, name) is False, name
    assert s.EXTRACTION_CALL_TIMEOUT_S == 45.0


def test_every_flag_has_a_non_secure_mapping_to_a_real_settings_field():
    mappings = {m.ssm_path: m for m in SSMParameterLoader.get_parameter_mappings()}
    for env_var in PARTX_SSM_ENV_VARS:
        mapping = mappings[f"summary/{env_var.lower()}"]
        assert mapping.env_var == env_var
        assert mapping.is_secure is False
        assert env_var in Settings.model_fields


def test_mapping_present_is_loaded_and_normalised():
    out = _loader(
        {
            "summary/procedure_status_v2_enabled": "TRUE",
            "summary/medication_retention_enabled": "0",
            "summary/extraction_call_timeout_s": "90",
        }
    )._load_parameters_core()
    assert out["PROCEDURE_STATUS_V2_ENABLED"] == "true"
    assert out["MEDICATION_RETENTION_ENABLED"] == "false"
    assert out["EXTRACTION_CALL_TIMEOUT_S"] == "90.0"


def test_absent_parameters_leave_defaults():
    out = _loader({"summary/visit_summary_allowlist_enabled": "true"})._load_parameters_core()
    assert not any(name in out for name in PARTX_SSM_ENV_VARS)


@pytest.mark.parametrize("raw", ["enable", "", "maybe", "2", "tru e"])
def test_invalid_bool_is_ignored(raw):
    out = _loader({"summary/evidence_fallback_enabled": raw})._load_parameters_core()
    assert "EVIDENCE_FALLBACK_ENABLED" not in out


@pytest.mark.parametrize("raw", ["abc", "nan", "inf", "-5", "0", ""])
def test_invalid_timeout_is_ignored(raw):
    out = _loader({"summary/extraction_call_timeout_s": raw})._load_parameters_core()
    assert "EXTRACTION_CALL_TIMEOUT_S" not in out


def test_invalid_value_does_not_drop_other_parameters():
    out = _loader(
        {
            "summary/evidence_fallback_enabled": "garbage",
            "summary/summary_date_check_enabled": "true",
            "summary/visit_summary_allowlist_enabled": "true",
        }
    )._load_parameters_core()
    assert out["SUMMARY_DATE_CHECK_ENABLED"] == "true"
    assert out["VISIT_SUMMARY_ALLOWLIST_ENABLED"] == "true"
    assert "EVIDENCE_FALLBACK_ENABLED" not in out


def test_sanitize_never_raises():
    assert sanitize_partx_value("EVIDENCE_FALLBACK_ENABLED", None) is None
    assert sanitize_partx_value("EXTRACTION_CALL_TIMEOUT_S", object()) is None
    assert sanitize_partx_value("NOT_A_PARTX_VAR", "true") is None


def test_sanitized_values_parse_in_settings(monkeypatch):
    monkeypatch.setenv("SUMMARY_LABEL_FIXES_ENABLED", sanitize_partx_value("SUMMARY_LABEL_FIXES_ENABLED", "Yes"))
    monkeypatch.setenv("EXTRACTION_CALL_TIMEOUT_S", sanitize_partx_value("EXTRACTION_CALL_TIMEOUT_S", "90"))
    s = Settings()
    assert s.SUMMARY_LABEL_FIXES_ENABLED is True
    assert s.EXTRACTION_CALL_TIMEOUT_S == 90.0


def test_startup_log_line_all_off(caplog):
    with caplog.at_level(logging.INFO):
        log_partx_flags_configuration()
    assert "partx_flags enabled=[] extraction_call_timeout_s=45.0" in caplog.text


def test_startup_log_line_lists_enabled_flags(monkeypatch, caplog):
    monkeypatch.setenv("CDA_COMPACT_EXTRACTION_ENABLED", "true")
    monkeypatch.setenv("SUMMARY_DATE_CHECK_ENABLED", "true")
    monkeypatch.setenv("EXTRACTION_CALL_TIMEOUT_S", "90")
    reset_settings()
    with caplog.at_level(logging.INFO):
        log_partx_flags_configuration()
    assert (
        "partx_flags enabled=[CDA_COMPACT_EXTRACTION_ENABLED,SUMMARY_DATE_CHECK_ENABLED] "
        "extraction_call_timeout_s=90.0"
    ) in caplog.text
