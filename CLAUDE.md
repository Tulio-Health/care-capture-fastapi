# Care Capture FastAPI - Configuration Guide

## Overview
This FastAPI application has been migrated to use AWS Systems Manager (SSM) Parameter Store for configuration management, similar to the NodeAPI implementation. The application loads configuration from SSM at startup when running in AWS or when explicitly enabled for local development.

## Architecture

### Parameter Storage
- **AWS SSM Parameter Store**: `/tuliohealth/{environment}/{service}/{parameter}`  
- **Environment Detection**: Automatic SSM loading in AWS App Runner, optional for local development
- **Local Override**: Redis automatically switched to localhost for local development

### Environment-Specific Configuration

| Environment | Database | Redis | SSM Parameters | Config Loading |
|-------------|----------|-------|---------------|----------------|
| **Local Dev** | AWS RDS Dev | Local Redis (127.0.0.1:6379) | `/tuliohealth/dev/*` | Direct SSM connection |
| **AWS Dev** | AWS RDS Dev | AWS ElastiCache Dev | `/tuliohealth/dev/*` | Runtime SSM loading |
| **AWS Prod** | AWS RDS Prod | AWS ElastiCache Prod | `/tuliohealth/prod/*` | Runtime SSM loading |

## Local Development Setup

### Prerequisites
- AWS CLI configured with credentials
- Local Redis server running on port 6379  
- Python 3.12+ and Poetry installed

### Environment Configuration
The `.env.development` file is already configured:
```bash
NODE_ENV=development
AWS_REGION=us-east-2
USE_SSM_LOCALLY=true
PORT=8000
DEBUG=true
```

### Start Development Server
```bash
# Install dependencies
poetry install

# Start with SSM parameter loading
poetry run python -m uvicorn src.app.main:app --host 0.0.0.0 --port 8000 --reload

# Alternative using the main function
poetry run python src/app/main.py
```

The application will:
1. Load all required parameters from AWS SSM Parameter Store
2. Override Redis to use local instance (127.0.0.1:6379)
3. Connect to AWS dev database with SSM credentials
4. Start server on port 8000

## SSM Parameters Used by FastAPI

### Current Parameters (10 total)
```
/tuliohealth/dev/
├── database/
│   ├── host         → DB_HOST
│   ├── port         → DB_PORT  
│   ├── username     → DB_USER
│   ├── password     → DB_PASSWORD
│   ├── name         → DB_NAME
│   └── ssl          → DB_SSL
├── redis/
│   ├── host         → REDIS_HOST
│   ├── port         → REDIS_PORT
│   └── password     → REDIS_PASSWORD
└── openai/
    └── api_key      → OPENAI_API_KEY
```

### Local Environment Variables
These are loaded from `.env.development` and not from SSM:
- `LANGSMITH_TRACING`
- `LANGSMITH_ENDPOINT` 
- `LANGSMITH_PROJECT`
- `LANGSMITH_API_KEY`

## Key Files

### Configuration Loading
- `src/app/config/environment.py` - Environment setup and SSM initialization
- `src/app/config/ssm_loader.py` - SSM Parameter Store integration
- `src/app/core/settings.py` - Application settings with SSM support
- `.env.development` - Local development configuration

### Application Entry Points
- `src/app/main.py` - FastAPI application with SSM integration
- `src/app/main.py:main()` - Development server entry point

## Adding New Parameters

### 1. Add to SSM Parameter Store
```bash
aws ssm put-parameter \\
  --name "/tuliohealth/dev/service/new_param" \\
  --value "parameter_value" \\
  --type "String" \\
  --description "Description of parameter"
```

### 2. Update Parameter Mapping
Edit `src/app/config/ssm_loader.py` and add to `get_parameter_mappings()`:
```python
SSMParameterMapping('service/new_param', 'NEW_PARAM', is_secure=False)
```

### 3. Update Settings
Add the new parameter to `src/app/core/settings.py`:
```python
NEW_PARAM: str = ""
```

## Development Commands

```bash
# Start development server with SSM
poetry run python -m uvicorn src.app.main:app --host 0.0.0.0 --port 8000 --reload

# Check Redis connection (ensure local Redis is running)
redis-cli ping

# Test database connection
psql -h dev-db-carecapture-ai.cbyowmas6qgt.us-east-2.rds.amazonaws.com -U postgresadmin -d care-capture-app-dev

# List SSM parameters
aws ssm describe-parameters --query "Parameters[?contains(Name, 'tuliohealth/dev')]"

# Test SSM parameter loading
poetry run python -c "
import asyncio
import sys
sys.path.append('src')
from src.app.config.ssm_loader import load_ssm_configuration
asyncio.run(load_ssm_configuration())
"
```

## Troubleshooting

### Common Issues

**SSM Parameters Not Loading**
```bash
# Check if parameters exist
aws ssm describe-parameters --query "Parameters[?contains(Name, 'tuliohealth')]"

# Test parameter retrieval  
aws ssm get-parameter --name "/tuliohealth/dev/database/host" --with-decryption
```

**Database Connection Errors**
- Verify database password in SSM: `/tuliohealth/dev/database/password`
- Check if RDS security groups allow connections
- Confirm database endpoint is accessible

**Redis Connection Timeout**
- Local dev: Ensure Redis is running (`redis-cli ping`)
- AWS: Check ElastiCache security groups and VPC configuration

## Migration Benefits

**Before**: Manual environment variable management  
**After**: Automatic SSM parameter loading with local development support

**Benefits**:
- ✅ Consistent configuration with NodeAPI
- ✅ Centralized parameter management
- ✅ Environment-specific parameter isolation
- ✅ Local development with AWS resources
- ✅ Automatic Redis localhost override for development