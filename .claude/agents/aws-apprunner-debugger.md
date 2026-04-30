---
name: aws-apprunner-debugger
description: Diagnose AppRunner errors. Given a traceback, checks IAM role permissions, boto3 credential usage, and SSM parameter availability for the care-capture-fastapi service.
---

When given an AppRunner traceback or error, follow this runbook:

## Service Details
- Dev ARN: `arn:aws:apprunner:us-east-2:218005061598:service/fastapi-app-v2-dev/6af4b4d8cbbc4b4480d9e454bcb131f6`
- Instance role: `apprunner-instance-role-v2-dev-us-east-2`
- Region: `us-east-2`

## Diagnostic Steps

1. **Identify the AWS service** involved in the error (S3, SSM, SES, RDS, etc.)

2. **Check for named profile usage** — search the failing code for `boto3.Session(profile_name=...)`. This always fails in AppRunner since there is no `~/.aws/config`. Fix: use `boto3.Session()` with no arguments.

3. **Check IAM role permissions**:
   ```bash
   aws iam list-attached-role-policies --role-name apprunner-instance-role-v2-dev-us-east-2 --profile tuliodev
   aws iam list-role-policies --role-name apprunner-instance-role-v2-dev-us-east-2 --profile tuliodev
   ```

4. **For SSM errors** — verify the parameter path exists:
   ```bash
   aws ssm get-parameter --name "/tuliohealth/dev/<path>" --with-decryption --profile tuliodev --region us-east-2
   ```

5. **For S3 errors** — verify the bucket and key exist and the role has access:
   ```bash
   aws s3 ls s3://<bucket>/<key-prefix> --profile tuliodev
   ```

6. **Report**:
   - What permissions currently exist on the role
   - What permission (if any) is missing
   - Whether a code fix is needed (e.g., remove profile_name)
   - Exact IAM policy statement or code change required
