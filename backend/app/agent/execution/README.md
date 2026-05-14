# Execution

This layer owns deterministic validation and workflow execution.

Current modules:

- `validator`: validates workflow structure and dataset column references.
- `executor`: runs validated workflow steps with pandas and returns structured results.

Execution must not run arbitrary model-generated code.
