# Tulio - Care Capture GenAI API

API for Care Capture AI - Making healthcare patient data more meaningful for patients and caregivers!!!
This API is based on the Python FastAPI

This API is based on Python Fast API!

## Configuration

This application uses **AWS Systems Manager (SSM) Parameter Store** for centralized configuration management, eliminating the need for numerous GitHub secrets.

### GitHub Secrets Required (Only 2!)
- `FASTAPI_AWS_ROLE_ARN` - IAM role for AWS access
- `AWS_REGION` - AWS region (us-east-2)

### SSM Parameters Used
All sensitive configuration is stored in AWS SSM:
```
/tuliohealth/{env}/infrastructure/
├── fastapi_ecr_repository      → ECR repository name
└── fastapi_app_runner_service  → App Runner service name

/tuliohealth/{env}/database/
├── host, port, username, password, name, ssl

/tuliohealth/{env}/redis/
├── host, port, password

/tuliohealth/{env}/openai/
└── api_key
```

## Setup

1. Install Poetry if you haven't already:
```bash
curl -sSL https://install.python-poetry.org | python3 -
```

2. Clone the repository and install dependencies:
```bash
git clone <repository-url>
cd care-capture-fastapi
poetry install
```

3. Activate the virtual environment:
```bash
poetry shell
```

## Development

- Run the application:

```bash
poetry run uvicorn src.app.main:app --reload
#poetry run python main.py
```

- Run tests:
```bash
poetry run pytest
```

- Format code:
```bash
poetry run black .
poetry run isort .
```

## Project Structure

```
care-capture-fastapi/
├── src/
│   └── app/
│       ├── main.py                      # Application entry point
│       ├── routes/                      # HTTP endpoints
│       │   └── care_capture.py         # Care Capture API routes
│       ├── services/                    # Business logic layer
│       │   └── summarization/          # Summarization services
│       │       ├── transcript_summarization.py
│       │       ├── fhir_analysis.py
│       │       ├── playground_summarization.py
│       │       └── comprehensive_summarization.py
│       ├── models/                      # Pydantic models
│       │   ├── conversation_summaries.py
│       │   └── comprehensive_summarization.py
│       ├── db/                          # Database layer
│       │   ├── repositories/           # Data access layer
│       │   └── objects/entities/       # SQLAlchemy entities
│       └── core/                        # Core configuration
├── docs/                                # Documentation
│   ├── COMPREHENSIVE_SUMMARIZATION.md  # New endpoint guide
│   ├── ARCHITECTURE.md                 # Service layer architecture
│   ├── METADATA_IMPLEMENTATION.md      # Metadata usage
│   ├── BREAKING_CHANGES_ANALYSIS.md    # Compatibility info
│   └── API_EXAMPLES.md                 # Code examples
├── tests/                               # Test suite
├── pyproject.toml                       # Dependencies
└── README.md
```

### Architecture

This application follows a **layered architecture** with clear separation of concerns:

- **Routes Layer**: HTTP request/response handling
- **Services Layer**: Business logic and orchestration
- **Repository Layer**: Database operations
- **Models Layer**: Data validation and serialization

See [Architecture Documentation](./docs/ARCHITECTURE.md) for details.

## Dependencies

All dependencies are managed by Poetry. See `pyproject.toml` for details.

## Contributing

1. Create a new branch
2. Make your changes
3. Run tests and formatting
4. Submit a pull request

## License

[Add your license information here]

---

## Key Features

### 🚀 Service Layer Architecture

This API implements a clean **service layer architecture** following SOLID principles:

- **Single Responsibility**: Each service handles one specific domain
- **Dependency Injection**: Services receive dependencies (DB, clients) for easy testing
- **Error Isolation**: Failures in one service don't affect others
- **Testability**: Business logic separated from HTTP handling

### ⚡ Parallel Execution

The comprehensive summarization endpoint executes multiple AI operations in parallel:

- **37.5% faster** than sequential operations
- **Partial success support**: Returns successful results even if one operation fails
- **Timeout control**: Configurable per-request (10-300s)
- **Independent transactions**: Each service manages its own database transaction

### 🔍 Metadata Source Tracking

Summaries are tagged with `metadata.source` to distinguish their origin:

- `"transcript"` - Generated from conversation transcripts
- `"fhir_analysis"` - Generated from clinical FHIR data

This enables:
- **Multiple summaries per appointment**: One conversation summary + one clinical analysis
- **Source-based filtering**: Frontend can display summaries separately
- **Better analytics**: Track which summary types are most used

### 🛡️ Backward Compatible

All changes are **fully backward compatible**:

- ✅ No breaking changes to existing endpoints
- ✅ No database migrations required
- ✅ Existing clients work without modification
- ✅ NodeAPI already handles multiple summaries per appointment

See [Breaking Changes Analysis](./docs/BREAKING_CHANGES_ANALYSIS.md) for details.

---

## Documentation

### Comprehensive Guides

- **[Comprehensive Summarization](./docs/COMPREHENSIVE_SUMMARIZATION.md)** - New parallel execution endpoint
- **[Architecture](./docs/ARCHITECTURE.md)** - Service layer design and SOLID principles
- **[Metadata Implementation](./docs/METADATA_IMPLEMENTATION.md)** - Metadata usage and querying
- **[Breaking Changes Analysis](./docs/BREAKING_CHANGES_ANALYSIS.md)** - Compatibility information
- **[API Examples](./docs/API_EXAMPLES.md)** - Code examples in Python, TypeScript, JavaScript

### Quick Links

- **API Documentation (Swagger)**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`
- **OpenAPI Schema**: `http://localhost:8000/openapi.json`

---

## Recent Updates

### Version 1.X.0 (Latest)

**Added:**
- ✨ New endpoint: `POST /care-capture/comprehensive-summary`
  - Parallel execution of transcript and FHIR analysis
  - Configurable timeout and partial success support
- 🏗️ Service layer architecture for better code organization
- 🔍 Metadata source tracking for summary type distinction

**Changed:**
- ♻️ Internal refactoring: Extracted business logic into service layer
  - `POST /care-capture/transcript-summarization`
  - `POST /care-capture/fhir-analysis`
  - `POST /care-capture/playground-summarization`

**Migration Notes:**
- ✅ No breaking changes
- ✅ No database migrations required
- ✅ No client code changes required
- ℹ️ Optional: Frontend can enhance UX by filtering by `metadata.source`

---

## API Documentation

The API documentation is automatically generated using OpenAPI (Swagger) and is available through multiple interfaces:

### Swagger UI

Access the interactive API documentation at `http://your-server/docs`. This interface allows you to:

- To access in local - - Local - `http://localhost:8000/docs`
- Read detailed API documentation
- Test endpoints directly from the browser
- View request/response schemas
- See example responses

### ReDoc

A more readable version of the API documentation is available at `http://your-server/redoc`

- Local - `http://localhost:8000/redoc`

### OpenAPI Schema

The raw OpenAPI schema can be accessed at `http://your-server/openapi.json`

- Local - `http://localhost:8000/openapi.json`

### Available Endpoints

#### Core Endpoints

- **`GET /`**: Root endpoint
  - Returns a welcome message for the Care Capture AI API

- **`GET /health`**: Health check endpoint
  - Returns the current health status of the service

#### Summarization Endpoints

- **`POST /care-capture/comprehensive-summary`**: **✨ NEW - Parallel Execution**
  - Executes transcript summarization and FHIR analysis in parallel
  - Features:
    - ⚡ 37.5% faster than sequential operations
    - 🛡️ Partial success support (returns successful results even if one fails)
    - 🔍 Source tracking via `metadata.source` field
    - ⏱️ Configurable timeout (10-300s, default 120s)
  - See [Comprehensive Summarization Guide](./docs/COMPREHENSIVE_SUMMARIZATION.md)
  - Example:
    ```bash
    curl -X POST 'http://localhost:8000/care-capture/comprehensive-summary' \
      -H 'Content-Type: application/json' \
      -d '{
        "appointment_id": "123e4567-e89b-12d3-a456-426614174000",
        "user_id": "223e4567-e89b-12d3-a456-426614174000",
        "transcripts": [{
          "text": "Patient presents with persistent headache...",
          "language_code": "en"
        }],
        "include_fhir_analysis": true,
        "timeout_seconds": 120
      }'
    ```

- **`POST /care-capture/transcript-summarization`**: Transcript to summary
  - Converts conversation transcripts into medical summaries
  - Returns: `ConversationSummary` with `metadata.source = "transcript"`
  - Example:
    ```bash
    curl -X POST 'http://localhost:8000/care-capture/transcript-summarization' \
      -H 'Content-Type: application/json' \
      -d '{
        "appointment_id": "123e4567-e89b-12d3-a456-426614174000",
        "user_id": "223e4567-e89b-12d3-a456-426614174000",
        "transcripts": [{
          "text": "Patient presents with persistent headache for 3 days...",
          "language_code": "en"
        }]
      }'
    ```

- **`POST /care-capture/fhir-analysis`**: FHIR clinical data analysis
  - Analyzes FHIR resources (Conditions, Observations, Medications, etc.)
  - Returns: `ConversationSummary` with `metadata.source = "fhir_analysis"`
  - Example:
    ```bash
    curl -X POST 'http://localhost:8000/care-capture/fhir-analysis' \
      -H 'Content-Type: application/json' \
      -d '{
        "appointment_id": "123e4567-e89b-12d3-a456-426614174000",
        "user_id": "223e4567-e89b-12d3-a456-426614174000",
        "resource_types": ["Condition", "Observation", "MedicationRequest"],
        "analysis_focus": "chronic_conditions"
      }'
    ```

- **`POST /care-capture/playground-summarization`**: Plain text summarization
  - Summarizes plain text without appointment context
  - Useful for testing and experimentation

#### Health Insights

- **`POST /care-capture/users/{user_id}/health_insights`**: Create user health insights
  - Creates/Updates health insights for a specific user
  - Example:
    ```bash
    curl -X POST 'http://localhost:8000/care-capture/users/ae163cd0-89c9-4ed6-9073-8e155cff6eb1/health_insights' \
      -H 'Content-Type: application/json' \
      -d '{"user_id":"ae163cd0-89c9-4ed6-9073-8e155cff6eb1"}'
    ```
