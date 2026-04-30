---
generated: 2026-04-03
focus: arch
---

# Codebase Structure

## Overview

The project follows a `src/app/` layout with clear separation between routes, services, chains (AI), database, and common utilities. The main application is in `src/app/`, with evaluation tooling in `evals/` and deployment configs in `.github/workflows/`.

## Directory Layout

```
care-capture-fastapi/
├── src/
│   └── app/
│       ├── main.py                    # FastAPI app factory, lifespan, middleware setup
│       ├── version.py                 # Version string
│       ├── routes/                    # HTTP endpoints (FastAPI routers)
│       ├── services/                  # Business logic layer
│       │   ├── summarization/         # All summarization services
│       │   ├── health_insights/       # Health insight generation (scheduled)
│       │   ├── translation/           # Medical translation
│       │   ├── base.py                # BaseService generic class
│       │   └── document_extraction.py # PDF/DOCX/TXT text extraction
│       ├── chains/                    # LangChain AI pipelines
│       │   ├── ai_chat_intents/       # Chatbot intent system
│       │   ├── transcript_summarization/
│       │   ├── attachment_summarization/
│       │   ├── fhir_analysis/
│       │   ├── health_insights/
│       │   ├── schedule_visit/
│       │   ├── translation/
│       │   └── chat.py                # Legacy chat chain
│       ├── models/                    # Pydantic request/response models
│       ├── schemas/                   # Pydantic base schemas
│       ├── db/                        # Database layer
│       │   ├── config/database.py     # Engine, session factory, get_db
│       │   ├── models/                # SQLAlchemy ORM models (shared DB)
│       │   └── objects/               # Entities + Repositories
│       ├── config/                    # SSM loader, environment setup
│       ├── core/                      # Settings, scheduler, tracing
│       ├── common/                    # Shared utilities
│       │   ├── auth/                  # Auth helpers
│       │   ├── constants/             # Cache keys, LLM constants, scheduler
│       │   ├── exception/             # Custom exception classes
│       │   ├── logging/               # Logger configuration
│       │   ├── middleware/            # CORS, Clerk auth, rate limiter, request logging
│       │   ├── scheduler/             # Job execution DB logger
│       │   ├── llm_factory.py         # LLM model factory (cached)
│       │   ├── error_handlers.py      # Error response builders
│       │   ├── error_models.py        # BusinessLogicError, ExternalServiceError
│       │   └── exception_handlers.py  # Global FastAPI exception handler registration
│       ├── prompts/                   # Prompt base classes
│       ├── constants/                 # App-level constants (scheduler config)
│       ├── cache/                     # Redis client singleton
│       ├── health/                    # Startup health checks
│       ├── utils/                     # S3 client, other utilities
│       └── tests/                     # Test files
│           ├── unit/
│           └── integration/
├── evals/                             # AI prompt evaluation framework
│   ├── scoring/                       # Evaluation scoring modules
│   ├── fixtures/                      # Test documents and ground truth
│   ├── prompts/                       # Versioned prompt snapshots
│   └── results/                       # Evaluation run results
├── scripts/                           # Utility scripts
├── docs/                              # Documentation
├── .github/workflows/                 # CI/CD (dev-deploy.yml, prod-deploy.yml)
├── pyproject.toml                     # Project config (uv/hatch)
├── uv.lock                            # Dependency lockfile
├── CLAUDE.md                          # Project instructions for Claude
├── Dockerfile                         # Container build
└── .env.development                   # Local dev environment (secrets via SSM)
```

## Directory Purposes

**`src/app/routes/`**
- Purpose: FastAPI router definitions -- one file per feature domain
- Contains: Router instances with endpoint decorators, request validation, error mapping
- Key files:
  - `__init__.py` - Exports all routers
  - `care_capture.py` - Core summarization endpoints: `/care-capture/transcript-summarization`, `/care-capture/fhir-analysis`, `/care-capture/attachment-summary`, `/care-capture/comprehensive-summary`, `/care-capture/playground-summarization`
  - `ai_chat.py` - Chatbot endpoint: `/care-capture/ai-chat/`
  - `schedule_visit.py` - Visit scheduling
  - `translation.py` - Medical translation
  - `users.py` - User management
  - `health.py` - Health check endpoint
  - `version.py` - Version info
  - `auth_test.py` - Auth testing endpoint
  - `pull_db_context.py` - Helper functions for chatbot context (not a router)
  - `playground_attachment.py` - Dev-only attachment testing

**`src/app/services/`**
- Purpose: Business logic layer between routes and chains
- Contains: Service classes that coordinate DB operations and AI invocations
- Key files:
  - `summarization/transcript_summarization.py` - `TranscriptSummarizationService`
  - `summarization/attachment_summarization.py` - `AttachmentSummarizationService`
  - `summarization/fhir_analysis.py` - `FhirAnalysisService`
  - `summarization/comprehensive_summarization.py` - `ComprehensiveSummarizationService` (parallel orchestrator)
  - `summarization/playground_summarization.py` - `PlaygroundSummarizationService` (no DB)
  - `health_insights/health_insight_generator.py` - `HealthInsightGenerator` (scheduled batch)
  - `translation/translation_service.py` - Translation service
  - `document_extraction.py` - `DocumentTextExtractor` (PDF, DOCX, TXT)
  - `base.py` - `BaseService` generic class (not widely used)

**`src/app/chains/`**
- Purpose: LangChain AI pipeline definitions (prompt + model + parser)
- Contains: Chain classes, each with a `constants.py` for prompts
- Pattern: Each subdirectory has `chain.py` and `constants.py` (prompt text)
- Key subdirectories:
  - `transcript_summarization/` - Medical transcript -> structured summary
  - `attachment_summarization/` - Document text -> clinical insights (map-reduce)
  - `fhir_analysis/` - FHIR resources -> clinical analysis
  - `health_insights/` - Summaries -> health insight extraction
  - `translation/` - Medical text translation
  - `schedule_visit/` - Visit scheduling assistance
  - `ai_chat_intents/` - Intent-based chatbot system:
    - `intend_identifier/chain.py` - Intent classification LLM
    - `intend_identifier/router.py` - Intent -> handler dispatch
    - `intend_identifier/models.py` - `RouterOptions` enum
    - `past_visit_intent/` - Past visit query (two-stage: extraction + response)
    - `health_insights_intent/` - Health insights lookup
    - `upcoming_visit_intent/` - Upcoming appointment queries
    - `medical_inquiry_intent/` - General medical questions
    - `not_valid_intent/` - Invalid query handling
    - `not_found_intent/` - No data found response

**`src/app/models/`**
- Purpose: Pydantic models for request/response validation
- Contains: Input/output models for each feature
- Key files:
  - `transcript_summarization.py` - `TranscriptSummarizationRequest`, `TranscriptSummarizationResponse`
  - `attachment_summarization.py` - `AttachmentSummarizationRequest`, `DocumentAttachment`
  - `comprehensive_summarization.py` - `ComprehensiveSummarizationRequest`, `ComprehensiveSummarizationResponse`
  - `fhir_analysis.py` - `FhirAnalysisRequest`
  - `conversation_summaries.py` - `ConversationSummary` (shared output model)
  - `ai_chat.py` - `AiChatRequest`
  - `intent_identify.py` - `IntentResponse`, `MedicalIntentResponse`
  - `past_visit_query.py` - `PastVisitQuery`, `VisitTimeframe`
  - `health_insights_extraction.py` - `HealthInsightsResponse`
  - `translation.py` - Translation models
  - `schedule_visit.py` - Scheduling models

**`src/app/db/`**
- Purpose: Database configuration and data access
- Contains: Engine setup, ORM models, repository classes
- Key files:
  - `config/database.py` - Async engine (lazy init), session factory, `get_db()` dependency
  - `models/appointments.py` - `Appointment` ORM model
  - `models/chatbot_conversations.py` - `ChatbotConversation`
  - `models/chatbot_messages.py` - `ChatbotMessage`
  - `models/fhir_resources.py` - `FhirResource`
  - `models/user_profiles.py` - `UserProfile`
  - `models/users.py` - `User`
  - `models/ref_cms_provider_data.py` - `RefCmsProviderData`
  - `objects/repositories/conversation_summaries.py` - `ConversationSummariesRepository` (upsert, query by appointment)
  - `objects/repositories/fhir_resources.py` - `FhirResourcesRepository` (DocumentReference queries)
  - `objects/repositories/patient_health_insights.py` - Health insights CRUD
  - `objects/repositories/users.py` - User queries
  - `objects/entities/` - Entity definitions for tables owned by FastAPI

**`src/app/config/`**
- Purpose: Application configuration loading
- Key files:
  - `ssm_loader.py` - `SSMParameterLoader` class, `SSMParameterMapping` definitions, sync/async loading
  - `environment.py` - `initialize_environment_sync()`, env file loading, SSM orchestration
  - `configuration_summary.py` - Debug logging of loaded configuration

**`src/app/core/`**
- Purpose: Core application services
- Key files:
  - `settings.py` - `Settings` (Pydantic BaseSettings), `get_settings()` cached factory
  - `scheduler.py` - APScheduler initialization, health insight job registration
  - `langsmith_trace.py` - LangSmith tracing configuration

**`src/app/common/`**
- Purpose: Shared utilities, middleware, constants, error handling
- Key files:
  - `llm_factory.py` - `get_default_chat_model()`, `get_creative_chat_model()`, `get_pydantic_ai_model()` (all cached)
  - `middleware/clerk_auth.py` - `ClerkAuthMiddleware` (JWT validation)
  - `middleware/cors.py` - CORS configuration
  - `middleware/request_logging.py` - `RequestLoggingMiddleware`
  - `middleware/rate_limiter.py` - Rate limiting setup
  - `constants/cache_keys.py` - Redis cache key templates (shared with Node API)
  - `constants/llm.py` - LLM model names and providers
  - `exception/` - Custom exception classes (`base.py`, `exception.py`, `handlers.py`)
  - `exception_handlers.py` - `register_exception_handlers()` for FastAPI app
  - `error_handlers.py` - Error response factory functions
  - `error_models.py` - `BusinessLogicError`, `ExternalServiceError`

**`src/app/cache/`**
- Purpose: Redis client singleton
- Key files:
  - `redis.py` - `RedisClient` singleton class, module-level `redis_client` instance

**`src/app/utils/`**
- Purpose: External service clients
- Key files:
  - `s3_client.py` - `S3DocumentClient` for downloading document attachments

**`evals/`**
- Purpose: AI prompt evaluation framework for testing summarization quality
- Contains: Test runners, scoring modules, fixture documents, versioned prompts
- Key files:
  - `run_eval.py` - Main evaluation runner
  - `run_live_eval.py` - Live case evaluation
  - `scoring/` - Scoring modules (accuracy, hallucination, completeness, etc.)
  - `fixtures/documents/` - Sample medical documents
  - `fixtures/ground_truth/` - Expected outputs
  - `prompts/v001/`, `v002/`, `v003/` - Versioned prompt snapshots

## Key File Locations

**Entry Points:**
- `src/app/main.py` - FastAPI application factory and lifespan handler
- `src/app/main.py:main()` - Development server entry point (`uv run python src/app/main.py`)

**Configuration:**
- `pyproject.toml` - Dependencies, build config, tool settings
- `src/app/core/settings.py` - All application settings
- `src/app/config/ssm_loader.py` - SSM parameter path mappings
- `.env.development` - Local dev env vars (not secrets)

**Core Logic:**
- `src/app/services/summarization/comprehensive_summarization.py` - Most complex service
- `src/app/routes/ai_chat.py` - Chatbot entry point
- `src/app/chains/ai_chat_intents/intend_identifier/router.py` - Intent dispatch
- `src/app/chains/ai_chat_intents/past_visit_intent/chain.py` - Most complex intent handler

**Testing:**
- `src/app/tests/unit/test_chat.py` - Chat unit tests
- `src/app/tests/unit/test_health.py` - Health check tests
- `evals/` - AI evaluation framework (separate from unit tests)

## Naming Conventions

**Files:**
- Snake_case: `transcript_summarization.py`, `health_insight_generator.py`
- Models match their domain: `ai_chat.py`, `past_visit_query.py`

**Directories:**
- Snake_case for features: `transcript_summarization/`, `past_visit_intent/`
- Singular for utility dirs: `config/`, `core/`, `cache/`
- Plural for collection dirs: `models/`, `routes/`, `services/`, `chains/`

**Classes:**
- PascalCase with domain suffix: `TranscriptSummarizationService`, `TranscriptSummarizationChain`, `ConversationSummariesRepository`
- Service classes: `{Feature}Service`
- Chain classes: `{Feature}Chain`
- Repository classes: `{Table}Repository`

## Where to Add New Code

**New Summarization Type:**
1. Create chain: `src/app/chains/{feature_name}/chain.py` + `constants.py`
2. Create Pydantic models: `src/app/models/{feature_name}.py`
3. Create service: `src/app/services/summarization/{feature_name}.py`
4. Add route endpoint in `src/app/routes/care_capture.py`
5. Export service from `src/app/services/summarization/__init__.py`

**New Chatbot Intent:**
1. Create directory: `src/app/chains/ai_chat_intents/{intent_name}/`
2. Add `chain.py`, `constants.py`, `__init__.py` following existing intent pattern
3. Add enum value to `src/app/chains/ai_chat_intents/intend_identifier/models.py` (`RouterOptions`)
4. Update system prompt in `src/app/chains/ai_chat_intents/intend_identifier/constants.py`
5. Register handler in `src/app/chains/ai_chat_intents/intend_identifier/router.py`

**New API Route:**
1. Create route file: `src/app/routes/{feature}.py`
2. Define router with prefix and tags
3. Export from `src/app/routes/__init__.py`
4. Register in `src/app/main.py` via `app.include_router()`

**New Database Model:**
1. Add SQLAlchemy model: `src/app/db/models/{table_name}.py`
2. Add repository: `src/app/db/objects/repositories/{table_name}.py`
3. Add entity (if FastAPI-owned): `src/app/db/objects/entities/{table_name}.py`

**New Background Job:**
1. Create generator class in `src/app/services/`
2. Register in `src/app/core/scheduler.py`
3. Add constants in `src/app/constants/scheduler.py`

**New Pydantic Model:**
- Place in `src/app/models/{feature_name}.py`
- Use for both request validation and response serialization

**New Utility/Helper:**
- Shared helpers: `src/app/common/`
- External service clients: `src/app/utils/`

## Special Directories

**`evals/`**
- Purpose: AI prompt evaluation and regression testing
- Generated: Results are generated, prompts are versioned
- Committed: Yes (fixtures and prompts committed, some results gitignored)

**`.github/workflows/`**
- Purpose: CI/CD deployment pipelines
- Files: `dev-deploy.yml`, `prod-deploy.yml`
- Committed: Yes

**`.planning/`**
- Purpose: Planning and analysis documents
- Generated: Yes
- Committed: Varies

**`.claude/`**
- Purpose: Claude Code configuration, agent memory, skills
- Generated: Yes
- Committed: Partially

## Key Observations

- The `src/app/routes/pull_db_context.py` file is a helper module, not a router -- it provides functions used by `ai_chat.py` to populate Redis cache
- The `src/app/models/` directory contains Pydantic models only (not SQLAlchemy) -- DB models are in `src/app/db/models/`
- Chain `constants.py` files contain the actual prompt text -- these are the most frequently edited files when tuning AI behavior
- The `evals/` directory is a standalone evaluation framework with its own test runner, separate from pytest
- Two constant directories exist: `src/app/common/constants/` (shared) and `src/app/constants/` (app-level) -- prefer `src/app/common/constants/` for new constants
