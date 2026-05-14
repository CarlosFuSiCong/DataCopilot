"""Future intent parser boundary for MVP5 planner decomposition."""
from app.workflow.intake.intent import ParsedTaskIntent


def parse_intent(query: str) -> ParsedTaskIntent:
    """Return a minimal intent object without changing current planner behavior.

    The full MVP5 implementation will classify intent, constraints, candidate
    columns, and missing information. For now this keeps the boundary explicit.
    """
    return ParsedTaskIntent(intent="unknown", goal=query)
