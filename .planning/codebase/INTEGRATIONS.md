---
generated: 2026-04-03
focus: tech
---

# External Integrations

## Overview

The FastAPI service integrates with OpenAI for all AI capabilities, shares a PostgreSQL database and Redis cache with the Node API, uses Clerk for authentication, and relies on AWS SSM for configuration. Inter-service communication with the Node API happens primarily through shared Redis keys and a shared database, not direct HTTP calls.

## APIs & External Services

### OpenAI

- **Purpose:** Powers all AI chains -- summarization, chatbot intent routing, translation, FHIR analysis, health insights, schedule visit parsing
- **SDK/Client:** `langchain-openai` (via `init_chat_model()`), `openai` SDK, `pydantic-ai-slim[openai]`
- **Factory:** `src/app/common/llm_factory.py` -- centralized model creation with `@lru_cache`
- **Default model:** `gpt-4o-mini` at temperature 0.2
- **Auth:** `OPENAI_API_KEY` loaded from SSM (`/tuliohealth/{env}/openai/api_key`)
- **Usage locations:**
  - `src/app/chains/transcript_summarization/chain.py` - Visit transcript summarization
  - `src/app/chains/ai_chat_intents/intend_identifier/chain.py` - Chatbot intent classification
  - `src/app/chains/ai_chat_intents/past_visit_intent/chain.py` - Past visit queries
  - `src/app/chains/ai_chat_intents/upcoming_visit_intent/chain.py` - Upcoming visit queries
  - `src/app/chains/ai_chat_intents/medical_inquiry_intent/chain.py` - Medical inquiry responses
  - `src/app/chains/ai_chat_intents/health_insights_intent/chain.py` - Health insight queries
  - `src/app/chains/fhir_analysis/chain.py` - FHIR resource analysis
  - `src/app/chains/translation/chain.py` - Medical summary translation
  - `src/app/chains/attachment_summarization/chain.py` - Document attachment summarization
  - `src/app/chains/health_insights/chain.py` - Health insight extraction
  - `src/app/chains/schedule_visit/chain.py` - Schedule visit parsing

### LangSmith

- **Purpose:** LLM observability, tracing, and debugging
- **SDK/Client:** `langsmith` (`LangSmithClient`), `langchain.callbacks.tracers.LangChainTracer`
- **Implementation:** `src/app/core/langsmith_trace.py` -- `LangSmithTrace` class with lazy init
- **Auth:** `LANGSMITH_API_KEY` (from SSM or `.env.development`)
- **Config vars:** `LANGSMITH_TRACING`, `LANGSMITH_ENDPOINT`, `LANGSMITH_PROJECT`
- **Behavior:** Tracing is optional. When disabled (`is_enabled() == False`), callbacks return `None` and chains run without tracing.

### Clerk (Authentication)

- **Purpose:** JWT-based user authentication
- **Implementation:** `src/app/common/middleware/clerk_auth.py` -- `ClerkAuthMiddleware`
- **Auth flow:**
  1. Node API passes Clerk JWT via `x-clerk-jwt` header
  2. FastAPI middleware verifies JWT using Clerk's RSA public key (RS256)
  3. User info (clerk_id, email, role) extracted and attached to `request.state.user`
- **Auth vars from SSM:**
  - `CLERK_PUBLIC_JWT_KEY` - RSA public key for JWT verification
  - `CLERK_SECRET_KEY` - Clerk secret key
  - `CLERK_PUBLISHABLE_KEY` - Clerk publishable key
- **Service-to-service auth:** `x-internal-service-key` header matched against `INTERNAL_SERVICE_KEY` env var for internal calls from Node API
- **Excluded paths:** Health checks, docs, playground endpoints skip auth

## Data Storage

### PostgreSQL (AWS RDS)

- **Provider:** AWS RDS PostgreSQL
- **Client:** SQLAlchemy 2.0 async with `asyncpg` driver
- **Connection config:** `src/app/db/config/database.py`
- **Connection vars (all from SSM):**
  - `DB_HOST` - RDS endpoint
  - `DB_PORT` - Default 5432
  - `DB_USER` - Database username
  - `DB_PASSWORD` - Database password
  - `DB_NAME` - Database name (`care-capture-app-dev` / `care-capture-app`)
- **Connection URL format:** `postgresql+asyncpg://{user}:{pass}@{host}:{port}/{db}`
- **Pool config:**
  - App Runner: `AsyncAdaptedQueuePool` (pool_size=5, max_overflow=10, pool_timeout=120)
  - Local dev: `NullPool` (no pooling)
- **Shared database:** This is the SAME database used by the Node API and EMR Connector
- **Key tables accessed:**
  - `fhir_resources` - FHIR data synced from EMR systems (`src/app/db/models/fhir_resources.py`)
  - `user_profiles` - User profile data (`src/app/db/models/user_profiles.py`)
  - `chatbot_conversations` - Chatbot conversation records (`src/app/db/models/chatbot_conversations.py`)
  - `chatbot_messages` - Individual chat messages (`src/app/db/models/chatbot_messages.py`)
  - `appointments` - Patient appointments (`src/app/db/models/appointments.py`)
  - `ref_cms_provider_data` - CMS provider reference data (`src/app/db/models/ref_cms_provider_data.py`)
  - `conversation_summaries` - AI-generated summaries (entity: `src/app/db/objects/entities/conversation_summaries.py`)
  - `patient_health_insights` - Extracted health insights (entity: `src/app/db/objects/entities/patient_health_insights.py`)
  - `scheduler_job_execution_logs` - Background job logs (entity: `src/app/db/objects/entities/scheduler_job_execution_logs.py`)
- **Migrations:** Alembic is a dependency but migration files are not in this repo (likely managed by the Node API or a separate process)

### Redis (AWS ElastiCache)

- **Provider:** AWS ElastiCache (production), local Redis (development)
- **Client:** `redis-py` synchronous client, singleton pattern (`src/app/cache/redis.py`)
- **Connection vars (from SSM):**
  - `REDIS_HOST` - ElastiCache endpoint (overridden to `127.0.0.1` for local dev)
  - `REDIS_PORT` - Default 6379
  - `REDIS_PASSWORD` - Auth token (cleared for local dev)
- **Local override:** When not running in App Runner, Redis host is automatically set to `127.0.0.1:6379` with no password
- **Usage patterns:**
  - User profile cache (12h TTL): `care-capture-cache-key:conversation:user-profile:{user_id}`
  - Health insights cache (2h TTL): `care-capture-cache-key:conversation:health-insights:{user_id}`
  - Conversation context: `care-capture-cache-key:chatbot:conversation-context:{conversation_id}`
  - Rate limiting (via `fastapi-limiter`)

**Critical: Shared Redis with Node API**
- The Node API writes enriched summaries to Redis keys: `care-capture-cache-key:chatbot:user-summaries:{user_id}`
- The Node API writes conversation chat history using `lpush` to keys: `care-capture-cache-key:conversation:{conversation_id}`
- FastAPI reads these keys directly (`src/app/routes/pull_db_context.py`)
- Key prefix `care-capture-cache-key` is shared between both services (`src/app/common/constants/cache_keys.py`)

### File Storage

- No external file storage (S3, etc.)
- Document attachments are received as bytes in API requests and processed in-memory
- `src/app/services/document_extraction.py` handles PDF, DOCX, TXT, XML, HTML extraction

## Inter-Service Communication

### Node API -> FastAPI (Inbound)

- **Transport:** HTTP REST calls from Node API to FastAPI endpoints
- **Authentication:** Either Clerk JWT passthrough (`x-clerk-jwt`) or internal service key (`x-internal-service-key`)
- **Key endpoints called by Node API:**
  - `POST /care-capture/transcript-summarization` - Summarize provider visit transcripts
  - `POST /care-capture/comprehensive-summary` - Parallel transcript + FHIR analysis
  - `POST /care-capture/attachment-summary` - Summarize document attachments
  - `POST /care-capture/fhir-analysis` - Analyze FHIR resources
  - `POST /care-capture/ai-chat/` - AI chatbot requests
  - `POST /care-capture/schedule-visit/` - Parse schedule visit intent
  - `POST /care-capture/conversation-summaries/{id}/translate` - Translate summaries

### Node API <-> FastAPI (Shared State via Redis)

- Node API writes enriched appointment summaries to Redis (`chatbot:user-summaries:{user_id}`)
- Node API writes conversation history via `lpush` to Redis (`conversation:{conversation_id}`)
- FastAPI reads these keys to build chatbot context (`src/app/routes/pull_db_context.py`, `src/app/routes/ai_chat.py`)
- FastAPI writes conversation context for follow-ups (`chatbot:conversation-context:{conversation_id}`)
- Both services share the `care-capture-cache-key` prefix convention

### EMR Connector -> Database (Indirect)

- The EMR Connector syncs FHIR resources from EHR systems (Cerner, Epic, Meditech, Allscripts, Athenahealth) into the shared `fhir_resources` table
- FastAPI reads these resources for FHIR analysis (`src/app/services/summarization/fhir_analysis.py`)
- No direct communication between FastAPI and EMR Connector

## AWS Services

### SSM Parameter Store

- **Purpose:** Centralized configuration management (secrets and non-secrets)
- **Implementation:** `src/app/config/ssm_loader.py` -- `SSMParameterLoader` class
- **Loading:** Synchronous at app startup, before route imports (`src/app/main.py` line 14)
- **Parameter prefix:** `/tuliohealth/{dev|prod}/`
- **Total parameters:** 18 mappings defined (database, redis, openai, clerk, langsmith, internal service key, playground)
- **Secure parameters:** `DB_PASSWORD`, `REDIS_PASSWORD`, `OPENAI_API_KEY`, `CLERK_SECRET_KEY`, `LANGSMITH_API_KEY`, `INTERNAL_SERVICE_KEY`, `PLAYGROUND_API_KEY`
- **Behavior:** In production, missing SSM parameters cause startup failure. In development, falls back to environment variables.

### AWS App Runner

- **Purpose:** Production container hosting
- **Detection:** `AWS_EXECUTION_ENV` starts with `AWS_App_Runner`
- **Impact on config:**
  - Database: Uses `AsyncAdaptedQueuePool` instead of `NullPool`
  - Redis: Uses ElastiCache endpoint instead of localhost override
- **Docker image:** Built from `Dockerfile`, python:3.12-slim base

### AWS RDS

- **Purpose:** PostgreSQL database hosting
- **Environments:** Separate dev and prod instances
- **Connection:** Via SSM-loaded credentials, asyncpg driver

### AWS ElastiCache

- **Purpose:** Redis hosting for production
- **Connection:** Via SSM-loaded credentials

## Monitoring & Observability

### LangSmith Tracing

- **Purpose:** LLM call tracing, cost monitoring, debugging
- **Implementation:** `src/app/core/langsmith_trace.py`
- **Integration:** Chains pass `LangChainTracer` callbacks; also uses `@traceable` decorator
- **Config:** `LANGSMITH_TRACING`, `LANGSMITH_API_KEY`, `LANGSMITH_ENDPOINT`, `LANGSMITH_PROJECT`

### Application Logging

- **Framework:** Python `logging` with custom configuration (`src/app/common/logging/`)
- **Request logging:** `RequestLoggingMiddleware` (`src/app/common/middleware/request_logging.py`)
- **Configuration summary:** `src/app/config/configuration_summary.py` logs config at startup

### Health Checks

- **Startup validation:** `src/app/health/startup_checks.py` runs checks during lifespan startup
- **Health endpoint:** `/health` route (`src/app/routes/health.py`)

## Background Jobs

### APScheduler

- **Purpose:** Periodic background task execution
- **Implementation:** `src/app/core/scheduler.py` -- `AsyncIOScheduler`
- **Jobs:**
  - Health insight generation: Runs on interval (configured via `HEALTH_INSIGHT_SCHEDULE_SECONDS` in `src/app/constants/scheduler.py`)
  - Implementation: `src/app/services/health_insights/health_insight_generator.py`
  - Execution logged to `scheduler_job_execution_logs` table

## Webhooks & Callbacks

**Incoming:** None detected. All inbound communication is synchronous REST.

**Outgoing:** None detected. No webhook dispatch code found.

## Environment Configuration

**Required SSM parameters (production):**
- `database/host`, `database/port`, `database/username`, `database/password`, `database/name`, `database/ssl`
- `redis/host`, `redis/port`, `redis/password`
- `openai/api_key`
- `clerk/public_jwt_key`, `clerk/secret_key`, `clerk/publishable_key`
- `internal/service_key`
- `infrastructure/app_env`

**Optional SSM parameters:**
- `langsmith/tracing`, `langsmith/api_key`, `langsmith/endpoint`, `langsmith/project`
- `playground/api_key`

**Secrets location:**
- AWS SSM Parameter Store (SecureString type for sensitive values)
- Local: `.env.development` for non-secret overrides; SSM still used for secrets when AWS credentials are available

## Key Observations

1. **Shared state is the primary integration pattern.** FastAPI and Node API communicate through shared Redis keys and a shared PostgreSQL database rather than direct API calls between services. This creates implicit coupling through key naming conventions in `src/app/common/constants/cache_keys.py`.

2. **OpenAI is the sole LLM provider.** All AI functionality depends on OpenAI. There is no fallback provider or model abstraction beyond the OpenAI-specific factory.

3. **SSM loading is synchronous and blocking.** Configuration loads synchronously at module import time (`src/app/main.py` line 14), before the ASGI app starts. This adds startup latency but ensures all routes have access to config.

4. **Redis client is synchronous.** Despite the async FastAPI framework, the Redis client (`src/app/cache/redis.py`) uses synchronous `redis-py`, which blocks the event loop during Redis operations.

5. **No message queue.** All communication is synchronous REST or shared state. There are no SQS, SNS, or event-driven patterns. Background processing uses APScheduler only.

6. **Document extraction is in-memory only.** No file storage integration (S3, etc.). Documents are received as request payloads, extracted in memory, and discarded after processing.

---

*Integration audit: 2026-04-03*
