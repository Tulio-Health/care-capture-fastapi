"""
Enterprise router aggregator.

Registers sub-routers for each enterprise endpoint group.
Sub-routers for Plans 02-03 (profiles) and 02-04 (chat) are imported with
try/except guards so this package is importable before those plans are executed.
"""

from fastapi import APIRouter

from .signals import router as signals_router

enterprise_router = APIRouter(prefix="/enterprise", tags=["enterprise"])

# Always-present sub-router (Plan 02-02)
enterprise_router.include_router(signals_router)

# Optional sub-routers — added by later plans; guarded so this file remains
# importable while Plans 02-03 and 02-04 have not yet run.
try:
    from .profiles import router as profiles_router  # noqa: F401 (Plan 02-03)
    enterprise_router.include_router(profiles_router)
except ImportError:
    pass

try:
    from .chat import router as chat_router  # noqa: F401 (Plan 02-04)
    enterprise_router.include_router(chat_router)
except ImportError:
    pass

__all__ = ["enterprise_router"]
