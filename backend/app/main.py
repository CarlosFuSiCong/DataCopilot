from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI

from app.api import chat as chat_router
from app.api import dataset as dataset_router
from app.api import rag as rag_router
from app.api import workflow as workflow_router
from app.core import database
from app.core.exceptions import DataCopilotError, datacoppilot_error_handler


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    await database.connect()
    yield
    await database.disconnect()


app = FastAPI(
    title="DataCopilot API",
    description="RAG-powered workflow chatbot backend.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_exception_handler(DataCopilotError, datacoppilot_error_handler)

app.include_router(dataset_router.router, prefix="/api")
app.include_router(workflow_router.router, prefix="/api")
app.include_router(rag_router.router, prefix="/api")
app.include_router(chat_router.router, prefix="/api")


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
