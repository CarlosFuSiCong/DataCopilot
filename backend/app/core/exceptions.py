import logging
from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class DataCopilotError(Exception):
    """Base error for all application-level failures."""

    def __init__(
        self,
        message: str,
        error_code: str | None = None,
        context: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        # Machine-readable error code for frontend to render specific UI.
        self.error_code = error_code
        # Optional structured context (e.g. available_columns, example_queries).
        self.context: dict = context or {}


class InvalidDatasetError(DataCopilotError):
    """Raised when the uploaded file is not a valid CSV."""


class ProfilerError(DataCopilotError):
    """Raised when pandas fails to parse the CSV."""


class DatasetNotFoundError(DataCopilotError):
    """Raised when a dataset_id is not found in the store."""


class WorkflowValidationError(DataCopilotError):
    """Raised when a workflow step references invalid columns or parameters."""


class ExecutionError(DataCopilotError):
    """Raised when a workflow step fails at pandas execution time."""


class PlannerError(DataCopilotError):
    """Raised when the LLM planner fails to produce a valid workflow JSON."""


class ClarificationNeeded(Exception):
    """Raised by the planner when the user query is too ambiguous to plan.

    This is NOT a DataCopilotError — it is a valid application state, not a
    failure.  chat.py catches it and returns a 200 ChatResponse with
    needs_clarification=True rather than a 400 error.
    """

    def __init__(self, question: str) -> None:
        super().__init__(question)
        self.question = question


async def datacoppilot_error_handler(
    request: Request, exc: DataCopilotError
) -> JSONResponse:
    logger.warning("Application error on %s: %s", request.url.path, exc.message)
    payload: dict = {"error": exc.message}
    if exc.error_code:
        payload["error_code"] = exc.error_code
    if exc.context:
        payload["context"] = exc.context
    return JSONResponse(status_code=400, content=payload)
