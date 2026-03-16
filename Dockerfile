FROM python:3.12-slim

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

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copy environment file
COPY ${ENV_FILE} .env

# Install dependencies (without dev group, skip building the project package itself)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src

EXPOSE 8000

ENV PATH="/app/.venv/bin:$PATH"
CMD ["uvicorn", "src.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
