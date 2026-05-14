# Evaluation

This layer will decide whether an Agent iteration has satisfied the current step or task.

Current status:

- MVP5 skeleton only.
- Existing hard validation lives in `agent.execution.validator`.

Future work:

- Evaluate observations against success criteria.
- Decide whether to continue, retry, replan, ask for clarification, or stop.
