---
generated: 2026-04-03
focus: quality
---

# Testing Patterns

## Overview

The project has minimal unit/integration tests (2 test files with basic coverage) but a well-developed AI evaluation framework under `evals/`. The eval system tests LLM output quality across multiple dimensions (completeness, accuracy, hallucination, etc.) using ground truth fixtures and scoring functions. Traditional test coverage is a significant gap.

## Test Framework

**Runner:**
- pytest 8.x (configured in `pyproject.toml` dev dependencies)
- pytest-asyncio 0.23.x with `asyncio_mode = auto`
- pytest-cov 4.x for coverage

**Config:** `pytest.ini` at project root
```ini
[pytest]
testpaths = src/app/tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
asyncio_mode = auto
addopts = 
    --verbose
    --cov=src/app
    --cov-report=term-missing
    --cov-report=html
    --no-cov-on-fail
```

**Run Commands:**
```bash
uv run pytest                          # Run all tests with coverage
uv run pytest src/app/tests/           # Run unit/integration tests only
uv run pytest evals/                   # Run AI eval tests (makes LLM calls)
uv run pytest --no-cov                 # Run without coverage
uv run pytest -k "test_health"         # Run specific test
```

## Test File Organization

**Location:** Tests are in a dedicated directory, NOT co-located with source.

**Structure:**
```
src/app/tests/
    __init__.py
    conftest.py                    # App-level fixtures (test_client, mock_redis, DB setup)
    integration/
        __init__.py                # Empty - no integration tests exist
    unit/
        __init__.py
        test_chat.py               # Chat endpoint tests (3 tests)
        test_health.py             # Health check test (1 test)

evals/                             # AI/LLM evaluation framework (separate from pytest tests)
    __init__.py
    conftest.py                    # Eval fixtures (chain, ground truths, extraction results)
    test_extraction.py             # Extraction quality tests (5 parametrized x 8 docs = 40 tests)
    test_synthesis.py              # Synthesis quality tests (4 parametrized x 2 cases = 8 tests)
    run_eval.py                    # Standalone eval runner (writes JSON reports)
    run_live_eval.py               # Live case evaluation
    analyze.py                     # Result analysis utilities
    compare.py                     # Cross-version comparison
    log_experiment.py              # Experiment tracking
    scoring/                       # Scoring modules
        __init__.py
        accuracy.py
        clinical_summary.py        # LLM-as-judge scorer
        completeness.py
        deduplication.py
        hallucination.py
        medication_filter.py
        patient_language.py
        runner.py                  # Shared scoring orchestration
        types.py                   # ScoreResult, CaseResult, EvalReport dataclasses
    fixtures/
        documents/                 # 8 medical document text files
        ground_truth/              # 8 JSON files with expected extractions
        synthesis_cases/           # 2 multi-document synthesis case definitions
        live_cases/                # Live case data (documents, ground truth, AI output, metadata)
    prompts/
        v001/                      # Versioned prompts
        v002/
        v003/
    results/                       # JSON eval reports (timestamped)
```

**Naming:** `test_*.py` for test files, `test_*` for test functions.

## Test Structure

**Unit test pattern (`src/app/tests/unit/test_health.py`):**
```python
import pytest
from fastapi.testclient import TestClient

def test_health_check(test_client: TestClient):
    """Test the health check endpoint"""
    response = test_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "message" in data
```

**Chat test pattern with mocking (`src/app/tests/unit/test_chat.py`):**
```python
@pytest.fixture
def mock_intent_identifier():
    with patch("src.app.routes.ai-chat.IntendIdentifierChain") as mock:
        instance = mock.return_value
        instance.identify_intent.return_value = "medical_inquiry"
        yield instance

def test_chat_endpoint_success(
    test_client: TestClient,
    mock_redis,
    mock_intent_identifier,
    mock_intent_router
):
    response = test_client.post(
        "/care-capture/ai-chat/",
        json={"conversation_id": "test-conv-123", "message": "What are my test results?"}
    )
    assert response.status_code == 200
```

**NOTE:** The chat tests in `test_chat.py` have a bug - they patch `src.app.routes.ai-chat` (with hyphen) instead of the actual module path. These tests likely do not pass.

## Fixtures

**App-level fixtures (`src/app/tests/conftest.py`):**

```python
@pytest.fixture(scope="session")
def test_client() -> Generator[TestClient, None, None]:
    """Create a test client for the FastAPI application"""
    with TestClient(app) as client:
        yield client

@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """Set up test database and clean up after tests"""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

@pytest.fixture
def mock_redis():
    """Mock Redis client for testing"""
    class MockRedis:
        def __init__(self):
            self.cache = {}
        async def get(self, key: str) -> str:
            return self.cache.get(key)
        async def set(self, key: str, value: str, ex: int = None) -> bool:
            self.cache[key] = value
            return True
```

**Issue:** `setup_test_database` uses synchronous `engine` but the app uses `AsyncEngine`. This fixture likely fails or is incompatible with the current async database setup.

## AI Eval Framework

**Purpose:** Evaluate LLM output quality for the attachment summarization pipeline.

**How it works:**
1. Ground truth JSON files define expected extractions per document
2. The chain runs against fixture documents (real LLM calls)
3. Scoring functions compare outputs against ground truth
4. Results are session-scoped (LLM calls run once, reused across tests)

**Eval fixtures (`evals/conftest.py`):**
```python
@pytest.fixture(scope="session", autouse=True)
def init_env():
    """Load SSM/env configuration once before any tests run."""
    from src.app.config.environment import initialize_environment_sync
    initialize_environment_sync()

@pytest.fixture(scope="session")
def extraction_results(chain) -> dict:
    """Run extraction on all 8 documents and cache the DocumentSummary objects."""
    async def _run_all():
        results = {}
        for doc_name in DOC_NAMES:
            doc = _load_document(doc_name)
            summaries = await chain._extract_batch([doc], 1, 1)
            results[doc_name] = summaries[0] if summaries else None
        return results
    return asyncio.run(_run_all())
```

**Scoring dimensions (`evals/scoring/types.py`):**

| Dimension | Weight | Threshold | What it measures |
|-----------|--------|-----------|------------------|
| completeness | 0.20 | 0.85 | Expected items present in output |
| accuracy | 0.20 | 0.85 | No fabricated items beyond ground truth |
| hallucination | 0.15 | 0.90 | Trap items NOT appearing in output |
| medication_filtering | 0.15 | 0.95 | Non-drugs excluded from medications |
| patient_language | 0.10 | 0.80 | Abbreviations expanded, plain language |
| deduplication | 0.10 | 0.85 | No near-duplicate items in synthesis |
| clinical_summary | 0.10 | 0.75 | LLM-as-judge quality assessment |

**Eval test pattern (`evals/test_extraction.py`):**
```python
@pytest.mark.parametrize("doc_name", DOC_NAMES)
def test_extraction_completeness(doc_name, extraction_results, ground_truths):
    """Expected items must be present in output."""
    result = extraction_results.get(doc_name)
    gt = ground_truths[doc_name]
    # ... score and assert overall >= 0.85
```

**Standalone eval runner (`evals/run_eval.py`):**
```bash
uv run python evals/run_eval.py v001           # Run all cases for prompt v001
uv run python evals/run_eval.py v002 --log      # Run and log to experiments.tsv
uv run python evals/run_eval.py v003 --cases lab_report_cbc,diabetes_followup  # Subset
```

Output: JSON report to `evals/results/{version}_{timestamp}.json`

**Prompt versioning:** Prompts live in `evals/prompts/v001/`, `v002/`, `v003/`. Each version has `extraction_prompt.txt` and `synthesis_prompt.txt`. The active version is tracked in `evals/prompts/current.json`.

## Mocking

**Framework:** `unittest.mock` (standard library)

**Patterns used:**
```python
from unittest.mock import patch, MagicMock

@pytest.fixture
def mock_intent_identifier():
    with patch("src.app.routes.ai-chat.IntendIdentifierChain") as mock:
        instance = mock.return_value
        instance.identify_intent.return_value = "medical_inquiry"
        yield instance
```

**What to mock:**
- LLM chains (`IntendIdentifierChain`, `TranscriptSummarizationChain`)
- Redis client
- Database sessions (for unit tests)

**What NOT to mock (in evals):**
- LLM calls are real in the eval framework (that is the point)
- Ground truth comparisons use fuzzy matching, not exact

## Coverage

**Configuration:** Coverage enabled by default via `pytest.ini` (`--cov=src/app`).

**Current state:** Extremely low. Only 2 test files exist with 4 test functions total:
- `test_health.py`: 1 test (health endpoint)
- `test_chat.py`: 3 tests (chat endpoint, likely broken due to wrong module path in patches)

**Untested areas (critical gaps):**
- All summarization services (`src/app/services/summarization/`)
- All route handlers except health and chat
- Repository layer (`src/app/db/objects/repositories/`)
- Chain logic (`src/app/chains/`) - only covered by evals, not unit tests
- Middleware (`src/app/common/middleware/`)
- Redis caching (`src/app/cache/redis.py`)
- Configuration loading (`src/app/config/`)
- Error handlers (`src/app/common/exception_handlers.py`)
- Scheduler (`src/app/core/scheduler.py`)

## Test Types

**Unit Tests (`src/app/tests/unit/`):**
- Scope: Individual endpoint responses
- Approach: FastAPI `TestClient` with mocked dependencies
- Status: Minimal (2 files, likely partially broken)

**Integration Tests (`src/app/tests/integration/`):**
- Status: Directory exists but is empty

**E2E Tests:**
- Not present

**AI Evaluation Tests (`evals/`):**
- Scope: LLM output quality for attachment summarization
- Approach: Ground truth comparison with fuzzy matching and weighted scoring
- Status: Well-developed with 8 extraction cases and 2 synthesis cases
- Makes real LLM API calls (requires OpenAI API key via SSM)

## Common Patterns

**Async testing:**
```python
# pytest-asyncio with asyncio_mode = auto means async tests work automatically
async def test_async_operation():
    result = await some_async_function()
    assert result is not None
```

**Parametrized eval tests:**
```python
@pytest.mark.parametrize("doc_name", DOC_NAMES)
def test_extraction_completeness(doc_name, extraction_results, ground_truths):
    result = extraction_results.get(doc_name)
    gt = ground_truths[doc_name]
    assert overall >= 0.85, f"[{doc_name}] Completeness {overall:.2f} < 0.85"
```

## Key Observations

1. **Traditional test coverage is critically low.** Only 4 test functions exist for the entire application. The eval framework covers LLM quality but not application logic, error handling, or database operations.

2. **Test infrastructure has bugs.** The `test_chat.py` patches use a module path with a hyphen (`ai-chat`) which is not a valid Python identifier. The `conftest.py` uses synchronous `engine` for database setup but the app uses `AsyncEngine`.

3. **Eval framework is well-designed.** The scoring system with weighted dimensions, threshold-based pass/fail, ground truth fixtures, and versioned prompts is production-quality.

4. **No test database isolation.** The `conftest.py` attempts to create/drop tables on the real database engine. There is no test database configuration or SQLite fallback.

5. **Missing test infrastructure for services.** There are no fixtures for creating service instances with mocked DB sessions, no factory functions for test data, and no helpers for creating test requests.

6. **Eval tests require real credentials.** The eval framework calls `initialize_environment_sync()` which loads SSM parameters. These tests cannot run without AWS credentials and an OpenAI API key.
