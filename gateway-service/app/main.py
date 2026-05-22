import sys
import os

# Add shared directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from fastapi import FastAPI, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging
from app.routes.routes import api_router

app = FastAPI(title="Gateway Service", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)

logger = logging.getLogger(__name__)

def process_webhook_payload(payload: dict):
    logger.info(f"Processing WhatsApp payload in background: {payload}")
    pass

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "gateway-service"}


@app.get("/")
async def root():
    return {"message": "FastAPI Gateway funcionando"}