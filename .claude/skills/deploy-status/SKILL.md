---
name: deploy-status
description: Check the latest GitHub Actions deploy status and AppRunner service health for care-capture-fastapi
---

Check deploy status for care-capture-fastapi:

1. **GitHub Actions — last 3 deploy runs**:
   ```bash
   gh run list --repo Tulio-Health/care-capture-fastapi --workflow dev-deploy.yml --limit 3
   ```

2. **AppRunner service health**:
   ```bash
   aws apprunner describe-service \
     --service-arn arn:aws:apprunner:us-east-2:218005061598:service/fastapi-app-v2-dev/6af4b4d8cbbc4b4480d9e454bcb131f6 \
     --profile tuliodev \
     --region us-east-2 \
     --query 'Service.{Status:Status,URL:ServiceUrl,UpdatedAt:UpdatedAt}'
   ```

3. **Report**:
   - Last 3 workflow run statuses (success/failure + timestamp)
   - Current AppRunner service status and URL
   - If any run failed, offer to fetch the logs with: `gh run view <run-id> --log-failed`
