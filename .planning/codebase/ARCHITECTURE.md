---
generated: 2026-04-03
focus: arch
---

# Architecture

## Overview

Care Capture FastAPI is a Python AI service that sits behind a Node.js API in a three-service architecture (Node API, EMR Connector, FastAPI). It handles two primary domains: (1) clinical document summarization (transcripts, FHIR resources, document attachments) and (2) an AI chatbot for patient-facing health queries. All AI operations use OpenAI GPT-4o-mini via LangChain. The Node API acts as the gateway, forwarding requests to this service and sharing state through a common Redis cache and PostgreSQL database.

## Pattern Overview

**Overall:** Layered architecture with Route -> Service -> Chain (AI) separation

**Key Characteristics:**
- Routes handle HTTP concerns and delegate to services
- Services contain business logic, database access, and orchestration
- Chains encapsulate LangChain prompt + model + parser pipelines
- Configuration loaded from AWS SSM Parameter Store at startup (before any imports)
- Redis used as a shared cache layer between Node API and FastAPI
- Database shared with Node API (same PostgreSQL instance)

## System Context

```
[Mobile/Web App] --> [Node API (main gateway)]
                          |
                          |--> [FastAPI (this service)] -- AI summarization + chatbot
                          |         |
                          |         |--> OpenAI GPT-4o-mini (LangChain)
                          |         |--> PostgreSQL (shared DB)
                          |         |--> Redis (shared cache)
                          |         |--> S3 (document storage)
                          |         |--> LangSmith (tracing)
                          |
                          |--> [EMR Connector] -- FHIR/EHR integration
```

## Layers

**Routes Layer:**
- Purpose: HTTP endpoint definitions, request validation, error mapping
- Location: `src/app/routes/`
- Contains: FastAPI router definitions with Pydantic request/response models
- Depends on: Services, Models, Database session (`get_db`)
- Used by: External callers (Node API)
- Key files:
  - `src/app/routes/care_capture.py` - Summarization endpoints (transcript, FHIR, attachment, comprehensive)
  - `src/app/routes/ai_chat.py` - Chatbot endpoint with intent routing
  - `src/app/routes/schedule_visit.py` - Visit scheduling
  - `src/app/routes/translation.py` - Medical translation
  - `src/app/routes/users.py` - User management
  - `src/app/routes/health.py` - Health check
  - `src/app/routes/version.py` - Version info

**Services Layer:**
- Purpose: Business logic, data access orchestration, AI chain invocation
- Location: `src/app/services/`
- Contains: Service classes that coordinate between repositories and AI chains
- Depends on: Chains, Repositories, Models
- Used by: Routes
- Key files:
  - `src/app/services/summarization/transcript_summarization.py` - Transcript -> AI summary -> DB
  - `src/app/services/summarization/attachment_summarization.py` - S3 download -> text extraction -> AI analysis -> DB
  - `src/app/services/summarization/fhir_analysis.py` - FHIR resources -> AI analysis -> DB
  - `src/app/services/summarization/comprehensive_summarization.py` - Parallel orchestrator for transcript + attachment/FHIR
  - `src/app/services/health_insights/health_insight_generator.py` - Scheduled batch job for health insights
  - `src/app/services/translation/translation_service.py` - Medical text translation
  - `src/app/services/document_extraction.py` - PDF/DOCX/TXT text extraction

**Chains Layer (AI):**
- Purpose: LangChain prompt templates + model + output parsers
- Location: `src/app/chains/`
- Contains: Chain classes that wrap LLM invocations with structured I/O
- Depends on: LLM factory, LangSmith tracing, Pydantic models
- Used by: Services
- Pattern: Each chain class follows `prompt | model | parser` composition
- Key files:
  - `src/app/chains/transcript_summarization/chain.py` - Medical transcript summarization
  - `src/app/chains/attachment_summarization/chain.py` - Document attachment analysis (map-reduce)
  - `src/app/chains/fhir_analysis/chain.py` - FHIR resource analysis
  - `src/app/chains/health_insights/chain.py` - Health insight extraction
  - `src/app/chains/translation/chain.py` - Medical translation
  - `src/app/chains/ai_chat_intents/` - Chatbot intent system (see below)

**Data Layer:**
- Purpose: Database models, entities, repositories
- Location: `src/app/db/`
- Contains: SQLAlchemy models, async repository classes
- Depends on: SQLAlchemy, AsyncSession
- Used by: Services
- Key files:
  - `src/app/db/config/database.py` - Async engine creation, session factory, `get_db` dependency
  - `src/app/db/models/` - SQLAlchemy ORM models (shared with Node API schema)
  - `src/app/db/objects/repositories/` - Repository pattern for CRUD operations
  - `src/app/db/objects/entities/` - Entity definitions for FastAPI-owned tables

## Data Flow

**Summarization Request Flow (comprehensive-summary endpoint):**

1. Node API sends POST to `/care-capture/comprehensive-summary` with appointment_id, user_id, transcripts
2. Route handler creates `ComprehensiveSummarizationService` with DB session
3. Service checks for existing summaries in DB (cache-like behavior)
4. If missing, builds parallel tasks: transcript summarization + attachment/FHIR analysis
5. Each task gets its own DB session (from session factory)
6. Transcript task: `TranscriptSummarizationService` -> `TranscriptSummarizationChain` -> OpenAI -> parse response -> upsert DB
7. Attachment task: `AttachmentSummarizationService` -> fetch FHIR DocumentReferences -> download from S3 -> extract text -> `AttachmentSummarizationChain` -> OpenAI -> upsert DB
8. Results merged, partial success supported (one can fail while other succeeds)
9. Response returned with both transcript and FHIR/attachment summaries

**Chatbot Request Flow:**

1. Node API sends POST to `/care-capture/ai-chat/` with message, user_id, conversation_id
2. Route loads context from Redis:
   - User profile + health insights (FastAPI-managed cache, populated from DB)
   - Enriched summaries (Node API-managed cache, populated by Node API)
   - Conversation history (Node API-managed, stored as Redis list via lpush)
   - Conversation context (FastAPI-managed, for follow-up resolution)
3. `IntendIdentifierChain` classifies intent via LLM (past_visits, health_insights, upcoming_visits, medical_inquiry, not_valid, end_conversation)
4. `IntentRouter` dispatches to appropriate handler chain
5. Handler chain (e.g., `PastVisitIntentChain`) uses two-stage LLM:
   - Stage 1: Extract structured query params from natural language
   - Stage 2: Filter enriched summaries, generate response
6. Conversation context saved to Redis for follow-up detection
7. Response returned with intent type and AI-generated content

**Health Insights Scheduled Job:**

1. APScheduler triggers `generate_health_insight()` at configured interval
2. `HealthInsightGenerator` fetches new conversation summaries since last run
3. Groups summaries by user, runs `GenerateHealthInsightsChain` per user
4. Stores extracted health insights in `patient_health_insights` table
5. Logs job execution to `scheduler_job_execution_logs` table

## AI Pipeline Architecture

**Chain Pattern:**
All chains follow LangChain's composition pattern:
```python
chain = prompt_template | chat_model | output_parser
result = chain.invoke({"key": "value"})
```

**LLM Configuration:**
- Factory: `src/app/common/llm_factory.py`
- Default model: GPT-4o-mini, temperature 0.2
- Creative model: GPT-4o-mini, temperature 0.7
- PydanticAI model: Also available for newer chains
- Models are cached via `@lru_cache` to avoid re-initialization
- API key loaded from SSM at startup

**Tracing:**
- LangSmith integration via `src/app/core/langsmith_trace.py`
- Callbacks passed to chain invocations for observability
- `@traceable` decorator used on key methods

**Chatbot Intent System:**
```
src/app/chains/ai_chat_intents/
  intend_identifier/     # Intent classification
    chain.py             # LLM-based intent detection
    router.py            # Maps intent -> handler chain
    models.py            # RouterOptions enum
  past_visit_intent/     # Two-stage: query extraction + response generation
  health_insights_intent/
  upcoming_visit_intent/
  medical_inquiry_intent/
  not_valid_intent/
  not_found_intent/
```

## Configuration Management

**Startup Sequence:**
1. `src/app/main.py` imports trigger `configure_logging()` first
2. `initialize_environment_sync()` called at module level (before route imports)
3. Loads `.env.{APP_ENV}` file
4. `SSMParameterLoader` connects to AWS SSM, fetches all params under `/tuliohealth/{env}/`
5. Maps SSM paths to env vars (e.g., `database/host` -> `DB_HOST`)
6. Overrides Redis to localhost for local development
7. `get_settings()` (cached) reads from environment, used throughout app

**Key Config Files:**
- `src/app/config/ssm_loader.py` - SSM Parameter Store integration with path mappings
- `src/app/config/environment.py` - Environment detection and SSM initialization
- `src/app/core/settings.py` - Pydantic `BaseSettings` with validation
- `src/app/config/configuration_summary.py` - Debug logging of loaded config

## Authentication

**Clerk JWT Middleware** (`src/app/common/middleware/clerk_auth.py`):
- Validates `x-clerk-jwt` header on all non-excluded paths
- Decodes RS256 JWT using Clerk public key (from SSM)
- Attaches user info to `request.state.user`
- Supports service-to-service auth via `x-internal-service-key` header
- Excluded paths: `/`, `/health`, `/api/docs`, playground endpoints
- When auth is disabled (no key configured), sets dev user and proceeds

## Error Handling

**Strategy:** Layered exception handling with structured error responses

**Global Exception Handlers** (`src/app/common/exception_handlers.py`):
- `RequestValidationError` -> 422 with field-level details
- `BusinessLogicError` -> 400 with context
- `ExternalServiceError` -> 503 (e.g., OpenAI failures)
- `HTTPException` -> passthrough with request_id
- `Exception` (catch-all) -> 500 with sanitized message

**Legacy Handlers:**
- `HealthCheckError` and `CareCaptureError` still registered alongside new handlers

**Route-Level Pattern:**
Routes typically catch `ValueError` -> 400, `HTTPException` -> re-raise, `Exception` -> 500.

**Service-Level Pattern:**
Services log errors with context and re-raise. The comprehensive summarization service supports partial success via `asyncio.gather(return_exceptions=True)`.

## Cross-Cutting Concerns

**Logging:**
- Custom logger via `src/app/common/logging/logging.py`
- `get_logger(__name__)` used throughout
- Request logging middleware logs method, path, status, timing

**Middleware Stack** (order matters):
1. CORS (`src/app/common/middleware/cors.py`)
2. Request Logging (`src/app/common/middleware/request_logging.py`)
3. Clerk Auth (`src/app/common/middleware/clerk_auth.py`)

**Caching:**
- Redis singleton via `src/app/cache/redis.py`
- Shared cache keys defined in `src/app/common/constants/cache_keys.py`
- Node API writes enriched summaries and conversation history to Redis
- FastAPI reads from Node API cache and manages its own profile/insights cache

**Scheduling:**
- APScheduler (AsyncIOScheduler) initialized in `src/app/core/scheduler.py`
- Currently runs health insight generation on interval
- Job execution logged to database

**Database:**
- Async SQLAlchemy with asyncpg driver
- NullPool for local dev, AsyncAdaptedQueuePool for AWS App Runner
- Lazy engine initialization (created on first use after SSM loading)
- Session-per-request via `get_db()` FastAPI dependency

## Key Observations

- The Node API acts as the primary gateway; this service is never called directly by clients
- Redis serves as a critical shared state layer between Node API and FastAPI -- cache key formats must stay synchronized
- The comprehensive summarization endpoint is the most complex, orchestrating parallel tasks with partial success, timeouts, and existing summary detection
- The chatbot route (`ai_chat.py`) contains significant inline logic rather than delegating to a service class -- it directly manages Redis reads, context assembly, and intent routing
- LLM model instances are cached globally via `@lru_cache`, meaning temperature/model changes require cache invalidation
- The database schema is owned by the Node API; FastAPI reads/writes to shared tables
