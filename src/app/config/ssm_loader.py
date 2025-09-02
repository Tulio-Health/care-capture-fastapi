"""
AWS SSM Parameter Store loader for FastAPI application
"""
import os
import boto3
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass
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
        self.region = region or os.getenv('AWS_REGION', 'us-east-2')
        
        try:
            self.ssm_client = boto3.client('ssm', region_name=self.region)
        except NoCredentialsError:
            logger.error("AWS credentials not configured for SSM access")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize SSM client: {e}")
            raise
        
        # Determine environment from NODE_ENV or default to dev
        environment = 'prod' if os.getenv('NODE_ENV') == 'production' else 'dev'
        self.parameter_prefix = os.getenv('SSM_PARAMETER_PREFIX', f'/tuliohealth/{environment}')
        
        logger.info(f"SSM Parameter Loader initialized for environment: {environment}")
        logger.info(f"Parameter prefix: {self.parameter_prefix}")
    
    @staticmethod
    def get_parameter_mappings() -> List[SSMParameterMapping]:
        """
        Define mappings between SSM parameters and environment variables
        Only include parameters that FastAPI actually needs
        """
        return [
            # Database Configuration
            SSMParameterMapping('database/host', 'DB_HOST'),
            SSMParameterMapping('database/port', 'DB_PORT'),
            SSMParameterMapping('database/username', 'DB_USER'),
            SSMParameterMapping('database/password', 'DB_PASSWORD', is_secure=True),
            SSMParameterMapping('database/name', 'DB_NAME'),
            SSMParameterMapping('database/ssl', 'DB_SSL'),
            
            # Redis Configuration
            SSMParameterMapping('redis/host', 'REDIS_HOST'),
            SSMParameterMapping('redis/port', 'REDIS_PORT'),
            SSMParameterMapping('redis/password', 'REDIS_PASSWORD', is_secure=True),
            
            # External Services
            SSMParameterMapping('openai/api_key', 'OPENAI_API_KEY', is_secure=True),
            
            # Note: LangSmith parameters are not in SSM yet - they should be loaded from .env
            # If needed in SSM later, add:
            # SSMParameterMapping('langsmith/api_key', 'LANGSMITH_API_KEY', is_secure=True),
            # SSMParameterMapping('langsmith/endpoint', 'LANGSMITH_ENDPOINT'),
            # SSMParameterMapping('langsmith/project', 'LANGSMITH_PROJECT'),
        ]
    
    def should_load_ssm(self) -> bool:
        """
        Determine if SSM parameters should be loaded
        
        Returns:
            True if running in AWS App Runner or USE_SSM_LOCALLY=true
        """
        # Check if running in AWS App Runner
        is_app_runner = os.getenv('AWS_EXECUTION_ENV', '').startswith('AWS_App_Runner')
        
        # Check for local SSM override
        force_ssm_local = os.getenv('USE_SSM_LOCALLY', 'false').lower() == 'true'
        
        return is_app_runner or force_ssm_local
    
    async def load_parameters(self) -> Dict[str, str]:
        """
        Load all parameters from SSM Parameter Store
        
        Returns:
            Dictionary of parameter values keyed by environment variable names
            
        Raises:
            Exception: If SSM parameter loading fails
        """
        if not self.should_load_ssm():
            logger.info("SSM parameter loading disabled - using existing environment variables")
            return {}
        
        logger.info(f"Loading SSM parameters from prefix: {self.parameter_prefix}")
        
        try:
            # Get all parameters by path (AWS SSM limits MaxResults to 10)
            all_parameters = []
            next_token = None
            
            while True:
                params = {
                    'Path': self.parameter_prefix,
                    'Recursive': True,
                    'WithDecryption': True,
                    'MaxResults': 10
                }
                
                if next_token:
                    params['NextToken'] = next_token
                
                response = self.ssm_client.get_parameters_by_path(**params)
                all_parameters.extend(response.get('Parameters', []))
                
                next_token = response.get('NextToken')
                if not next_token:
                    break
            
            parameter_dict = {}
            
            # Convert SSM parameters to environment variables
            mappings = self.get_parameter_mappings()
            mapping_dict = {f"{self.parameter_prefix}/{mapping.ssm_path}": mapping for mapping in mappings}
            
            for param in all_parameters:
                param_name = param['Name']
                param_value = param['Value']
                
                if param_name in mapping_dict:
                    mapping = mapping_dict[param_name]
                    parameter_dict[mapping.env_var] = param_value
                    logger.debug(f"Loaded parameter: {mapping.env_var}")
            
            logger.info(f"Successfully loaded {len(parameter_dict)} SSM parameters")
            return parameter_dict
            
        except ClientError as e:
            logger.error(f"AWS SSM ClientError: {e}")
            raise Exception(f"Failed to load SSM parameters: {e}")
        except Exception as e:
            logger.error(f"Unexpected error loading SSM parameters: {e}")
            raise
    
    def set_environment_variables(self, parameters: Dict[str, str]) -> None:
        """
        Set environment variables from SSM parameters
        
        Args:
            parameters: Dictionary of environment variables and their values
        """
        for env_var, value in parameters.items():
            os.environ[env_var] = value
            logger.debug(f"Set environment variable: {env_var}")
        
        logger.info(f"Set {len(parameters)} environment variables from SSM")


async def load_ssm_configuration() -> None:
    """
    Main function to load SSM configuration into environment variables
    Call this early in application startup
    """
    try:
        loader = SSMParameterLoader()
        
        # Only load if we should use SSM
        if not loader.should_load_ssm():
            logger.info("SSM loading skipped - using existing environment configuration")
            return
        
        logger.info("🔧 Loading configuration from AWS SSM Parameter Store...")
        
        # Load parameters from SSM
        parameters = await loader.load_parameters()
        
        if parameters:
            # Set environment variables
            loader.set_environment_variables(parameters)
            
            # Override Redis configuration for local development (similar to NodeAPI)
            force_ssm_local = os.getenv('USE_SSM_LOCALLY', 'false').lower() == 'true'
            if force_ssm_local:
                logger.info("🔧 Overriding Redis configuration for local development")
                os.environ['REDIS_HOST'] = '127.0.0.1'
                os.environ['REDIS_PORT'] = '6379'
                os.environ['REDIS_PASSWORD'] = ''
                logger.info("Redis configuration set to local instance")
            
            logger.info("✅ SSM configuration loaded successfully")
        else:
            logger.warning("No SSM parameters loaded")
            
    except Exception as e:
        logger.error(f"❌ Failed to load SSM configuration: {e}")
        # Don't raise - allow app to start with existing env vars
        logger.info("Continuing with existing environment variables")