"""
AWS SSM Parameter Store loader for FastAPI application
"""

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Dict, List, Optional

import boto3
from botocore.exceptions import ClientError, NoCredentialsError

logger = logging.getLogger(__name__)


@dataclass
class SSMParameterMapping:
    """Mapping between SSM parameter paths and environment variables"""

    ssm_path: str
    env_var: str
    is_secure: bool = False


class SSMParameterLoader:
    """Loads configuration from AWS SSM Parameter Store"""

    def __init__(self, region: Optional[str] = None):
        """
        Initialize SSM client and determine environment

        Args:
            region: AWS region (defaults to AWS_REGION env var or us-east-2)
        """
        self.region = region or os.getenv("AWS_REGION", "us-east-2")

        try:
            self.ssm_client = boto3.client("ssm", region_name=self.region)
        except NoCredentialsError:
            logger.error("AWS credentials not configured for SSM access")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize SSM client: {e}")
            raise

        # Determine environment from APP_ENV or default to dev
        environment = "prod" if os.getenv("APP_ENV") == "production" else "dev"
        self.parameter_prefix = os.getenv(
            "SSM_PARAMETER_PREFIX", f"/tuliohealth/{environment}"
        )

        # Cached result of should_load_ssm() — computed at most once per instance
        # (WR-03: avoids duplicate describe_parameters API calls per startup).
        self._ssm_available: Optional[bool] = None

        logger.info(f"SSM Parameter Loader initialized for environment: {environment}")
        logger.info(f"Parameter prefix: {self.parameter_prefix}")

    @staticmethod
    def get_parameter_mappings() -> List[SSMParameterMapping]:
        """
        Define mappings between SSM parameters and environment variables
        Only include parameters that FastAPI actually needs
        """
        return [
            # Infrastructure Configuration
            SSMParameterMapping("infrastructure/app_env", "APP_ENV"),
            # Database Configuration
            SSMParameterMapping("database/host", "DB_HOST"),
            SSMParameterMapping("database/port", "DB_PORT"),
            SSMParameterMapping("database/username", "DB_USER"),
            SSMParameterMapping("database/password", "DB_PASSWORD", is_secure=True),
            SSMParameterMapping("database/name", "DB_NAME"),
            SSMParameterMapping("database/ssl", "DB_SSL"),
            # Redis Configuration
            SSMParameterMapping("redis/host", "REDIS_HOST"),
            SSMParameterMapping("redis/port", "REDIS_PORT"),
            SSMParameterMapping("redis/password", "REDIS_PASSWORD", is_secure=True),
            # External Services
            SSMParameterMapping("openai/api_key", "OPENAI_API_KEY", is_secure=True),
            # Clerk Configuration
            SSMParameterMapping("clerk/public_jwt_key", "CLERK_PUBLIC_JWT_KEY"),
            SSMParameterMapping("clerk/secret_key", "CLERK_SECRET_KEY", is_secure=True),
            SSMParameterMapping("clerk/publishable_key", "CLERK_PUBLISHABLE_KEY"),
            # LangSmith Configuration (optional - will use defaults if not in SSM)
            SSMParameterMapping("langsmith/tracing", "LANGSMITH_TRACING"),
            SSMParameterMapping(
                "langsmith/api_key", "LANGSMITH_API_KEY", is_secure=True
            ),
            SSMParameterMapping("langsmith/endpoint", "LANGSMITH_ENDPOINT"),
            SSMParameterMapping("langsmith/project", "LANGSMITH_PROJECT"),
            # Internal Service-to-Service Auth
            SSMParameterMapping(
                "internal/service_key", "INTERNAL_SERVICE_KEY", is_secure=True
            ),
            SSMParameterMapping("urls/node_api_url", "NODE_API_URL"),
            # Playground (dev-only)
            SSMParameterMapping(
                "playground/api_key", "PLAYGROUND_API_KEY", is_secure=True
            ),
        ]

    def should_load_ssm(self) -> bool:
        """
        Determine if SSM parameters should be loaded.

        Result is cached per instance (WR-03) — the underlying
        describe_parameters API call is made at most once per startup.

        Returns:
            True if AWS credentials are available and SSM is accessible
        """
        if self._ssm_available is not None:
            return self._ssm_available
        try:
            # Test if we can access SSM (indicates AWS credentials are available)
            self.ssm_client.describe_parameters(MaxResults=1)
            logger.info("AWS credentials detected - will load from SSM Parameter Store")
            self._ssm_available = True
        except Exception as e:
            logger.info(
                f"No AWS credentials or SSM access - using environment variables: {str(e)}"
            )
            self._ssm_available = False
        return self._ssm_available

    # ---------------------------------------------------------------------------
    # Shared parameter-processing core (WR-02: eliminates ~100 line duplication).
    # Both load_parameters_sync and load_parameters call this helper.
    # ---------------------------------------------------------------------------

    def _load_parameters_core(self) -> Dict[str, str]:
        """
        Synchronous core: page through SSM, map to env-var names, return dict.

        This is the single source of truth for parameter loading logic.
        load_parameters_sync() calls it directly; load_parameters() (async)
        dispatches it to a thread pool via asyncio.to_thread() (WR-01).
        """
        logger.info(f"Loading SSM parameters from prefix: {self.parameter_prefix}")

        try:
            # Get all parameters by path (AWS SSM limits MaxResults to 10)
            all_parameters = []
            next_token = None

            while True:
                params = {
                    "Path": self.parameter_prefix,
                    "Recursive": True,
                    "WithDecryption": True,
                    "MaxResults": 10,
                }

                if next_token:
                    params["NextToken"] = next_token

                response = self.ssm_client.get_parameters_by_path(**params)
                all_parameters.extend(response.get("Parameters", []))

                next_token = response.get("NextToken")
                if not next_token:
                    break

            # Check if we got any parameters
            if not all_parameters:
                logger.error(
                    f"❌ No SSM parameters found at path: {self.parameter_prefix}"
                )
                if os.getenv("APP_ENV") == "production":
                    raise ValueError(
                        f"No SSM parameters found at path: {self.parameter_prefix}"
                    )
                logger.warning("⚠️ Continuing with existing environment variables")
                return {}

            parameter_dict = {}

            # Convert SSM parameters to environment variables
            mappings = self.get_parameter_mappings()
            mapping_dict = {
                f"{self.parameter_prefix}/{mapping.ssm_path}": mapping
                for mapping in mappings
            }

            # Log which parameters were found
            loaded_params = [p["Name"] for p in all_parameters]
            logger.info(f"✅ Found SSM parameters: {loaded_params}")

            # Track successfully mapped parameters
            mapped_params = []
            for param in all_parameters:
                param_name = param["Name"]
                param_value = param["Value"]

                if param_name in mapping_dict:
                    mapping = mapping_dict[param_name]
                    parameter_dict[mapping.env_var] = param_value
                    mapped_params.append(mapping.env_var)
                    # Log with security considerations
                    if mapping.is_secure:
                        logger.debug(f"Loaded secure parameter: {mapping.env_var}")
                    else:
                        logger.debug(
                            f"Loaded parameter: {mapping.env_var} = {param_value}"
                        )

            logger.info(f"Successfully loaded {len(parameter_dict)} SSM parameters")
            logger.info(f"Mapped parameters to environment variables: {mapped_params}")
            logger.info(f"Set {len(parameter_dict)} environment variables from SSM")
            return parameter_dict

        except ClientError as e:
            logger.error(f"AWS SSM ClientError: {e}")
            # In production, fail fast for SSM issues
            if os.getenv("APP_ENV") == "production":
                raise Exception(f"Failed to load SSM parameters: {e}")
            logger.warning("⚠️ Continuing with existing environment variables")
            return {}
        except Exception as e:
            logger.error(f"Unexpected error loading SSM parameters: {e}")
            # In production, fail fast for SSM issues
            if os.getenv("APP_ENV") == "production":
                raise
            logger.warning("⚠️ Continuing with existing environment variables")
            return {}

    def load_parameters_sync(self) -> Dict[str, str]:
        """
        Load all parameters from SSM Parameter Store synchronously.

        Returns:
            Dictionary of parameter values keyed by environment variable names

        Raises:
            Exception: If SSM parameter loading fails
        """
        if not self.should_load_ssm():
            logger.info(
                "SSM parameter loading disabled - using existing environment variables"
            )
            return {}

        return self._load_parameters_core()

    async def load_parameters(self) -> Dict[str, str]:
        """
        Load all parameters from SSM Parameter Store (async variant).

        Delegates the blocking boto3 calls to a thread pool via
        asyncio.to_thread() so the event loop is not blocked during startup
        (WR-01).

        Returns:
            Dictionary of parameter values keyed by environment variable names

        Raises:
            Exception: If SSM parameter loading fails
        """
        if not self.should_load_ssm():
            logger.info(
                "SSM parameter loading disabled - using existing environment variables"
            )
            return {}

        return await asyncio.to_thread(self._load_parameters_core)

    def set_environment_variables(self, parameters: Dict[str, str]) -> None:
        """
        Set environment variables from SSM parameters.

        After writing all values into os.environ, invalidates the Settings
        singleton so the next get_settings() call builds a fresh instance from
        the now-populated environment (CR-01 fix).

        Args:
            parameters: Dictionary of environment variables and their values
        """
        skipped = []
        for env_var, value in parameters.items():
            if env_var in os.environ:
                skipped.append(env_var)
                logger.debug(f"Skipping {env_var} — already set in local environment")
            else:
                os.environ[env_var] = value
                logger.debug(f"Set environment variable: {env_var}")

        if skipped:
            logger.info(f"Local env overrides SSM for: {skipped}")
        logger.info(f"Set {len(parameters) - len(skipped)} environment variables from SSM")

        # Invalidate the cached Settings object so the next get_settings() call
        # reads the freshly injected SSM values (CR-01).
        try:
            from src.app.core.settings import reset_settings
            reset_settings()
            logger.debug("Settings singleton reset after SSM injection")
        except Exception as exc:
            logger.warning(f"Could not reset settings after SSM injection: {exc}")


def load_ssm_configuration_sync() -> None:
    """
    Main function to load SSM configuration into environment variables synchronously
    Call this early in application startup
    """
    try:
        loader = SSMParameterLoader()

        # Only load if we should use SSM
        if not loader.should_load_ssm():
            logger.info(
                "SSM loading skipped - using existing environment configuration"
            )
            return

        logger.info("🔧 Loading configuration from AWS SSM Parameter Store...")

        # Load parameters from SSM synchronously
        parameters = loader.load_parameters_sync()

        if parameters:
            # Set environment variables
            loader.set_environment_variables(parameters)

            # Override Redis configuration for local development (similar to NodeAPI)
            # Check if running locally (not in AWS App Runner)
            aws_execution_env = os.getenv("AWS_EXECUTION_ENV", "")
            logger.info(f"AWS_EXECUTION_ENV detected: '{aws_execution_env}'")
            is_local_dev = not (
                aws_execution_env.startswith("AWS_App_Runner")
                or "AWS" in aws_execution_env
                or os.path.exists("/opt/aws")
            )
            if is_local_dev:
                logger.info("🔧 Overriding Redis configuration for local development")
                os.environ["REDIS_HOST"] = "127.0.0.1"
                os.environ["REDIS_PORT"] = "6379"
                os.environ["REDIS_PASSWORD"] = ""
                logger.info("Redis configuration set to local instance")

            # Log Redis service details
            redis_host = os.getenv("REDIS_HOST", "NOT_SET")
            redis_port = os.getenv("REDIS_PORT", "NOT_SET")
            logger.info(f"📡 Redis Service Configuration: {redis_host}:{redis_port}")

            logger.info("✅ SSM configuration loaded successfully")
        else:
            logger.warning("No SSM parameters loaded")

    except Exception as e:
        logger.error(f"❌ Failed to load SSM configuration: {e}")
        # Don't raise - allow app to start with existing env vars
        logger.info("Continuing with existing environment variables")


async def load_ssm_configuration() -> None:
    """
    Main function to load SSM configuration into environment variables
    Call this early in application startup
    """
    try:
        loader = SSMParameterLoader()

        # Only load if we should use SSM
        if not loader.should_load_ssm():
            logger.info(
                "SSM loading skipped - using existing environment configuration"
            )
            return

        logger.info("🔧 Loading configuration from AWS SSM Parameter Store...")

        # Load parameters from SSM
        parameters = await loader.load_parameters()

        if parameters:
            # Set environment variables
            loader.set_environment_variables(parameters)

            # Override Redis configuration for local development (similar to NodeAPI)
            # Check if running locally (not in AWS App Runner)
            aws_execution_env = os.getenv("AWS_EXECUTION_ENV", "")
            logger.info(f"AWS_EXECUTION_ENV detected: '{aws_execution_env}'")
            is_local_dev = not (
                aws_execution_env.startswith("AWS_App_Runner")
                or "AWS" in aws_execution_env
                or os.path.exists("/opt/aws")
            )
            if is_local_dev:
                logger.info("🔧 Overriding Redis configuration for local development")
                os.environ["REDIS_HOST"] = "127.0.0.1"
                os.environ["REDIS_PORT"] = "6379"
                os.environ["REDIS_PASSWORD"] = ""
                logger.info("Redis configuration set to local instance")

            # Log Redis service details
            redis_host = os.getenv("REDIS_HOST", "NOT_SET")
            redis_port = os.getenv("REDIS_PORT", "NOT_SET")
            logger.info(f"📡 Redis Service Configuration: {redis_host}:{redis_port}")

            logger.info("✅ SSM configuration loaded successfully")
        else:
            logger.warning("No SSM parameters loaded")

    except Exception as e:
        logger.error(f"❌ Failed to load SSM configuration: {e}")
        # Don't raise - allow app to start with existing env vars
        logger.info("Continuing with existing environment variables")

