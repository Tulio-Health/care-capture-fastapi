"""Execution contract shared by mock and live application regression adapters."""
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class ExecutionContext:
    mode: str  # mock or live; both exercise the same actual FastAPI implementation.
    ai: Any = None  # RegressionAI in live mode, None in mock mode.
    persistence_mode: str = 'memory'

    @property
    def uses_live_ai(self):
        return self.mode == 'live'
