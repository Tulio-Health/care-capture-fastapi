from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI
from typing import List

def setup_cors_middleware(
    app: FastAPI,
    allow_origins: List[str] = ["*"],
    allow_credentials: bool = True,
    allow_methods: List[str] = ["*"],
    allow_headers: List[str] = ["*"]
) -> None:
    """
    Configure CORS middleware for the FastAPI application
    
    Args:
        app: FastAPI application instance
        allow_origins: List of allowed origins
        allow_credentials: Whether to allow credentials
        allow_methods: List of allowed HTTP methods
        allow_headers: List of allowed HTTP headers
    """
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=allow_credentials,
        allow_methods=allow_methods,
        allow_headers=allow_headers,
    ) 