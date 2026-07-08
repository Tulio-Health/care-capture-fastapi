from .health import router as health_router
from .root import router as root_router
from .care_capture import router as care_capture_router
from .users import router as users_router
from .ai_chat import router as ai_chat_router
from .schedule_visit import router as schedule_visit_router
from .translation import router as translation_router
from .auth_test import router as auth_test_router
from .document_type_inference import router as document_type_inference_router

__all__ = ["health_router", "root_router", "care_capture_router", "users_router", "ai_chat_router", "schedule_visit_router", "translation_router", "auth_test_router", "document_type_inference_router"]

