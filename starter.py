"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from backend import get_rag_service
from config import settings
from conversation import router as conversation_router
from evaluation_api import router as evaluation_router
from search import router as chat_router
from upload import router as upload_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Only create local directories. Model and vector-store initialization remain lazy.
    if settings.app_environment != "development" and not settings.api_key:
        raise RuntimeError("API_KEY must be configured outside development mode")
    settings.ensure_storage_directories()
    yield


app = FastAPI(
    title="Evidence RAG API",
    version="1.0.0",
    description="Source-aware hybrid retrieval and streaming knowledge-base Q&A.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)
app.include_router(upload_router)
app.include_router(conversation_router)
app.include_router(evaluation_router)


@app.get("/", tags=["system"])
async def root() -> dict[str, str]:
    return {"name": settings.app_name, "docs": "/docs", "health": "/health"}


@app.get("/health", tags=["system"])
async def health() -> dict[str, Any]:
    """Configuration-only health check. It never downloads or initializes a model."""
    return get_rag_service().health_report()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("starter:app", host="127.0.0.1", port=8000, reload=settings.app_environment == "development")
