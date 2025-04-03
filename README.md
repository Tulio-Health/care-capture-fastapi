# FastAPI Example API

This project demonstrates a simple FastAPI application designed for containerization and deployment to AWS App Runner. It provides two basic endpoints, `/hello` and `/health`, showcasing a minimal API setup.

### Prerequisites

- Python 3.8+
- Poetry (install with `pip install poetry`)
- Docker
- AWS account with ECR and App Runner permissions
- GitHub account
- An AWS account with appropriate permissions
- An IAM role with permissions for ECR and App Runner
- ECR repositories created for your applications
- App Runner services created (or permissions to create them)

## Setting Up GitHub Secrets

Navigate to your repository settings → Secrets and variables → Actions, and add the following secrets:

| Secret Name              | Description                                                                                                                        |
| ------------------------ | ---------------------------------------------------------------------------------------------------------------------------------- |
| `FASTAPI_AWS_ROLE_ARN`   | ARN of an IAM role with permissions to push to ECR and deploy to App Runner (format: `arn:aws:iam::{account-id}:role/{role-name}`) |
| `AWS_REGION`             | The AWS region where your resources are deployed (e.g., `us-east-1`)                                                               |
| `ECR_REPOSITORY`         | Name of your ECR repository for the FastAPI application                                                                            |
| `APPRUNNER_SERVICE_NAME` | Name of your App Runner service for the FastAPI application                                                                        |

## How to Add GitHub Secrets

1. Go to your GitHub repository
2. Click on "Settings" tab
3. In the left sidebar, click on "Secrets and variables" then "Actions"
4. Click on "New repository secret"
5. Enter the secret name and value
6. Click "Add secret"
7. Repeat for each required secret

## Verifying Secret Configuration

Once all secrets are added, you can verify them by:

1. Going to your repository's "Settings" → "Secrets and variables" → "Actions"
2. Checking that all required secrets are listed (the values will be hidden)
3. Making a small commit to trigger the workflow and checking the workflow logs for any secret-related errors

### Setup

1.  **Clone the repository:**

    ```bash
    git clone [https://github.com/Tulio-Health/care-capture-fastapi.git](https://github.com/Tulio-Health/care-capture-fastapi.git)
    cd fastapi
    ```

2.  **Install dependencies using Poetry:**

    ```bash
    poetry install
    ```

3.  **Configure AWS:**

    - Replace placeholders in `.github/workflows/deploy.yml` with your AWS region and App Runner service name.
    - Set up AWS credentials as GitHub secrets: `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`.
    - Create an ECR repository to store the Docker image.
    - Create an App Runner service to deploy the application.

### Local Development

1.  **Run the FastAPI application:**

    ```bash
    poetry run uvicorn fastapi_example.main:app --reload
    ```

    This will start the server, and you can access the endpoints at `http://127.0.0.1:8000`.

2.  **Test the endpoints:**

    - `http://127.0.0.1:8000/hello` (returns `{"message": "Hello, World!"}`)
    - `http://127.0.0.1:8000/health` (returns a 200 OK status)

### Local Docker Development

1.  **Build the Docker image:**

    ```bash
    docker build -t fastapi-example .
    ```

2.  **Run the Docker container:**

    ```bash
    docker run -p 8000:8000 fastapi-example
    ```

    The application will be accessible at `http://localhost:8000`.

### Deployment to AWS App Runner

1.  **Push your code to the `main` branch of your GitHub repository.**

2.  **GitHub Actions will automatically build the Docker image, push it to ECR, and deploy it to AWS App Runner.**

## Endpoints

- `/hello`: Returns a JSON response with a "Hello, World!" message.
- `/health`: Returns a 200 OK status, indicating the application is running.

## AWS Services Used

- **Amazon ECR (Elastic Container Registry):** Stores the Docker image.
- **AWS App Runner:** Provides a fully managed container service for deploying the application.
- **GitHub Actions:** Automates the CI/CD pipeline for building and deploying the application.

## Contributing

Contributions are welcome! Please feel free to submit pull requests or open issues for any improvements or bug fixes.
