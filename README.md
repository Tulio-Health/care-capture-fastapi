# FastAPI Example API

This project demonstrates a simple FastAPI application designed for containerization and deployment to AWS App Runner. It provides two basic endpoints, `/hello` and `/health`, showcasing a minimal API setup.

## Features

* **FastAPI:** Utilizes FastAPI for building the API, offering high performance and ease of development.
* **Poetry:** Manages dependencies and packaging with Poetry, ensuring consistent environments.
* **Docker:** Containerized for easy deployment and scalability.
* **AWS App Runner:** Deployed to AWS App Runner for a fully managed container service.
* **GitHub Actions:** Automated CI/CD pipeline for building and deploying the application.

## Project Structure

fastapi-example/
├── fastapi_example/
│   └── main.py       # FastAPI application code
├── pyproject.toml    # Poetry configuration file
├── poetry.lock       # Poetry lock file for dependencies
├── Dockerfile        # Docker configuration file
└── .github/workflows/
└── deploy.yml    # GitHub Actions workflow for deployment

## Getting Started

### Prerequisites

* Python 3.8+
* Poetry (install with `pip install poetry`)
* Docker
* AWS account with ECR and App Runner permissions
* GitHub account

### Setup

1.  **Clone the repository:**

    ```bash
    git clone [https://github.com/abaidgulshan/fastapi.git](https://github.com/abaidgulshan/fastapi.git)
    cd fastapi
    ```

2.  **Install dependencies using Poetry:**

    ```bash
    poetry install
    ```

3.  **Configure AWS:**

    * Replace placeholders in `.github/workflows/deploy.yml` with your AWS region and App Runner service name.
    * Set up AWS credentials as GitHub secrets: `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`.
    * Create an ECR repository to store the Docker image.
    * Create an App Runner service to deploy the application.

### Local Development

1.  **Run the FastAPI application:**

    ```bash
    poetry run uvicorn fastapi_example.main:app --reload
    ```

    This will start the server, and you can access the endpoints at `http://127.0.0.1:8000`.

2.  **Test the endpoints:**

    * `http://127.0.0.1:8000/hello` (returns `{"message": "Hello, World!"}`)
    * `http://127.0.0.1:8000/health` (returns a 200 OK status)

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

* `/hello`: Returns a JSON response with a "Hello, World!" message.
* `/health`: Returns a 200 OK status, indicating the application is running.

## AWS Services Used

* **Amazon ECR (Elastic Container Registry):** Stores the Docker image.
* **AWS App Runner:** Provides a fully managed container service for deploying the application.
* **GitHub Actions:** Automates the CI/CD pipeline for building and deploying the application.

## Contributing

Contributions are welcome! Please feel free to submit pull requests or open issues for any improvements or bug fixes.