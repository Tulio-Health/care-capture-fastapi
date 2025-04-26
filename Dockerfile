FROM python:3.12

# Build arguments
ARG APP_ENV
ARG DB_HOST
ARG DB_NAME
ARG DB_PASSWORD
ARG DB_PORT
ARG DB_SSL
ARG DB_USER
ARG PORT
ARG REDIS_HOST
ARG REDIS_PORT

# Environment variables
ENV APP_ENV=$APP_ENV
ENV DB_HOST=$DB_HOST
ENV DB_NAME=$DB_NAME
ENV DB_PASSWORD=$DB_PASSWORD
ENV DB_PORT=$DB_PORT
ENV DB_SSL=$DB_SSL
ENV DB_USER=$DB_USER
ENV PORT=$PORT
ENV REDIS_HOST=$REDIS_HOST
ENV REDIS_PORT=$REDIS_PORT

WORKDIR /app

COPY poetry.lock pyproject.toml ./

RUN pip install poetry && poetry install --no-root

# COPY fastapi_example ./fastapi_example
COPY src ./src

EXPOSE 8000

CMD ["poetry", "run", "uvicorn", "src.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
