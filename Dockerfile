# syntax=docker/dockerfile:1
# The syntax directive (must be line 1) pins the stable BuildKit Dockerfile frontend:
# the offline-load proof below uses `RUN --network=none`, stable since dockerfile
# syntax 1.3 (BuildKit 0.9, 2021). `docker build` has defaulted to BuildKit since
# Docker Engine 23; the legacy builder fails LOUDLY on the flag (never silently).
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

# Bake the o200k_base tokenizer encoding into the image so token-based chunk sizing
# performs ZERO network I/O at runtime (App Runner /tmp is per-instance-ephemeral; a
# first-use fetch of https://openaipublic.blob.core.windows.net/... in the chunking
# path is exactly the dependency this bake eliminates). ENV persists to runtime so the
# service reads this baked file.
ENV TIKTOKEN_CACHE_DIR=/app/.tiktoken
# The sha256 assertion is load-bearing: tiktoken does NOT fail closed on a corrupt
# cache -- check_hash() deletes the bad file and silently falls through to a runtime
# network re-download. Fail the BUILD instead. The expected sha256 is tiktoken's own
# hardcoded expected_hash for o200k_base (tiktoken_ext/openai_public.py); the cache
# filename is sha1 of the encoding's blob URL.
RUN /app/.venv/bin/python -c "\
import hashlib, os, tiktoken; \
enc = tiktoken.get_encoding('o200k_base'); \
assert enc.encode_ordinary('bake self-check'), 'encoder returned no tokens'; \
path = os.path.join(os.environ['TIKTOKEN_CACHE_DIR'], 'fb374d419588a4632f3f557e76b4b70aebbca790'); \
digest = hashlib.sha256(open(path, 'rb').read()).hexdigest(); \
assert digest == '446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d', 'corrupt tiktoken bake: ' + digest; \
print('tiktoken o200k_base baked OK:', path)"

# Offline-load proof (round-3 MAJOR-1). The assertion above cannot catch a corrupt
# cache on a NETWORKED build step: get_encoding() runs first, and on a hash mismatch
# tiktoken deletes the bad file and silently re-downloads it -- the assert then passes
# against the self-healed file with zero visibility that a network fetch occurred.
# This second step re-checks the hash BEFORE loading, then re-loads the ALREADY-BAKED
# encoding with network access disabled, so no self-heal is possible: any fetch
# attempt fails immediately inside the isolated network namespace. If this step
# passes, the image layer provably contains a loadable o200k_base cache and the
# runtime never needs the network for it.
RUN --network=none /app/.venv/bin/python -c "\
import hashlib, os, tiktoken; \
path = os.path.join(os.environ['TIKTOKEN_CACHE_DIR'], 'fb374d419588a4632f3f557e76b4b70aebbca790'); \
digest = hashlib.sha256(open(path, 'rb').read()).hexdigest(); \
assert digest == '446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d', 'baked cache corrupt at offline check: ' + digest; \
enc = tiktoken.get_encoding('o200k_base'); \
assert enc.encode_ordinary('offline self-check'), 'encoder returned no tokens offline'; \
print('tiktoken o200k_base loads OFFLINE from the baked cache')"

COPY src ./src

EXPOSE 8000

ENV PATH="/app/.venv/bin:$PATH"
CMD ["uvicorn", "src.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
