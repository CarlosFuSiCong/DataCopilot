from fastapi import FastAPI

from app.api import dataset as dataset_router
from app.core.exceptions import DataCopilotError, datacoppilot_error_handler

app = FastAPI(
    title="DataCopilot API",
    description="RAG-powered workflow chatbot backend.",
    version="0.1.0",
)

app.add_exception_handler(DataCopilotError, datacoppilot_error_handler)

app.include_router(dataset_router.router, prefix="/api")


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
