---
generated: 2026-04-03
focus: quality
---

# Coding Conventions

## Overview

This FastAPI application follows Python conventions with some inconsistencies between older and newer code. It uses black/isort for formatting, flake8 for linting, and mypy for type checking (all configured but enforcement varies). The codebase mixes relative and absolute imports, and logging patterns vary between `logger` and `print()` statements.

## Naming Patterns

**Files:**
- Use `snake_case.py` for all Python files
- Route files are named after feature domains: `ai_chat.py`, `care_capture.py`, `schedule_visit.py`
- Chain modules use `chain.py` inside feature directories: `src/app/chains/transcript_summarization/chain.py`
- Constants files use `constants.py` inside feature directories
- Model files match the feature: `src/app/models/ai_chat.py`, `src/app/models/transcript_summarization.py`

**Classes:**
- Use `PascalCase` for all classes
- Service classes end with `Service`: `TranscriptSummarizationService`, `FhirAnalysisService`
- Repository classes end with `Repository`: `UsersRepository`, `ConversationSummariesRepository`
- Chain classes end with `Chain`: `IntendIdentifierChain`, `TranscriptSummarizationChain`
- Request/response models end with `Request`/`Response`: `AiChatRequest`, `TranscriptSummarizationResponse`
- SQLAlchemy entities use plural nouns: `Users`, `ChatbotConversation`
- Pydantic schemas use `{Entity}Base`, `{Entity}Create`, `{Entity}Update`, `{Entity}InDB` pattern

**Functions:**
- Use `snake_case` for all functions
- Route handlers use descriptive verbs: `transcript_summarize_text()`, `analyze_fhir_resources()`
- Private methods prefixed with underscore: `_generate_summary()`, `_prepare_summary_data()`
- Getters use `get_` prefix: `get_settings()`, `get_db()`, `get_logger()`

**Variables:**
- Use `snake_case` for local variables
- Use `UPPER_SNAKE_CASE` for module-level constants
- Use `_engine`, `_model` for private module/instance variables with lazy initialization

## Code Style

**Formatting:**
- Tool: `black` (configured in `pyproject.toml`)
- Line length: 88 characters
- Target: Python 3.12

**Import Sorting:**
- Tool: `isort` with `profile = "black"` and `multi_line_output = 3`

**Linting:**
- Tool: `flake8` (in dev dependencies, no config file found)

**Type Checking:**
- Tool: `mypy` (configured in `pyproject.toml`)
- Settings: `disallow_untyped_defs = true`, `warn_return_any = true`
- In practice, type hints are used inconsistently (see Type Hints section)

## Import Organization

**Standard pattern observed across files:**

1. Standard library imports
2. Third-party imports (FastAPI, SQLAlchemy, Pydantic, LangChain)
3. Local application imports

**Two import styles coexist:**

Absolute imports (used in routes and chains):
```python
from src.app.chains.transcript_summarization.chain import TranscriptSummarizationChain
from src.app.common.logging import get_logger
from src.app.core import get_settings
```

Relative imports (used in main.py and some modules):
```python
from ..common.logging import get_logger
from ..db.config.database import get_db
from ...core.settings import get_settings
```

**Prescriptive rule:** Use absolute imports (`from src.app.…`) in route handlers and chain modules. Use relative imports only within tightly coupled sub-packages (e.g., within `common/`).

**Path Aliases:** None. No `sys.path` manipulation in main codebase (only in evals).

**Barrel files (`__init__.py`):**
- Used extensively to re-export public APIs
- Routes: `src/app/routes/__init__.py` re-exports all routers
- Middleware: `src/app/common/middleware/__init__.py` re-exports middleware classes
- Scoring: `evals/scoring/__init__.py` re-exports all scoring functions
- Pattern: `from .module import SomeClass` with `__all__` list

## Route Definition Patterns

**Router creation:**
```python
router = APIRouter(
    prefix="/care-capture/schedule-visit",
    tags=["care-capture-schedule-visit"]
)
```

**Route handler pattern (well-structured routes like `care_capture.py`):**
```python
@router.post(
    "/transcript-summarization",
    response_model=ConversationSummary,
    summary="Provider Visit Summarization",
    description="...",
    responses={200: {...}, 400: {...}, 500: {...}},
)
async def transcript_summarize_text(
    request: TranscriptSummarizationRequest, db: AsyncSession = Depends(get_db)
) -> ConversationSummary:
    try:
        service = TranscriptSummarizationService(db)
        return await service.summarize_transcript(request)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process summary: {str(e)}")
```

**Route prefix convention:** All routes use `/care-capture/` prefix. Sub-features get nested prefixes: `/care-capture/ai-chat/`, `/care-capture/schedule-visit/`.

## Service/Repository Pattern

**Service layer (`src/app/services/`):**
- Services receive `AsyncSession` via constructor (not via DI)
- Services create repository instances internally
- Services contain business logic and orchestrate chain calls
- Base class exists at `src/app/services/base.py` but is not consistently used

```python
class TranscriptSummarizationService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.summaries_repo = ConversationSummariesRepository(db)
        self.logger = logger
```

**Repository layer (`src/app/db/objects/repositories/`):**
- Repositories receive `AsyncSession` via constructor
- Repositories handle raw database operations (CRUD)
- Methods are async and use SQLAlchemy select/insert patterns

```python
class UsersRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, user_id: str) -> Optional[Users]:
        result = await self.session.execute(
            select(Users).where(Users.id == user_id)
        )
        return result.scalar_one_or_none()
```

**Chain layer (`src/app/chains/`):**
- Chains encapsulate LLM interactions (LangChain / pydantic-ai)
- Chains use lazy model initialization via `@property`
- Chains use `ChatPromptTemplate` from LangChain
- Constants (system prompts) live in `constants.py` alongside `chain.py`

```python
class IntendIdentifierChain:
    def __init__(self):
        self._model = None
        self.prompt = ChatPromptTemplate.from_messages([...])

    @property
    def model(self):
        if self._model is None:
            self._model = get_default_chat_model()
        return self._model
```

## Dependency Injection

**Database session injection:** Via FastAPI `Depends()` in route handlers, then passed to services/repositories manually.

```python
async def transcript_summarize_text(
    request: TranscriptSummarizationRequest, db: AsyncSession = Depends(get_db)
) -> ConversationSummary:
    service = TranscriptSummarizationService(db)
```

**Settings injection:** Via `get_settings()` singleton (cached with `@lru_cache`). Defined in `src/app/core/settings.py`.

**Redis client:** Global singleton at `src/app/cache/redis.py`, imported directly (not injected).

## Error Handling

**Exception hierarchy:**
- `CareCaptureError(HTTPException)` - base for domain errors (`src/app/common/exception/base.py`)
- `HealthCheckError(HTTPException)` - health check failures
- `BusinessLogicError(Exception)` - business rule violations (`src/app/common/error_models.py`)
- `ExternalServiceError(Exception)` - third-party service failures (`src/app/common/error_models.py`)

**Standardized error response model:**
```python
class APIErrorResponse(BaseModel):
    error: bool = True
    error_type: ErrorType  # Enum: validation_error, business_logic_error, etc.
    message: str
    details: Optional[str] = None
    request_id: Optional[str] = None
```

**Route-level error handling pattern:**
```python
try:
    service = SomeService(db)
    return await service.do_work(request)
except ValueError as e:
    raise HTTPException(status_code=400, detail=str(e))
except HTTPException:
    raise  # Re-raise HTTP exceptions
except Exception as e:
    logger.error(f"...: {str(e)}", exc_info=True)
    raise HTTPException(status_code=500, detail=f"Failed to ...: {str(e)}")
```

**Global exception handlers:** Registered in `src/app/common/exception_handlers.py` via `register_exception_handlers(app)`. Handles `RequestValidationError`, `BusinessLogicError`, `ExternalServiceError`, `HTTPException`, and generic `Exception`.

## Logging

**Framework:** Python `logging` module with custom configuration at `src/app/common/logging/logging.py`.

**Logger initialization:**
```python
from src.app.common.logging import get_logger
logger = get_logger(__name__)
```

**Log format:** `%(asctime)s - %(name)s - %(levelname)s - %(message)s`
- Optional JSON structured logging via `JSONFormatter`
- Optional debug format includes `%(pathname)s:%(funcName)s:%(lineno)d`

**Logging conventions:**
- Use `logger.info()` for operation start/completion
- Use `logger.debug()` for detailed data
- Use `logger.error()` with `exc_info=True` for exceptions
- Use `logger.warning()` for degraded states

**Known issue:** `print()` statements are used alongside `logger` in 10 files (74 occurrences total), especially in `src/app/routes/chain_testing.py` (50 occurrences), `src/app/chains/ai_chat_intents/` (14 occurrences), and `src/app/routes/ai_chat.py` (3 occurrences). New code should use `logger` exclusively.

## Type Hints

**Settings/config:** Fully typed with Pydantic `Field()` validators (`src/app/core/settings.py`).

**Pydantic models:** Consistently typed (`src/app/models/`, `src/app/db/objects/schemas/`).

**Repository methods:** Return types present (`-> Optional[Users]`), parameter types present.

**Route handlers:** Return type annotations present on well-structured routes, missing on some older ones.

**Chain methods:** Type hints present on public methods, less consistent on private helpers.

**Prescriptive rule:** Always add return type annotations. Use `Optional[X]` for nullable returns. Use `list[str]` (lowercase) for Python 3.12+ style.

## Docstrings

**Convention:** Google-style docstrings with `Args:`, `Returns:`, `Raises:` sections.

**Where used consistently:**
- Service methods (`src/app/services/summarization/transcript_summarization.py`)
- Chain classes and methods (`src/app/chains/ai_chat_intents/intend_identifier/chain.py`)
- Module-level docstrings for chain modules

**Where missing:**
- Most repository methods
- Some route handlers
- Helper/utility functions

**Prescriptive rule:** Add docstrings to all public methods. Use Google-style format:
```python
def method(self, param: str) -> Result:
    """
    Brief description.
    
    Args:
        param: Description of param
    
    Returns:
        Description of return value
    
    Raises:
        ValueError: When validation fails
    """
```

## Pydantic Model Conventions

**Request models** (`src/app/models/`):
```python
class AiChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None
    user_id: Optional[str] = None
```

**Database entity schemas** (`src/app/db/objects/schemas/`):
- `{Entity}Base` - shared fields
- `{Entity}Create(Base)` - creation payload
- `{Entity}Update(BaseModel)` - update payload (all fields optional)
- `{Entity}InDB(Base)` - database representation with `Config: from_attributes = True`

**SQLAlchemy entities** (`src/app/db/objects/entities/`):
- Use `Column()` with explicit types
- UUID primary keys with `uuid4` default
- `created_at`/`updated_at` timestamps with `func.now()`

## Async Patterns

**Route handlers:** Always `async def`.
**Service methods:** Always `async def` when they involve DB or LLM calls.
**Repository methods:** Always `async def` (using `AsyncSession`).
**Chain methods:** Mixed - some sync (LangChain invoke), some async (pydantic-ai).

**Database sessions:** Use `async with` context manager via `get_db()` generator.

## Key Observations

1. **Import style inconsistency**: Absolute and relative imports are mixed. Standardize on absolute imports for cross-package references.

2. **print() vs logger**: 74 `print()` calls across 10 files. These should be replaced with proper logger calls.

3. **Commented-out code**: Large blocks of commented-out code in `src/app/routes/care_capture.py` (lines 203-303). Should be removed or tracked as issues.

4. **Hardcoded values in comments**: `src/app/routes/ai_chat.py` has commented-out hardcoded user IDs (lines 35-37).

5. **Error handling inconsistency**: Some routes catch specific exceptions and re-raise as HTTPException, while others let global handlers catch them. The newer pattern (letting `BusinessLogicError`/`ExternalServiceError` propagate to global handlers) is preferred.

6. **Two exception systems**: Legacy `CareCaptureError(HTTPException)` hierarchy coexists with newer `BusinessLogicError`/`ExternalServiceError` system. New code should use the newer system.
