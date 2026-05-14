"""Future workflow builder boundary.

The current `workflow_planner` still builds complete workflow JSON. This module
marks the future step that will assemble validated, resolved tool calls into a
workflow request.
"""
from app.models.workflow_steps import WorkflowStep
from app.models.workflow_transport import WorkflowRequest


def build_workflow(dataset_id: str, steps: list[WorkflowStep]) -> WorkflowRequest:
    """Build a workflow request from already parsed steps."""
    return WorkflowRequest(dataset_id=dataset_id, steps=steps)
