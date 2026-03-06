# Service Layer Architecture

## Overview

The Care Capture FastAPI application follows a **layered architecture** with clear separation of concerns, adhering to **SOLID principles** for maintainability, testability, and scalability.

---

## Architecture Layers

```
┌─────────────────────────────────────────────────────────────┐
│                        HTTP Layer                            │
│                    (routes/care_capture.py)                  │
│                                                              │
│  - Request validation (Pydantic)                            │
│  - Response formatting                                       │
│  - HTTP status codes                                         │
│  - API documentation (OpenAPI)                              │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                      Service Layer                           │
│              (services/summarization/*.py)                   │
│                                                              │
│  - Business logic                                           │
│  - AI orchestration                                         │
│  - Data transformation                                      │
│  - Error handling                                           │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                    Repository Layer                          │
│          (db/repositories/conversation_summaries.py)         │
│                                                              │
│  - Database operations (CRUD)                               │
│  - Query building                                           │
│  - Transaction management                                   │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                       Data Layer                             │
│              (db/objects/entities/*.py)                      │
│                                                              │
│  - SQLAlchemy entities                                      │
│  - Database schema mapping                                  │
└─────────────────────────────────────────────────────────────┘
```

---

## Service Layer Details

### Services Directory Structure

```
src/app/services/
└── summarization/
    ├── __init__.py                          # Module exports
    ├── transcript_summarization.py          # Transcript → Summary
    ├── playground_summarization.py          # Plain text → Summary
    ├── fhir_analysis.py                     # FHIR data → Summary
    └── comprehensive_summarization.py       # Orchestrator (parallel)
```

### Service Responsibilities

| Service | Responsibility | Input | Output |
|---------|---------------|-------|--------|
| **TranscriptSummarizationService** | Convert transcripts to summaries | Transcripts | ConversationSummary |
| **PlaygroundSummarizationService** | Summarize plain text | Plain text | ConversationSummary |
| **FhirAnalysisService** | Analyze FHIR clinical data | Appointment ID | ConversationSummary |
| **ComprehensiveSummarizationService** | Orchestrate parallel operations | Combined request | Multiple summaries |

---

## SOLID Principles Applied

### 1. Single Responsibility Principle (SRP)

**Each class has one reason to change:**

```python
# ❌ BEFORE: Route handler doing everything
@router.post("/transcript-summarization")
async def summarize_transcript(...):
    # Validate input
    # Call OpenAI
    # Format data
    # Save to database
    # Handle errors
    # Return response
    pass

# ✅ AFTER: Clear separation
@router.post("/transcript-summarization")  # HTTP handling only
async def summarize_transcript(...):
    return await TranscriptSummarizationService(db).summarize_transcript(request)

class TranscriptSummarizationService:     # Business logic only
    async def summarize_transcript(...): pass
    
class ConversationSummariesRepository:    # Database operations only
    async def upsert(...): pass
```

### 2. Open/Closed Principle (OCP)

**Open for extension, closed for modification:**

```python
# ✅ Adding new summarization type
class NewSummarizationType(BaseService):
    async def summarize(...):
        # New implementation
        pass

# ✅ No need to modify existing services
# ✅ Just add new task to orchestrator
class ComprehensiveSummarizationService:
    async def _build_task_list(self, request):
        tasks = []
        if request.transcripts:
            tasks.append(self._run_transcript_summarization(request))
        if request.include_fhir_analysis:
            tasks.append(self._run_fhir_analysis(request))
        # ✅ Easy to add: if request.include_new_type: tasks.append(...)
        return tasks
```

### 3. Liskov Substitution Principle (LSP)

**All services follow the same contract:**

```python
# All services return ConversationSummary
class BaseService:
    async def process(self, request) -> ConversationSummary:
        pass

class TranscriptSummarizationService(BaseService):
    async def summarize_transcript(self, ...) -> ConversationSummary:
        pass

class FhirAnalysisService(BaseService):
    async def analyze_fhir_resources(self, ...) -> ConversationSummary:
        pass

# ✅ Can be used interchangeably
services = [TranscriptSummarizationService, FhirAnalysisService]
for service in services:
    result = await service(db).process(request)  # Same interface
```

### 4. Interface Segregation Principle (ISP)

**Services only expose what they need:**

```python
# ✅ TranscriptSummarizationService only needs:
class TranscriptSummarizationService:
    def __init__(self, db: AsyncSession):
        self.repository = ConversationSummariesRepository(db)
    
    async def summarize_transcript(self, request):
        # Only depends on what it uses
        pass

# ✅ FhirAnalysisService has different dependencies:
class FhirAnalysisService:
    def __init__(self, db: AsyncSession):
        self.repository = ConversationSummariesRepository(db)
        self.fhir_client = FHIRClient()
    
    async def analyze_fhir_resources(self, request):
        # Different dependencies for different needs
        pass
```

### 5. Dependency Inversion Principle (DIP)

**Depend on abstractions, not concretions:**

```python
# ✅ Services depend on repository interface
class TranscriptSummarizationService:
    def __init__(self, db: AsyncSession):
        self.repository = ConversationSummariesRepository(db)
        # Depends on abstraction (repository), not direct DB access

# ✅ Easy to mock for testing
class MockRepository:
    async def upsert(self, ...):
        return mock_data

service = TranscriptSummarizationService(mock_db)
service.repository = MockRepository()  # Inject mock
```

---

## Data Flow

### Simple Request Flow

```
1. HTTP Request
   POST /care-capture/transcript-summarization
   ↓
2. Route Handler (care_capture.py)
   - Validate request with Pydantic
   - Extract parameters
   ↓
3. Service (TranscriptSummarizationService)
   - Validate business rules
   - Call AI (OpenAI)
   - Transform data
   ↓
4. Repository (ConversationSummariesRepository)
   - Build SQL query
   - Execute upsert
   - Commit transaction
   ↓
5. Response
   Return ConversationSummary
```

### Parallel Request Flow

```
1. HTTP Request
   POST /care-capture/comprehensive-summary
   ↓
2. Route Handler (care_capture.py)
   - Validate request
   ↓
3. Orchestrator (ComprehensiveSummarizationService)
   - Build task list
   - Execute tasks in parallel with asyncio.gather()
   ↓
4a. Transcript Service            4b. FHIR Service
    - Validate transcripts             - Fetch appointment
    - Generate summary                 - Fetch FHIR data
    - Save to DB                       - Generate summary
                                       - Save to DB
   ↓                                ↓
5. Orchestrator
   - Collect results
   - Separate successes from failures
   - Calculate metrics
   ↓
6. Response
   Return {summaries[], errors[], metrics{}}
```

---

## Error Handling Strategy

### Error Propagation

```python
┌─────────────────────────────────────┐
│  Route Handler                      │
│  - Catch HTTPException              │
│  - Return appropriate status code   │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  Service Layer                      │
│  - Catch business logic errors      │
│  - Transform to HTTPException       │
│  - Log errors with context          │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  Repository Layer                   │
│  - Catch database errors            │
│  - Rollback transactions            │
│  - Raise service-level exceptions   │
└─────────────────────────────────────┘
```

### Error Types by Layer

| Layer | Error Type | Example | Handling |
|-------|------------|---------|----------|
| **Route** | `HTTPException` | 404, 422, 500 | Return HTTP status |
| **Service** | `ValueError`, `HTTPException` | Validation, business rules | Log + raise HTTP |
| **Repository** | `SQLAlchemyError` | DB connection, constraint | Log + raise service error |
| **External** | `OpenAI.error`, `RequestException` | API failures | Retry + fallback |

### Comprehensive Service Error Handling

```python
# Parallel execution with error isolation
try:
    results = await asyncio.wait_for(
        asyncio.gather(*tasks, return_exceptions=True),
        timeout=request.timeout_seconds
    )
except asyncio.TimeoutError:
    # Log timeout, return partial results if any
    errors.append(build_timeout_error())
except Exception as e:
    # Unexpected error, log and return error response
    logger.error(f"Unexpected error: {e}")
    errors.append(build_unexpected_error(e))

# Process results
for result in results:
    if isinstance(result, Exception):
        # One service failed, but others may have succeeded
        errors.append(build_error_from_exception(result))
    else:
        # Service succeeded
        summaries.append(result)

# Return partial success if applicable
return ComprehensiveSummarizationResponse(
    transcript_summary=transcript_summary,
    fhir_summary=fhir_summary,
    errors=errors,
    metrics=build_metrics(transcript_summary, fhir_summary, errors)
)
```

---

## Transaction Management

### Separate Transactions Per Service

Each service manages its own database transaction:

```python
# Service 1
class TranscriptSummarizationService:
    async def summarize_transcript(self, request):
        # Uses injected DB session
        summary_data = await self._generate_summary(request)
        result = await self.repository.upsert(
            request.appointment_id, 
            summary_data
        )
        # Transaction commits when service completes
        return result

# Service 2 (independent transaction)
class FhirAnalysisService:
    async def analyze_fhir_resources(self, request):
        # Uses injected DB session
        summary_data = await self._run_ai_analysis(request)
        result = await self.repository.upsert(
            request.appointment_id,
            summary_data
        )
        # Transaction commits independently
        return result
```

### Benefits of Separate Transactions

✅ **Isolation**: One service's failure doesn't rollback the other  
✅ **Partial Success**: Can return successful results even if one fails  
✅ **Simpler Logic**: No distributed transaction coordination needed  
✅ **Better Performance**: Parallel commits vs sequential

---

## Testing Strategy

### Unit Testing (Per Layer)

```python
# Test service layer (mock repository)
class TestTranscriptSummarizationService:
    async def test_summarize_transcript(self):
        # Arrange
        mock_db = AsyncMock()
        mock_repository = AsyncMock()
        service = TranscriptSummarizationService(mock_db)
        service.repository = mock_repository
        
        # Act
        result = await service.summarize_transcript(mock_request)
        
        # Assert
        assert result.summary_text is not None
        mock_repository.upsert.assert_called_once()

# Test repository layer (mock database)
class TestConversationSummariesRepository:
    async def test_upsert(self):
        # Use in-memory SQLite for testing
        async with async_session() as session:
            repo = ConversationSummariesRepository(session)
            result = await repo.upsert(appointment_id, summary_data)
            assert result.id is not None
```

### Integration Testing

```python
# Test full flow with test database
class TestComprehensiveSummarization:
    async def test_parallel_execution(self):
        # Use test database
        async with test_db_session() as session:
            # Make real HTTP request to endpoint
            response = await client.post(
                "/care-capture/comprehensive-summary",
                json=test_request_data
            )
            
            # Verify database state
            summaries = await session.execute(
                select(ConversationSummary)
                .where(ConversationSummary.appointment_id == test_id)
            )
            
            assert len(summaries) == 2
            assert {s.metadata['source'] for s in summaries} == {'transcript', 'fhir_analysis'}
```

### Mocking External Services

```python
# Mock OpenAI
@patch('openai.ChatCompletion.create')
async def test_with_mock_openai(mock_openai):
    mock_openai.return_value = {
        'choices': [{'message': {'content': 'Mock summary'}}]
    }
    
    service = TranscriptSummarizationService(mock_db)
    result = await service.summarize_transcript(request)
    
    assert result.summary_text == 'Mock summary'
```

---

## Performance Considerations

### Parallel Execution Benefits

```python
# Sequential (old approach)
transcript_time = 2.5s
fhir_time = 4.8s
total_time = 7.3s  # Sequential

# Parallel (new approach)
total_time = max(2.5s, 4.8s) + 0.5s overhead = 5.3s
improvement = (7.3 - 5.3) / 7.3 = 27.4% faster
```

### Resource Usage

| Resource | Sequential | Parallel | Notes |
|----------|-----------|----------|-------|
| **CPU** | 1 core at a time | 2 cores simultaneously | Higher utilization |
| **Memory** | Single context | Two contexts | ~2x memory |
| **Database** | 1 connection | 2 connections | Connection pool handles |
| **API Calls** | Sequential | Parallel | Faster overall |

### Optimization Opportunities

1. **Caching**: Cache FHIR data for repeated requests
2. **Batching**: Process multiple appointments in parallel
3. **Streaming**: Stream AI responses for faster TTFB
4. **Connection Pooling**: Reuse database connections
5. **Async I/O**: Non-blocking operations throughout

---

## Service Communication Patterns

### 1. Orchestration (Current Implementation)

```python
# Orchestrator coordinates multiple services
class ComprehensiveSummarizationService:
    async def execute(self, request):
        # Orchestrator controls flow
        results = await asyncio.gather(
            transcript_service.process(request),
            fhir_service.process(request)
        )
        return aggregate(results)
```

**Pros:**
- ✅ Centralized control
- ✅ Easy to understand
- ✅ Simple error handling

**Cons:**
- ❌ Orchestrator knows about all services
- ❌ Tight coupling to service interfaces

### 2. Event-Driven (Future Enhancement)

```python
# Services publish events
class TranscriptSummarizationService:
    async def summarize(self, request):
        result = await self._generate_summary(request)
        await event_bus.publish('summary.created', result)
        return result

# Other services subscribe to events
class NotificationService:
    @subscribe('summary.created')
    async def on_summary_created(self, event):
        await send_notification(event.data)
```

**Pros:**
- ✅ Loose coupling
- ✅ Easy to add new subscribers
- ✅ Scalable

**Cons:**
- ❌ More complex
- ❌ Harder to trace flow
- ❌ Eventual consistency

---

## Scalability Considerations

### Horizontal Scaling

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  App Server  │     │  App Server  │     │  App Server  │
│   Instance 1 │     │   Instance 2 │     │   Instance 3 │
└──────┬───────┘     └──────┬───────┘     └──────┬───────┘
       │                    │                    │
       └────────────────────┼────────────────────┘
                            │
                    ┌───────▼────────┐
                    │  Load Balancer │
                    └────────────────┘
```

**Service layer benefits:**
- ✅ Stateless services
- ✅ Independent scaling
- ✅ No shared state

### Database Scaling

```
┌─────────────────────────────────────┐
│         Application Layer            │
└────────────┬────────────────────────┘
             │
    ┌────────┴─────────┐
    ▼                  ▼
┌─────────┐      ┌─────────┐
│ Primary │      │ Replica │
│   DB    │─────▶│   DB    │
└─────────┘      └─────────┘
  (Writes)         (Reads)
```

**Repository layer enables:**
- ✅ Read/write splitting
- ✅ Query optimization
- ✅ Connection pooling

---

## Security Considerations

### Input Validation

```python
# Layer 1: Pydantic (schema validation)
class ComprehensiveSummarizationRequest(BaseModel):
    appointment_id: UUID  # Type validation
    timeout_seconds: int = Field(ge=10, le=300)  # Range validation

# Layer 2: Service (business rules)
class TranscriptSummarizationService:
    async def _validate_input_text(self, text: str):
        if len(text) > 100000:
            raise ValueError("Text too long")
        if not text.strip():
            raise ValueError("Empty text")
```

### Authentication & Authorization

```python
# Route layer handles auth
@router.post("/comprehensive-summary")
async def comprehensive_summary(
    request: ComprehensiveSummarizationRequest,
    current_user: User = Depends(get_current_user)  # Auth check
):
    # Service layer doesn't need to know about auth
    return await service.execute(request)
```

### Data Sanitization

```python
# Service layer sanitizes before storing
class TranscriptSummarizationService:
    def _prepare_summary_data(self, summary: str) -> dict:
        return {
            "summary_text": sanitize_html(summary),  # Remove HTML
            "metadata": {
                "source": "transcript",
                # Never store sensitive data in metadata
            }
        }
```

---

## Logging & Monitoring

### Structured Logging

```python
import structlog

logger = structlog.get_logger()

class TranscriptSummarizationService:
    async def summarize_transcript(self, request):
        logger.info(
            "Starting transcript summarization",
            appointment_id=str(request.appointment_id),
            transcript_count=len(request.transcripts)
        )
        
        try:
            result = await self._generate_summary(request)
            logger.info(
                "Summarization successful",
                appointment_id=str(request.appointment_id),
                summary_length=len(result.summary_text)
            )
            return result
        except Exception as e:
            logger.error(
                "Summarization failed",
                appointment_id=str(request.appointment_id),
                error=str(e),
                exc_info=True
            )
            raise
```

### Metrics Collection

```python
# Track execution time
from prometheus_client import Histogram

summarization_duration = Histogram(
    'summarization_duration_seconds',
    'Time spent in summarization',
    ['service_type']
)

class TranscriptSummarizationService:
    async def summarize_transcript(self, request):
        with summarization_duration.labels('transcript').time():
            return await self._generate_summary(request)
```

---

## Migration Path

### From Monolithic to Service Layer

**Step 1: Extract Service**
```python
# Before: Everything in route
@router.post("/endpoint")
async def handler(...):
    # 200 lines of logic
    pass

# After: Service extracted
class NewService:
    async def process(...):
        # 200 lines moved here
        pass

@router.post("/endpoint")
async def handler(...):
    return await NewService(db).process(request)
```

**Step 2: Add Tests**
```python
# Now easy to test
class TestNewService:
    async def test_process(self):
        service = NewService(mock_db)
        result = await service.process(mock_request)
        assert result is not None
```

**Step 3: Refactor**
```python
# Break into smaller methods
class NewService:
    async def process(self, request):
        validated = self._validate(request)
        result = await self._execute(validated)
        return self._format(result)
```

---

## Best Practices

### ✅ DO

- ✅ Keep services focused on single responsibility
- ✅ Inject dependencies (DB session, clients)
- ✅ Return domain models (ConversationSummary)
- ✅ Log at service boundaries
- ✅ Handle errors at appropriate layer
- ✅ Write unit tests for each service
- ✅ Use type hints everywhere

### ❌ DON'T

- ❌ Access database directly from routes
- ❌ Put business logic in route handlers
- ❌ Let services know about HTTP details
- ❌ Create circular dependencies between services
- ❌ Ignore errors (always handle or propagate)
- ❌ Mix concerns (validation, logic, persistence)

---

## Related Documentation

- [Comprehensive Summarization](./COMPREHENSIVE_SUMMARIZATION.md) - Endpoint details
- [Metadata Implementation](./METADATA_IMPLEMENTATION.md) - Data structure
- [Breaking Changes Analysis](./BREAKING_CHANGES_ANALYSIS.md) - Compatibility
- [API Examples](./API_EXAMPLES.md) - Usage examples

---

## Future Enhancements

### Potential Improvements

1. **Event-Driven Architecture**
   - Add event bus for loose coupling
   - Subscribe to summary creation events

2. **Caching Layer**
   - Cache FHIR data for repeated requests
   - Redis-based summary caching

3. **Rate Limiting**
   - Per-user rate limits
   - Per-endpoint throttling

4. **Batch Processing**
   - Process multiple appointments in parallel
   - Background job processing

5. **Observability**
   - Distributed tracing (OpenTelemetry)
   - Better metrics (Prometheus)
   - Centralized logging (ELK stack)

6. **Advanced Error Recovery**
   - Automatic retry with exponential backoff
   - Circuit breaker pattern
   - Fallback strategies
