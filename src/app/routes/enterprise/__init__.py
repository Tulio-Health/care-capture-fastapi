"""
Enterprise router aggregator.

Registers sub-routers for each enterprise endpoint group.
The chat sub-router (Plan 02-04) is still behind a try/except guard because
chat.py does not exist until that plan runs.
"""

from fastapi import APIRouter

from .profiles import router as profiles_router
from .signals import router as signals_router

enterprise_router = APIRouter(prefix="/enterprise", tags=["enterprise"])

# Sub-routers registered in route order
enterprise_router.include_router(signals_router)
enterprise_router.include_router(profiles_router)

# Optional sub-router — added by Plan 02-04; guarded so this file remains
# importable while that plan has not yet run.
try:
    from .chat import router as chat_router  # noqa: F401 (Plan 02-04)
    enterprise_router.include_router(chat_router)
except ImportError:
    pass

__all__ = ["enterprise_router"]
