"""
Version information for the FastAPI application.
This file is auto-generated during CI/CD build process.
DO NOT EDIT MANUALLY.
"""
import os
from typing import Dict

def get_version_info() -> Dict[str, str]:
    """Get version information from environment variables."""
    from datetime import datetime
    
    # Get build time or use current time as fallback
    build_time = os.getenv("BUILD_TIME")
    if not build_time:
        build_time = datetime.utcnow().isoformat() + "Z"
    
    return {
        "version": os.getenv("API_VERSION", "1.0.0-local"),
        "buildNumber": os.getenv("BUILD_NUMBER", "local"),
        "buildTime": build_time,
        "commit": os.getenv("GIT_COMMIT", "local"),
        "branch": os.getenv("GIT_BRANCH", "local"),
        "environment": os.getenv("APP_ENV", "development"),
    }

# Version info singleton
API_VERSION = get_version_info()