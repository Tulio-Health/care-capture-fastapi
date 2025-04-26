from fastapi import FastAPI
from .main import create_app
import asyncio

# Create the FastAPI app instance
app = None

async def get_app() -> FastAPI:
    global app
    if app is None:
        app = await create_app()
    return app

# Initialize the app
app = asyncio.run(create_app()) 