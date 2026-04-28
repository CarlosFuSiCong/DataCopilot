from fastapi import FastAPI


app = FastAPI(
    title="DataCopilot API",
    description="RAG-powered workflow chatbot backend.",
    version="0.1.0",
)


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
