# fastapi-example/fastapi_example/main.py
from fastapi import FastAPI, Response

app = FastAPI()

@app.get("/hello")
async def hello():
    return {"message": "Hello, World! Commit 1"}

@app.get("/health")
async def health():
    return {"status": "healthy", "message": "Health check OK Commit 1"}
