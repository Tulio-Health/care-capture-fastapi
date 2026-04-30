---
generated: 2026-04-03
focus: concerns
---

# Concerns & Technical Debt

## Overview

The codebase is a functional FastAPI service handling AI-powered medical summarization and chatbot features. The core architecture is reasonable, but there are significant concerns around **test coverage** (nearly zero functional tests), **debug artifacts in production code** (74 print statements), **missing retry/resilience patterns for OpenAI calls**, and a **code-level bug in intent identification**. The application handles sensitive healthcare data (PHI), which amplifies the impact of security and reliability gaps.

---

## Critical Issues

### 1. Bug: Unreachable Code in Intent Identifier Chain

- **Issue:** In `_is_likely_ai_response()`, the method body is placed AFTER `@property` decorators at the bottom of the class, making it unreachable. The actual method on line 191 returns `None` (no return statement before the properties on line 207), meaning AI responses are never correctly identified in conversation history formatting.
- **Files:** `src/app/chains/ai_chat_intents/intend_identifier/chain.py` (lines 191-222)
- **Impact:** Conversation history formatting incorrectly labels all messages, degrading intent identification accuracy. Every message gets classified as a user message since `None` is falsy.
- **Fix approach:** Move lines 221-222 back into the `_is_likely_ai_response` method body before the `@property` decorators.

### 2. Near-Zero Test Coverage

- **Issue:** Only 2 unit test files exist (`test_chat.py`, `test_health.py`) with a total of ~4 tests. The chat tests reference `src.app.routes.ai-chat` (with a hyphen) which is an invalid Python import path -- these tests cannot run. Zero integration tests. No tests for any chain, service, or critical business logic.
- **Files:** `src/app/tests/unit/test_chat.py`, `src/app/tests/unit/test_health.py`, `src/app/tests/integration/` (empty)
- **Impact:** Any code change risks undetected regressions. The summarization pipeline, intent routing, FHIR analysis, and translation services have zero automated verification.
- **Fix approach:** Prioritize tests for: (1) intent identification chain, (2) past visit filtering logic, (3) comprehensive summarization orchestration, (4) translation service. Fix the broken import path in `test_chat.py`.

### 3. No Retry/Resilience for OpenAI API Calls

- **Issue:** All LLM calls (intent identification, summarization, chat responses) have zero retry logic, no circuit breakers, and no backoff. A single OpenAI API timeout or rate limit causes immediate user-facing failures.
- **Files:** `src/app/common/llm_factory.py`, all chain files under `src/app/chains/`
- **Impact:** OpenAI rate limits or transient failures cause 500 errors. Healthcare chatbot availability directly depends on a single external API with no fallback.
- **Fix approach:** Add `tenacity` retry decorator to LLM factory calls with exponential backoff. Consider adding a model fallback (e.g., GPT-4o-mini -> GPT-3.5-turbo) for degraded service.

### 4. No Prompt Injection Protection

- **Issue:** User chat messages are passed directly into LLM prompts without sanitization. In a healthcare context, this means a user could manipulate the AI to produce misleading medical information, extract system prompts, or bypass intent routing.
- **Files:** `src/app/routes/ai_chat.py` (line 108-114), `src/app/chains/ai_chat_intents/intend_identifier/chain.py` (line 96), all intent chain `handle_intent` methods
- **Impact:** Prompt injection could cause the chatbot to provide dangerous medical misinformation, leak system prompts, or bypass the intent classification system.
- **Fix approach:** Add input sanitization middleware for chat endpoints. Implement prompt injection detection (keyword filtering + structural checks). Add output validation to verify responses stay within expected medical context boundaries.

---

## Warnings

### 5. 74 Print Statements in Production Code

- **Issue:** 74 `print()` calls scattered across 10 source files instead of using the structured logging system (`get_logger`). These bypass log levels, are not captured by log aggregation, and leak debug info to stdout.
- **Files:** `src/app/routes/chain_testing.py` (50), `src/app/chains/ai_chat_intents/upcoming_visit_intent/chain.py` (7), `src/app/chains/ai_chat_intents/past_visit_intent/chain.py` (5), `src/app/routes/ai_chat.py` (3), `src/app/common/middleware/clerk_auth.py` (1)
- **Impact:** Debug noise in production logs; structured log queries miss these messages; potential PHI leakage via unstructured stdout (e.g., `print(f"AI response: ", ai_response)` in `ai_chat.py` line 116).
- **Fix approach:** Replace all `print()` with appropriate `logger.debug()` or `logger.info()` calls. Remove verbose debug prints from production paths.

### 6. Synchronous Redis Client in Async Application

- **Issue:** `RedisClient` uses synchronous `redis.Redis` instead of `redis.asyncio.Redis`. All Redis operations (`get`, `set`, `lrange`) block the event loop, reducing throughput under load.
- **Files:** `src/app/cache/redis.py`, `src/app/routes/ai_chat.py` (lines 45-93), `src/app/chains/ai_chat_intents/past_visit_intent/chain.py` (lines 306-318)
- **Impact:** Every Redis call blocks the entire asyncio event loop. Under concurrent load, this creates a bottleneck -- a single slow Redis call blocks all other requests. The rate limiter module (`src/app/common/middleware/rate_limiter.py`) correctly uses `redis.asyncio`, creating an inconsistency.
- **Fix approach:** Migrate `RedisClient` to use `redis.asyncio.Redis`. Update all call sites to use `await`. This is a significant refactor since `redis_client` is imported as a module-level singleton.

### 7. Authentication Bypass When CLERK_PUBLIC_JWT_KEY Missing

- **Issue:** When `CLERK_PUBLIC_JWT_KEY` is not configured, the middleware sets `auth_enabled = False` and allows all requests through with a default dev user (`clerk_id: "dev_user"`). If SSM fails to load this parameter in production, all endpoints become unauthenticated.
- **Files:** `src/app/common/middleware/clerk_auth.py` (lines 86-89, 239-249)
- **Impact:** A misconfiguration or SSM loading failure silently disables authentication for the entire service. No alert or hard failure occurs.
- **Fix approach:** In production (`APP_ENV=production`), raise a startup error if `CLERK_PUBLIC_JWT_KEY` is missing rather than silently disabling auth. Add health check verification for auth configuration.

### 8. Sensitive Data in Error Responses

- **Issue:** Multiple routes expose internal error details in HTTP responses via `str(e)` in HTTPException detail fields. This can leak database schema info, file paths, or API error messages to clients.
- **Files:** `src/app/routes/care_capture.py` (lines 82, 366, 391, 607), `src/app/routes/ai_chat.py` (line 122)
- **Impact:** Internal exception messages exposed to API consumers. In a healthcare context, this could leak PHI-adjacent information or internal architecture details.
- **Fix approach:** Return generic error messages to clients. Log detailed errors server-side. The `create_internal_error_response` in `src/app/common/error_handlers.py` already does this correctly -- ensure all routes use it consistently.

### 9. LLM Model Cached with `lru_cache` -- No Cache Invalidation

- **Issue:** `get_chat_model()` uses `@lru_cache(maxsize=1)` which means the model instance (including the API key) is cached forever. If the OpenAI API key is rotated via SSM, the application must be restarted to pick up the new key.
- **Files:** `src/app/common/llm_factory.py` (line 13)
- **Impact:** API key rotation requires service restart. Combined with the `get_settings()` `@lru_cache()` in `src/app/core/settings.py` (line 125), all SSM-loaded configuration is permanently cached after first access.
- **Fix approach:** Add a cache-clearing mechanism triggered by a management endpoint or signal. Alternatively, have the model factory check key freshness periodically.

### 10. Incomplete Health Insights Save Logic (TODO)

- **Issue:** The health insight generator has placeholder TODO comments where database save logic should be. The `_save_health_insights` method appears to have stub implementations.
- **Files:** `src/app/services/health_insights/health_insight_generator.py` (lines 167, 175)
- **Impact:** Generated health insights may not be persisted to the database, causing data loss for scheduled insight generation jobs.
- **Fix approach:** Implement the database save logic using `PatientHealthInsightsRepository`.

### 11. Chain Testing Route Exposed in Production

- **Issue:** `src/app/routes/chain_testing.py` contains hardcoded test user IDs and test cases. While it's unclear if this route is registered in production (it's not visible in `main.py` router includes), the file exists in the deployable source.
- **Files:** `src/app/routes/chain_testing.py` (507 lines), hardcoded user IDs throughout
- **Impact:** If accidentally mounted, exposes test endpoints with real user IDs. Even unmounted, hardcoded UUIDs in source code are a code quality concern.
- **Fix approach:** Move to `evals/` directory or gate behind development-only flag similar to the playground routes pattern in `src/app/main.py` (line 134).

### 12. Medical Terminology Service is a Hardcoded Dictionary (815 lines)

- **Issue:** `MedicalTerminologyService` is an 815-line file of hardcoded Spanish medical term mappings. This is not scalable for adding new languages and is difficult to maintain or verify for medical accuracy.
- **Files:** `src/app/services/translation/medical_terminology.py` (815 lines)
- **Impact:** Adding a new language requires duplicating the entire dictionary pattern. Medical term accuracy cannot be easily reviewed or updated by non-developers.
- **Fix approach:** Move terminology to a structured data file (JSON/YAML) that can be reviewed by medical translators. Load at startup. Consider using the LLM for dynamic translation with terminology guidelines.

---

## Minor Issues

### 13. Global Mutable State Pattern

- **Issue:** Multiple global variables used for lazy initialization: database engine, session factory, tracer instances across 11 chain files. The `redis_client` singleton is instantiated at module import time (`redis_client = RedisClient()` at bottom of `src/app/cache/redis.py` line 66).
- **Files:** `src/app/db/config/database.py` (lines 12-13, 86), `src/app/cache/redis.py` (line 66), all chain files using `global _tracer`
- **Impact:** Makes testing difficult (can't easily mock singletons), creates import order dependencies, and risks race conditions during startup.
- **Fix approach:** Use FastAPI's dependency injection system consistently. Convert singletons to app-state or dependency-injected instances.

### 14. Unused/Dead Code

- **Issue:** Large blocks of commented-out code in production files. The `async_session_factory = None` on line 86 of `database.py` is dead code (the actual factory is `_async_session_factory`). The `@property` decorator for `engine()` on line 79 of `database.py` is a module-level function decorated with `@property` which does nothing useful.
- **Files:** `src/app/routes/care_capture.py` (lines 203-303 -- 100 lines of commented code), `src/app/db/config/database.py` (lines 79-86), `src/app/chains/ai_chat_intents/intend_identifier/router.py` (commented handlers)
- **Impact:** Code noise, confusion about what's active, misleading backward compatibility stubs.
- **Fix approach:** Remove commented-out code (it's in git history). Remove dead backward-compatibility stubs.

### 15. No Token/Context Window Management for LLM Calls

- **Issue:** Chat conversation history is capped at 30 items but not by token count. Enriched summaries are capped at 15 (`MAX_SUMMARIES_FOR_LLM`) but individual summaries can be arbitrarily long. There's no token counting before LLM invocation.
- **Files:** `src/app/routes/ai_chat.py` (line 75 -- `MAX_CONVERSATION_ITEMS = 30`), `src/app/chains/ai_chat_intents/past_visit_intent/chain.py` (line 40 -- `MAX_SUMMARIES_FOR_LLM = 15`)
- **Impact:** Long conversations or verbose summaries could exceed the model's context window, causing API errors or silent truncation.
- **Fix approach:** Add token counting (using `tiktoken`) before LLM calls. Implement smart truncation that preserves the most relevant context.

### 16. Rate Limiter Not Connected

- **Issue:** The rate limiter module exists (`src/app/common/middleware/rate_limiter.py`) and is imported in `main.py`, but `setup_rate_limiter` is an async function that doesn't appear to be called during startup (it's imported but the lifespan function doesn't invoke it).
- **Files:** `src/app/common/middleware/rate_limiter.py`, `src/app/main.py` (line 25 -- imported but not called in lifespan)
- **Impact:** No rate limiting is active. The API is vulnerable to abuse, which is especially concerning for LLM endpoints that incur cost per request.
- **Fix approach:** Call `await setup_rate_limiter(app)` in the lifespan startup. Add rate limit decorators to expensive endpoints (chat, summarization).

### 17. Misspelling: "Intend" vs "Intent"

- **Issue:** The intent identifier module uses "Intend" instead of "Intent" throughout its naming: `IntendIdentifierChain`, `intend_identifier/` directory.
- **Files:** `src/app/chains/ai_chat_intents/intend_identifier/` (entire directory), `src/app/chains/ai_chat_intents/intend_identifier/chain.py` (class name)
- **Impact:** Minor code quality/readability issue. Inconsistent with the rest of the codebase which uses "intent" correctly.
- **Fix approach:** Rename when convenient, but low priority given the scope of the rename.

### 18. No Database Migration Verification at Startup

- **Issue:** The application connects to the database but doesn't verify that migrations are up to date. Alembic is a dependency but there's no startup check for schema compatibility.
- **Files:** `src/app/health/startup_checks.py`, `src/app/main.py`
- **Impact:** Deploying code that expects new columns/tables before running migrations causes runtime errors.
- **Fix approach:** Add an Alembic head check to `run_all_startup_checks()`.

---

## Recommendations

**Immediate priorities (next sprint):**
1. Fix the `_is_likely_ai_response` bug in intent identifier chain (item 1)
2. Replace `print()` statements with proper logging, especially in `ai_chat.py` where AI responses containing PHI are printed (item 5)
3. Add production guard for missing `CLERK_PUBLIC_JWT_KEY` (item 7)
4. Remove internal error details from client-facing HTTP responses (item 8)

**Short-term (next 2-3 sprints):**
5. Add retry logic with exponential backoff for OpenAI API calls (item 3)
6. Migrate Redis client to async (item 6)
7. Write tests for intent identification, past visit filtering, and summarization (item 2)
8. Add basic prompt injection sanitization (item 4)

**Medium-term:**
9. Implement token counting for LLM context management (item 15)
10. Activate rate limiting on LLM endpoints (item 16)
11. Extract medical terminology to data files (item 12)
12. Clean up dead code and commented blocks (item 14)
