FROM python:3.12

# Build arguments for version information
ARG API_VERSION=1.0.0-local
ARG BUILD_NUMBER=local
ARG BUILD_TIME
ARG GIT_COMMIT=local
ARG GIT_BRANCH=local

# Build argument for environment file
ARG ENV_FILE

# Set environment variables for runtime
ENV API_VERSION=${API_VERSION}
ENV BUILD_NUMBER=${BUILD_NUMBER}
ENV BUILD_TIME=${BUILD_TIME}
ENV GIT_COMMIT=${GIT_COMMIT}
ENV GIT_BRANCH=${GIT_BRANCH}

WORKDIR /app

# Copy environment file
COPY ${ENV_FILE} .env

COPY poetry.lock pyproject.toml ./

RUN pip install poetry && poetry install --no-root

# COPY fastapi_example ./fastapi_example
COPY src ./src

EXPOSE 8000

CMD ["poetry", "run", "uvicorn", "src.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
