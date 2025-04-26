from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI

def setup_cors_middleware(app: FastAPI) -> None:
    """Configure CORS middleware for the FastAPI application"""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # In production, replace with specific origins
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    ) 