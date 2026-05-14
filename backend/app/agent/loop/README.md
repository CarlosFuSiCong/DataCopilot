# Loop

This layer owns workflow state, Agent state, trace, and future orchestration.

Current modules:

- `runtime_models`: workflow runtime state and trace contracts.
- `agent_models`: controlled Agent trace contracts.
- `workflow_runtime`: workflow state, attempts, summaries, and one repair pass.

Future work:

- Controlled Agent orchestration service with bounded iterations.
