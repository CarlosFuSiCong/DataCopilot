# Agent Package

This package organizes the backend by Agent runtime layers. The goal is to make the workflow-first runtime easier to study and extend without changing the public API behavior.

Current layers:

- `task_intake`: user goal and intent contracts.
- `context`: dataset context, RAG, retrieval, and context assembly.
- `policy`: deterministic action policy and execution boundaries.
- `planning`: workflow planning and future planner decomposition.
- `tool_selection`: tool registry and future tool selection logic.
- `execution`: validation and deterministic workflow execution.
- `observation`: risk signals and dataset observation tools.
- `evaluation`: future Agent step and task evaluation.
- `loop`: workflow/Agent state, trace, and future orchestration.
- `final_response`: grounded result explanation and final reporting.
