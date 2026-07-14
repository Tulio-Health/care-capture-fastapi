---
name: investigate
description: Investigating production issues — missing data, errors, sync failures, translation issues across Care Capture services (Node API, EMR Connector, FastAPI). Trigger on questions like "why doesn't this appointment have a provider?", "why wasn't a summary generated?", "why did sync fail?"
allowed-tools: Bash(aws *), Bash(PGPASSWORD=* psql *), Bash(cat *), Bash(source *), Bash(echo *), Read, Write, Edit
---

# Care Capture Debug Skill

You are a debugging assistant for the Care Capture platform. Your job is to investigate production issues efficiently using the databases and cloud tooling below.

## Step 0: Load Session State

Before doing anything, check for cached session state:

```bash
# Check if session state exists (prod creds, user context)
cat .claude/debug-scratch/session-state.env 2>/dev/null
```

If the file exists, source it to avoid re-fetching SSM parameters:
```bash
source .claude/debug-scratch/session-state.env
```

If it does NOT exist, initialize it (see "Session State Management" below).

## Step 1: Gather Context

Before running any commands, ask the user for:
1. **Environment**: dev or prod? (default: dev)
2. **Issue category**: missing data | sync failure | translation | summary | provider | EHR connection | chatbot | other
3. **Identifiers**: user_id, appointment_id, email, or any relevant ID

If the user already provided this info in their question, skip asking and proceed.

## Step 2: Load Reference Files

Load only the reference files you need:
- **DB queries needed** → read `.claude/skills/investigate/references/db-schema.md` + `.claude/skills/investigate/references/common-queries.md`
- **CloudWatch logs needed** → read `.claude/skills/investigate/references/log-groups.md`
- **Cross-service trace** → read `.claude/skills/investigate/references/cross-service-flows.md`
- **Infrastructure/deployment issues** → read `.claude/skills/investigate/references/infra-health.md`

Also check agent memory for persistent schema knowledge:
```bash
cat .claude/agent-memory/db-schema-nodeapi.md 2>/dev/null
cat .claude/agent-memory/db-schema-emr.md 2>/dev/null
```

## Session State Management

Session state is stored in `.claude/debug-scratch/session-state.env`. This avoids re-calling SSM APIs and re-fetching DB credentials on every query.

### Initialize session state (run ONCE per session)

```bash
mkdir -p .claude/debug-scratch

# Fetch prod creds from SSM (only needed once)
PROD_HOST=$(aws ssm get-parameter --name "/tuliohealth/prod/database/host" --with-decryption --profile tuliodev --region us-east-2 --query Parameter.Value --output text)
PROD_DB=$(aws ssm get-parameter --name "/tuliohealth/prod/database/name" --with-decryption --profile tuliodev --region us-east-2 --query Parameter.Value --output text)
PROD_PASS=$(aws ssm get-parameter --name "/tuliohealth/prod/database/password" --with-decryption --profile tuliodev --region us-east-2 --query Parameter.Value --output text)
DEV_PASS=$(aws ssm get-parameter --name "/tuliohealth/dev/database/password" --with-decryption --profile tuliodev --region us-east-2 --query Parameter.Value --output text)

# Write session state
cat > .claude/debug-scratch/session-state.env << STATEEOF
# Auto-generated — do not commit
export PROD_HOST="$PROD_HOST"
export PROD_DB="$PROD_DB"
export PROD_PASS="$PROD_PASS"
export DEV_HOST="dev-db-carecapture-ai.cbyowmas6qgt.us-east-2.rds.amazonaws.com"
export DEV_DB="care-capture-app-dev"
export DEV_PASS="$DEV_PASS"
export DEV_EMR_DB="care-capture-emr-dev"
export PROD_EMR_DB="care-capture-emr-prod"
export AWS_PROFILE="tuliodev"
export AWS_REGION="us-east-2"
STATEEOF

echo "Session state initialized."
```

### Add user context to session (when investigating a specific user)

```bash
# Append user context — avoids re-typing user_id in every query
cat >> .claude/debug-scratch/session-state.env << STATEEOF
export USER_ID="<uuid>"
export USER_ENV="prod"  # or "dev"
STATEEOF
```

### Using session state in queries

After sourcing session-state.env, use the short-form helpers:

```bash
source .claude/debug-scratch/session-state.env

# Prod Node API query
PGPASSWORD="$PROD_PASS" psql -h "$PROD_HOST" -U postgresadmin -d "$PROD_DB" -c "<SQL>"

# Prod EMR query
PGPASSWORD="$PROD_PASS" psql -h "$PROD_HOST" -U postgresadmin -d "$PROD_EMR_DB" -c "<SQL>"

# Dev Node API query
PGPASSWORD="$DEV_PASS" psql -h "$DEV_HOST" -U postgresadmin -d "$DEV_DB" -c "<SQL>"

# Dev EMR query
PGPASSWORD="$DEV_PASS" psql -h "$DEV_HOST" -U postgresadmin -d "$DEV_EMR_DB" -c "<SQL>"
```

## Configuration

### AWS
```
Profile: tuliodev
Region:  us-east-2
```

### Database Hosts
```
Dev RDS:  dev-db-carecapture-ai.cbyowmas6qgt.us-east-2.rds.amazonaws.com
Prod RDS: (fetch from SSM once → session state)
User:     postgresadmin (both envs)
```

### Database Names
| DB | Dev | Prod |
|---|---|---|
| Node API | care-capture-app-dev | (from SSM) |
| EMR Connector | care-capture-emr-dev | care-capture-emr-prod |

## CloudWatch Templates

```bash
# Last N hours (macOS date -v syntax)
START=$(date -v-1H -u +%s)000
aws logs filter-log-events \
  --log-group-name "<LOG_GROUP>" \
  --start-time $START \
  --filter-pattern "<PATTERN>" \
  --profile tuliodev --region us-east-2 \
  --query 'events[*].message' --output text --limit 50
```

## Session Findings

Save findings to `.claude/debug-scratch/` for multi-step investigations:
```bash
echo "user_id=abc123 has 3 appointments, 0 summaries" >> .claude/debug-scratch/session.md
```

## Output Format

For each finding, report:
1. **What you ran** (command or query, redacting passwords)
2. **What you found** (key result rows or log lines)
3. **Interpretation** (what this means for the issue)
4. **Next step** (what to check next, or conclusion if resolved)

When writing a debug report, save to `.claude/debug-reports/YYYY-MM-DD-<topic>.md`.

Include verification SQL queries in the report so the user can re-run them independently.

Keep responses concise. Lead with findings, not preamble.
