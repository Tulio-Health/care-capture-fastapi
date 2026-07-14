# Infrastructure Health Checks

## App Runner Service ARNs

| Service       | Env  | ARN |
|---------------|------|-----|
| Node API      | dev  | `arn:aws:apprunner:us-east-2:218005061598:service/nodejs-app-v2-dev/78673134ccf142fd8031b0380d2401ab` |
| Node API      | prod | `arn:aws:apprunner:us-east-2:218005061598:service/nodejs-app-v2-prod/5767d061f5e643439b53521feffff989` |
| FastAPI       | dev  | `arn:aws:apprunner:us-east-2:218005061598:service/fastapi-app-v2-dev/6af4b4d8cbbc4b4480d9e454bcb131f6` |
| FastAPI       | prod | `arn:aws:apprunner:us-east-2:218005061598:service/fastapi-app-v2-prod/041fe75d4e5a491884815dac3cf2f518` |
| EMR Connector | dev  | `arn:aws:apprunner:us-east-2:218005061598:service/emr-connector-dev/9a9d258335684b5a96e9252ec08508a9` |
| EMR Connector | prod | `arn:aws:apprunner:us-east-2:218005061598:service/emr-connector-prod/4b14d77f39c848388f9231a2a80a6076` |

## Service URLs

| Service       | Dev                                        | Prod                                       |
|---------------|--------------------------------------------|--------------------------------------------|
| Node API      | `3prbzi93uc.us-east-2.awsapprunner.com`    | `r57hutgjpp.us-east-2.awsapprunner.com`    |
| FastAPI       | `utd7qiwpgp.us-east-2.awsapprunner.com`    | `wjemvxmtm7.us-east-2.awsapprunner.com`    |
| EMR Connector | `wqactdsprm.us-east-2.awsapprunner.com`    | `4naxg7fmpw.us-east-2.awsapprunner.com`    |

## Service Status Checks

```bash
# Check service status (replace ARN as needed)
aws apprunner describe-service \
  --service-arn "arn:aws:apprunner:us-east-2:218005061598:service/nodejs-app-v2-dev/78673134ccf142fd8031b0380d2401ab" \
  --profile tuliodev --region us-east-2 \
  --query 'Service.{Status:Status,URL:ServiceUrl,UpdatedAt:UpdatedAt}' \
  --output table

# Check all services at once
for ARN in \
  "arn:aws:apprunner:us-east-2:218005061598:service/nodejs-app-v2-dev/78673134ccf142fd8031b0380d2401ab" \
  "arn:aws:apprunner:us-east-2:218005061598:service/fastapi-app-v2-dev/6af4b4d8cbbc4b4480d9e454bcb131f6" \
  "arn:aws:apprunner:us-east-2:218005061598:service/emr-connector-dev/9a9d258335684b5a96e9252ec08508a9"; do
  aws apprunner describe-service --service-arn "$ARN" \
    --profile tuliodev --region us-east-2 \
    --query 'Service.{Name:ServiceName,Status:Status,UpdatedAt:UpdatedAt}' \
    --output json
done
```

## Recent Deployments / Operations

```bash
# List recent operations for a service
aws apprunner list-operations \
  --service-arn "arn:aws:apprunner:us-east-2:218005061598:service/nodejs-app-v2-dev/78673134ccf142fd8031b0380d2401ab" \
  --profile tuliodev --region us-east-2 \
  --query 'OperationSummaryList[*].{Type:Type,Status:Status,StartedAt:StartedAt,EndedAt:EndedAt}' \
  --output table
```

## Health Check (HTTP)

```bash
# Node API health
curl -s https://3prbzi93uc.us-east-2.awsapprunner.com/health

# FastAPI health
curl -s https://utd7qiwpgp.us-east-2.awsapprunner.com/health

# EMR Connector health
curl -s https://wqactdsprm.us-east-2.awsapprunner.com/health
```

## ECR Image History (recent pushes)

```bash
# List recent images for a repository
aws ecr describe-images \
  --repository-name nodejs-app-v2 \
  --profile tuliodev --region us-east-2 \
  --query 'sort_by(imageDetails, &imagePushedAt)[-5:].{Tag:imageTags[0],PushedAt:imagePushedAt,Size:imageSizeInBytes}' \
  --output table
```
