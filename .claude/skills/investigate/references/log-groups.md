# CloudWatch Log Groups

## App Runner Application Logs

| Service       | Dev                                                                                              | Prod                                                                                               |
|---------------|--------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------|
| Node API      | `/aws/apprunner/nodejs-app-v2-dev/78673134ccf142fd8031b0380d2401ab/application`                 | `/aws/apprunner/nodejs-app-v2-prod/5767d061f5e643439b53521feffff989/application`                  |
| FastAPI       | `/aws/apprunner/fastapi-app-v2-dev/6af4b4d8cbbc4b4480d9e454bcb131f6/application`               | `/aws/apprunner/fastapi-app-v2-prod/041fe75d4e5a491884815dac3cf2f518/application`                 |
| EMR Connector | `/aws/apprunner/emr-connector-dev/9a9d258335684b5a96e9252ec08508a9/application`                 | `/aws/apprunner/emr-connector-prod/4b14d77f39c848388f9231a2a80a6076/application`                  |

## Lambda Log Groups

| Function                             | Log Group                                          |
|--------------------------------------|----------------------------------------------------|
| Cleanup job (dev)                    | `/aws/lambda/cc-dev-lambda-cleanup-job`            |
| Cleanup job (prod)                   | `/aws/lambda/care-capture-cleanup-job`             |
| Fetch job (dev)                      | `/aws/lambda/cc-dev-lambda-fetch-job`              |
| Fetch job (prod)                     | `/aws/lambda/care-capture-fetch-job`               |
| Push notifications daily (dev)       | `/aws/lambda/cc-dev-lambda-push-notification-daily`|
| Push notifications hourly (dev)      | `/aws/lambda/cc-dev-lambda-push-notification-hourly`|

## filter-log-events Patterns

```bash
# Error logs for a user
--filter-pattern '"userId" "<USER_ID>"'

# Errors only
--filter-pattern '"ERROR"'

# Appointment-related
--filter-pattern '"appointmentId" "<APPOINTMENT_ID>"'

# Sync job
--filter-pattern '"jobId" "<JOB_ID>"'

# Summary generation
--filter-pattern '"summary"'

# Translation requests
--filter-pattern '"translate"'

# EHR connection
--filter-pattern '"connectionId" "<CONNECTION_ID>"'
```

## CloudWatch Insights Queries

Run via `aws logs start-query` (async) or use the console:

```sql
-- Top errors in last hour
fields @timestamp, @message
| filter @message like /ERROR/
| sort @timestamp desc
| limit 50

-- All events for a user
fields @timestamp, @message
| filter @message like /<USER_ID>/
| sort @timestamp desc
| limit 100

-- Summary generation failures
fields @timestamp, @message
| filter @message like /summary/ and @message like /error|fail|Error|Fail/
| sort @timestamp desc
| limit 50

-- EMR sync events for a connection
fields @timestamp, @message
| filter @message like /<CONNECTION_ID>/
| sort @timestamp desc
| limit 100
```

## Useful filter-log-events Flags

```bash
# Stream output as it comes (for recent logs)
--interleaved

# Limit events returned
--limit 50

# Multiple patterns (OR logic with ?):
--filter-pattern '?"ERROR" ?"WARN"'
```
