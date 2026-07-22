"""
Enterprise router aggregator.

Registers sub-routers for each enterprise endpoint group.
"""

from fastapi import APIRouter

from .chat import router as chat_router
from .profiles import router as profiles_router
from .signals import router as signals_router

enterprise_router = APIRouter(prefix="/enterprise", tags=["enterprise"])

# Sub-routers registered in route order
enterprise_router.include_router(signals_router)
enterprise_router.include_router(profiles_router)
enterprise_router.include_router(chat_router)

__all__ = ["enterprise_router"]
