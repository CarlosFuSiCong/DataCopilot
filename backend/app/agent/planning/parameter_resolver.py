"""Future parameter resolver boundary for workflow planning."""
from typing import Any


def resolve_parameters(step: dict[str, Any]) -> dict[str, Any]:
    """Return the step unchanged until MVP5 parameter resolution is implemented."""
    return step
