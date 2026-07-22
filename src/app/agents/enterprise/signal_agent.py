"""
PydanticAI signal agent for enterprise clinical-change detection.

Exposes:
  - ImportantChanges: Pydantic model with 8 boolean clinical-change flags
    (field names match enterprise_patient_signals DB column names exactly).
  - get_signal_agent(): returns the module-level singleton Agent[ImportantChanges];
    the model is resolved lazily on first call to avoid SSM/settings access at
    import time (important for testability and startup order).

Usage in route handlers:
    result = await get_signal_agent().run(prompt_str)
    signals: ImportantChanges = result.output  # NOT result.data
"""

from pydantic import BaseModel
from pydantic_ai import Agent

from src.app.common.constants.llm import LLM_MODEL


class ImportantChanges(BaseModel):
    """
    8 clinical-change signal flags extracted from FHIR resources.

    Field names are identical to the DB column names in enterprise_patient_signals
    (enforced by the Phase 1 migration).
    """

    hospitalization: bool
    er_visit: bool
    new_specialist_referral: bool
    medication_change: bool
    new_diagnosis: bool
    functional_decline: bool
    care_setting_change: bool
    follow_up_required: bool


# ---------------------------------------------------------------------------
# Module-level singleton — lazy-initialised to defer SSM/settings access
# until first use. The variable is set once and reused on all subsequent calls.
# ---------------------------------------------------------------------------

_signal_agent: Agent | None = None

_SIGNAL_AGENT_INSTRUCTIONS = (
    "You are a medical signal detector analyzing FHIR healthcare records. "
    "Your task is to identify clinically important changes for a patient "
    "based on the FHIR resources provided. "
    "For each signal, set the boolean to true only if clear evidence exists "
    "in the provided FHIR data. "
    "\n\n"
    "Signal definitions:\n"
    "- hospitalization: set to true if ANY Encounter resource has class code "
    "'IMP' (inpatient) or 'EMER' (emergency) with period.start date within "
    "30 days of today's date.\n"
    "- er_visit: set to true if ANY Encounter has class code 'EMER' (emergency).\n"
    "- new_specialist_referral: set to true if any referral to a specialist "
    "appears in Encounter or Procedure resources.\n"
    "- medication_change: set to true if any MedicationRequest shows a new, "
    "changed, or discontinued medication.\n"
    "- new_diagnosis: set to true if any Condition resource has recordedDate "
    "within 90 days of today.\n"
    "- functional_decline: set to true if any Encounter or Condition references "
    "decline in ADLs, mobility, or cognitive function.\n"
    "- care_setting_change: set to true if the patient moved between care settings "
    "(e.g., home to hospital, hospital to SNF).\n"
    "- follow_up_required: set to true if any Encounter or Procedure notes a "
    "required follow-up appointment.\n"
    "\n"
    "Analyze all provided resources carefully. "
    "When evidence is ambiguous, default to false."
)


def get_signal_agent() -> Agent:
    """
    Return the module-level signal_agent singleton, creating it on first call.

    Defers get_pydantic_ai_model() (and therefore get_settings() / SSM access)
    until the first request — not at import time.  This keeps the module safely
    importable during tests and at application startup before SSM parameters
    are loaded.
    """
    global _signal_agent
    if _signal_agent is None:
        from src.app.common.llm_factory import get_pydantic_ai_model

        _signal_agent = Agent(
            get_pydantic_ai_model(LLM_MODEL.GPT_4O_MINI),
            output_type=ImportantChanges,
            instructions=_SIGNAL_AGENT_INSTRUCTIONS,
        )
    return _signal_agent


# Convenience alias so callers can do:
#   from src.app.agents.enterprise.signal_agent import signal_agent
# and call  await signal_agent.run(...)  without knowing about lazy init.
# The first attribute access triggers lazy creation.
class _LazyAgent:
    """Proxy that creates the real Agent on first attribute access."""

    def __getattr__(self, name: str):
        return getattr(get_signal_agent(), name)

    def __repr__(self) -> str:  # pragma: no cover
        return repr(get_signal_agent())


signal_agent = _LazyAgent()
