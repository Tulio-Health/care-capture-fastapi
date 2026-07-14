---
name: poetry-to-uv-migration
description: >
  Migrate a Python project from Poetry to uv. Use when asked to switch package
  managers, when pyproject.toml still uses [tool.poetry], or when Dockerfile/CI
  still references poetry commands. Covers pyproject.toml rewrite, Dockerfile
  update, documentation sweep, and common pitfall avoidance.
category: devops-automation
---

# Poetry → uv Migration

## 1. pyproject.toml Conversion

### Build system (replace poetry-core with hatchling)
```toml
# Before
[build-system]
requires = ["poetry-core"]
build-backend = "poetry.core.masonry.api"

# After
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src"]   # adjust to match your source layout
```

### Project metadata (replace [tool.poetry] with [project])
```toml
# Before
[tool.poetry]
name = "my-app"
version = "0.1.0"
description = "..."
authors = ["Name <email>"]
readme = "README.md"

# After
[project]
name = "my-app"
version = "0.1.0"
description = "..."
authors = [{name = "Name", email = "email"}]
readme = "README.md"          # hatchling reads this — file MUST exist
requires-python = ">=3.12"
```

### Dependencies (version specifier translation)

| Poetry specifier | PEP 508 (uv) equivalent |
|-----------------|------------------------|
| `^1.2.3`        | `>=1.2.3,<2`           |
| `~1.2.3`        | `>=1.2.3,<1.3`         |
| `>=1.0,<2`      | `>=1.0,<2` (unchanged) |
| `*`             | no constraint (omit)   |

```toml
# Before
[tool.poetry.dependencies]
python = "^3.12"
fastapi = "^0.115"
httpx = "^0.27.0"

# After
[project]
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115.2,<0.116",
    "httpx>=0.27.0",
]
```

### Dev dependencies (replace groups with dependency-groups)
```toml
# Before
[tool.poetry.group.dev.dependencies]
pytest = "^8.0"

# After
[dependency-groups]
dev = [
    "pytest>=8.0.0,<9",
]
```

### Regenerate lockfile
```bash
uv lock          # create uv.lock
# Commit uv.lock — it should NOT be in .gitignore
# Delete poetry.lock if it exists
```

---

## 2. Dockerfile Update

### Install uv (official image pattern — fastest)
```dockerfile
# Copy uv binary from official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
```

### Install dependencies (avoid hatchling build during dep install)
```dockerfile
COPY pyproject.toml uv.lock ./
# --no-install-project: skips building the project package itself.
# This prevents hatchling from failing because README.md isn't copied yet.
RUN uv sync --frozen --no-dev --no-install-project
```

### Copy source and set CMD (critical: do NOT use `uv run`)
```dockerfile
COPY src ./src

# WRONG — uv run triggers hatchling project build at container start:
# CMD ["uv", "run", "uvicorn", "src.app.main:app", ...]

# CORRECT — use venv directly:
ENV PATH="/app/.venv/bin:$PATH"
CMD ["uvicorn", "src.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## 3. Common Pitfalls

| Pitfall | Symptom | Fix |
|---------|---------|-----|
| `readme = "README.md"` in pyproject.toml but file not copied | `OSError: Readme file does not exist` during `uv sync` | Add `--no-install-project` to sync step |
| `CMD ["uv", "run", "uvicorn", ...]` in Dockerfile | hatchling build failure at container start | Switch to `ENV PATH=/app/.venv/bin:$PATH` + `CMD ["uvicorn", ...]` |
| `httpx` upper-bound conflict with pydantic-ai | dependency resolution error | Relax to `>=0.27.0` (drop upper bound) |
| `poetry.lock` lingering in repo | confuses contributors | Delete it; remove from `.gitignore` (uv.lock is committed) |
| `uv run` in CI before `uv sync` | command not found | Always run `uv sync` first |

---

## 4. Documentation Sweep

Find all stale poetry references:
```bash
grep -r "poetry" --include="*.md" --include="*.yml" --include="*.sh" --include="*.toml" .
```

### CLI reference (old → new)

| Poetry command | uv equivalent |
|---------------|---------------|
| `poetry install` | `uv sync` |
| `poetry install --no-dev` | `uv sync --no-dev` |
| `poetry run <cmd>` | `uv run <cmd>` |
| `poetry shell` | not needed — just use `uv run` |
| `poetry add <pkg>` | `uv add <pkg>` |
| `poetry remove <pkg>` | `uv remove <pkg>` |
| `poetry update` | `uv lock --upgrade` |
| `poetry build` | `uv build` |

### Files to check
- [ ] `README.md` — setup + development sections
- [ ] `docs/` — any guide with install/run instructions
- [ ] `scripts/` — shell scripts with `poetry run`
- [ ] `.github/workflows/` — CI steps (usually only run `docker build`, no direct poetry)
- [ ] `.gitignore` — remove `poetry.lock` entry; uv.lock should be committed
- [ ] `.dockerignore` — add `poetry.lock` (in case it ever lingers); add `.claude/` `.serena/`

---

## 5. Verification Checklist

```bash
# 1. Dependencies install cleanly
uv sync

# 2. App starts locally
uv run uvicorn src.app.main:app --port 8000

# 3. Health check
curl localhost:8000/health

# 4. Build Docker/Podman image
echo "AWS_REGION=us-east-2" > .env.test
podman build --build-arg ENV_FILE=.env.test -t myapp:test .

# 5. Container starts uvicorn (will fail on DB/SSM without creds — that's OK)
podman run --rm myapp:test
# Look for: "Application startup complete" before any connection errors

# 6. No stale poetry refs
grep -r "poetry" --include="*.md" --include="*.yml" --include="*.sh" --include="*.toml" .

# Cleanup
rm .env.test
podman rmi myapp:test
```

### Reading container logs
- `SSM loading skipped - using existing environment configuration` → expected without AWS creds
- `Application startup complete` → uvicorn/Python layer works ✓
- `ConnectionRefusedError` on Redis/DB → expected without infrastructure ✓
- `OSError: Readme file does not exist` → missing `--no-install-project` in Dockerfile
- `Failed to build care-capture-ai` at container start → CMD still uses `uv run`, switch to venv PATH
