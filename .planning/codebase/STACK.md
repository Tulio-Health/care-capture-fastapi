---
generated: 2026-04-03
focus: tech
---

# Technology Stack

## Overview

Care Capture AI is a Python FastAPI service focused on AI-powered medical summarization, chatbot intent routing, and translation. It runs as a companion service behind a Node API, deployed on AWS App Runner with configuration loaded from AWS SSM Parameter Store.

## Languages

**Primary:**
- Python 3.12+ - All application code
- Target version enforced in `pyproject.toml` (`requires-python = ">=3.12"`) and `[tool.black]` (`target-version = ['py312']`)

## Runtime

**Environment:**
- Python 3.12-slim (Docker base image in `Dockerfile`)
- Uvicorn ASGI server with standard extras (`uvicorn[standard]>=0.27.0,<0.28`)

**Package Manager:**
- `uv` (Astral) - Fast Python package manager
- Lockfile: `uv.lock` present
- Build backend: `hatchling`
- Install command: `uv sync` (production: `uv sync --frozen --no-dev --no-install-project`)

## Frameworks

**Core:**
- FastAPI `>=0.115.2,<0.116` - Web framework (`src/app/main.py`)
- Pydantic (via pydantic-settings) - Settings management and request/response validation (`src/app/core/settings.py`)
- SQLAlchemy `>=2.0.23,<3` - Async ORM with `asyncpg` driver (`src/app/db/config/database.py`)

**AI/ML:**
- LangChain `>=0.3.3,<0.4` - LLM chain orchestration (`src/app/chains/`)
- LangChain-OpenAI `>=0.2.2,<0.3` - OpenAI model integration
- LangGraph `>=0.3.31,<0.4` - Agent graph workflows
- LangChain-Community `>=0.3.22,<0.4` - Community integrations
- LangSmith `>=0.3.42,<0.4` - LLM observability and tracing (`src/app/core/langsmith_trace.py`)
- OpenAI SDK `>=1.51.2,<2` - Direct OpenAI API access
- Pydantic AI Slim (OpenAI) `>=1.0,<2` - Pydantic-native AI agents (`src/app/common/llm_factory.py:get_pydantic_ai_model()`)

**Testing:**
- pytest `>=8.0.0,<9` - Test runner
- pytest-asyncio `>=0.23.5,<0.24` - Async test support
- pytest-cov `>=4.1.0,<5` - Coverage reporting

**Linting/Formatting:**
- Black `>=24.1.1,<25` - Code formatter (line-length: 88)
- isort `>=5.13.2,<6` - Import sorter (profile: black)
- flake8 `>=7.0.0,<8` - Linter
- mypy `>=1.8.0,<2` - Static type checker (`disallow_untyped_defs = true`)

## Key Dependencies

**Critical (runtime):**
- `langchain` + `langchain-openai` + `langgraph` - Core AI pipeline; all chains in `src/app/chains/` depend on these
- `sqlalchemy` + `asyncpg` - Database access layer; async engine with connection pooling
- `redis` `>=5.0.1,<6` - Caching and shared state with Node API (`src/app/cache/redis.py`)
- `boto3` `>=1.35.0,<2` - AWS SDK for SSM Parameter Store (`src/app/config/ssm_loader.py`)
- `pyjwt` `>=2.8.0,<3` + `cryptography` `>=41.0.7,<42` - Clerk JWT verification (`src/app/common/middleware/clerk_auth.py`)

**Document Processing:**
- `pymupdf` `>=1.24.0,<2` (imported as `fitz`) - PDF text extraction (`src/app/services/document_extraction.py`)
- `python-docx` `>=1.1.0,<2` - DOCX text extraction (`src/app/services/document_extraction.py`)
- `python-multipart` `>=0.0.9` - File upload handling

**Infrastructure:**
- `apscheduler` `>=3.11.0,<4` - Background job scheduling (`src/app/core/scheduler.py`)
- `fastapi-limiter` `>=0.1.6,<0.2` - Rate limiting (Redis-backed)
- `httpx` `>=0.27.0` - Async HTTP client
- `python-dotenv` `>=1.0.0,<2` - Local environment file loading
- `email-validator` `>=2.1.0,<3` - Pydantic EmailStr support
- `greenlet` `>=3.0.3,<4` - Required by SQLAlchemy async operations
- `psycopg2-binary` `>=2.9.9,<3` - PostgreSQL adapter (likely used by Alembic migrations, though alembic dir not present in repo)
- `alembic` `>=1.13.1,<2` - Database migrations (dependency declared but migration directory not in this repo)

## LLM Configuration

**Models available** (defined in `src/app/common/constants/llm.py`):
- `gpt-4o-mini` - Default model for all chains (temperature 0.2)
- `gpt-4o` - Available but not default
- `gpt-4-1` - Available
- `gpt-4-1-mini` - Available

**Provider:** OpenAI only (`LLM_PROVIDER.OPENAI`)

**Factory pattern** (`src/app/common/llm_factory.py`):
- `get_default_chat_model()` - GPT-4o-mini, temperature 0.2 (used by most chains)
- `get_creative_chat_model()` - GPT-4o-mini, temperature 0.7
- `get_pydantic_ai_model()` - For Pydantic AI agent usage
- All models are cached via `@lru_cache` and use `langchain.chat_models.init_chat_model()`

## Configuration

**Environment:**
- Configuration loaded from AWS SSM Parameter Store at startup (`src/app/config/ssm_loader.py`)
- SSM parameter prefix: `/tuliohealth/{dev|prod}/`
- Local development uses `.env.development` with SSM fallback
- Settings managed via Pydantic BaseSettings in `src/app/core/settings.py`
- Settings cached with `@lru_cache` via `get_settings()`

**Key env files (existence noted, contents NOT read):**
- `.env.development` - Local dev config
- `.env.example` - Template

**Build:**
- `pyproject.toml` - Project metadata, dependencies, tool config
- `Dockerfile` - Python 3.12-slim, uv-based install, uvicorn CMD
- `uv.lock` - Dependency lockfile

## Platform Requirements

**Development:**
- Python 3.12+
- `uv` package manager
- Local Redis server on port 6379
- AWS CLI configured (for SSM parameter access)
- Access to AWS RDS dev database

**Production:**
- AWS App Runner (detected via `AWS_EXECUTION_ENV`)
- AWS RDS PostgreSQL (via SSM-loaded credentials)
- AWS ElastiCache Redis (via SSM-loaded credentials)
- AWS SSM Parameter Store (18 parameters across database, redis, openai, clerk, langsmith, internal service key, playground)

**Docker:**
- Base: `python:3.12-slim`
- Build: `uv sync --frozen --no-dev --no-install-project`
- Runtime: `uvicorn src.app.main:app --host 0.0.0.0 --port 8000`
- Exposed port: 8000

---

*Stack analysis: 2026-04-03*
