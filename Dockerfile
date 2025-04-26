FROM python:3.9-slim

WORKDIR /app

COPY poetry.lock pyproject.toml ./

RUN pip install poetry && poetry install --no-root

# COPY fastapi_example ./fastapi_example
COPY src ./src

EXPOSE 8000

CMD ["poetry", "run", "uvicorn", "src.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
