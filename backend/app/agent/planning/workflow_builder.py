"""Workflow builder — assembles resolved steps into a validated WorkflowRequest.

The existing build_workflow() API is preserved for callers that already have
typed WorkflowStep objects. build_from_raw() is the new decomposed entry
that accepts raw step dicts and returns a WorkflowBuildResult preserving
both raw and parsed output.
"""
from typing import Any

from pydantic import ValidationError

from app.agent.planning.pipeline_models import WorkflowBuildResult
from app.core.exceptions import PlannerError
from app.models.workflow_steps import WorkflowStep
from app.models.workflow_transport import WorkflowRequest


def build_workflow(dataset_id: str, steps: list[WorkflowStep]) -> WorkflowRequest:
    """Build a WorkflowRequest from already parsed steps (existing API, preserved as-is)."""
    return WorkflowRequest(dataset_id=dataset_id, steps=steps)


def build_from_raw(
    dataset_id: str,
    raw_steps: list[dict[str, Any]],
) -> WorkflowBuildResult:
    """Build and validate a workflow from raw step dicts.

    Preserves raw_steps alongside the parsed typed steps so the caller
    can inspect what the builder accepted vs. what the LLM produced.
    Raises PlannerError when steps fail Pydantic validation.
    """
    try:
        request = WorkflowRequest(dataset_id=dataset_id, steps=raw_steps)
    except ValidationError as exc:
        raise PlannerError(
            f"Workflow build failed: step structure is invalid. {exc}"
        ) from exc
    except Exception as exc:
        raise PlannerError(f"Workflow build failed: {exc}") from exc

    return WorkflowBuildResult(
        raw_steps=raw_steps,
        steps=request.steps,
        step_count=len(request.steps),
    )
