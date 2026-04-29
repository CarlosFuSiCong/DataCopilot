import logging
from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class DataCopilotError(Exception):
    """Base error for all application-level failures."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


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


async def datacoppilot_error_handler(
    request: Request, exc: DataCopilotError
) -> JSONResponse:
    logger.warning("Application error on %s: %s", request.url.path, exc.message)
    return JSONResponse(status_code=400, content={"error": exc.message})
