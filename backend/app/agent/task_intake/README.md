# Task Intake

This layer turns a user request into structured task intent for the rest of the Agent runtime.

Current status:

- MVP5 skeleton only.
- Existing behavior still enters through the chat request and workflow planner.

Future work:

- Parse task type, goal, constraints, candidate columns, and missing information.
- Keep clarification context local to the current run or session.
