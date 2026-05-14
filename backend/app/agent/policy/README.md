# Policy

This layer owns deterministic action policy and guardrails.

Current modules:

- `models`: policy decision contracts.
- `action_policy`: workflow action policy enforcement.

Policy must remain independent from the LLM planner. It decides which actions are automatic, preview-only, require confirmation, or are blocked.
