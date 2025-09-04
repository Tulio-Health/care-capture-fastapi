# Care Capture GenAI API

API for Care Capture AI - Making healthcare patient data more meaningful for patients and caregivers!!!

This API is based on Python Fast API

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
care-capture-ai/
├── src/
│   └── app/
│       ├── main.py
│       ├── routes/
│       └── models/
├── pyproject.toml
├── README.md
└── .gitignore
```

## Dependencies

All dependencies are managed by Poetry. See `pyproject.toml` for details.

## Contributing

1. Create a new branch
2. Make your changes
3. Run tests and formatting
4. Submit a pull request

## License

[Add your license information here]

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

Currently documented endpoints:

- `GET /`: Root endpoint
  - Returns a welcome message for the Care Capture AI API
- `GET /health`: Health check endpoint
  - Returns the current health status of the service
- `POST /care-capture/users/{user_id}/health_insights`: Create user health insights
  - Creates/Updates health insights for a specific user
  - Sample request:
    ```bash
    curl --location --request POST 'http://localhost:8000/care-capture/users/ae163cd0-89c9-4ed6-9073-8e155cff6eb1/health_insights' \
    --header 'Content-Type: application/json' \
    --data '{
        "user_id":"ae163cd0-89c9-4ed6-9073-8e155cff6eb1"
    }'
    ```
- `POST /care-capture/provider_visit_summarization`: Summarize provider visit
  - Creates a summary of the provider visit from transcript
  - Sample request:
    ```bash
    curl --location --request POST 'http://localhost:8000/care-capture/provider_visit_summarization' \
    --header 'Content-Type: application/json' \
    --data '{
        "transcript_id": "ae163cd0-89c9-4ed6-9073-8e155cff6eb2",
        "user_id": "ae163cd0-89c9-4ed6-9073-8e155cff6eb1",
        "text": "You are completely healthy"
    }'
    ```
- `POST /care-capture/users/{user_id}/health_insights`: Create user health insights
  - Creates/Updates health insights for a specific user
  - Sample request:
    ```bash
    curl --location --request POST 'http://localhost:8000/care-capture/users/ae163cd0-89c9-4ed6-9073-8e155cff6eb1/health_insights' \
    --header 'Content-Type: application/json' \
    --data '{
        "user_id":"ae163cd0-89c9-4ed6-9073-8e155cff6eb1"
    }'
    ```

  - 

  
