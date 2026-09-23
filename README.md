# DataCopilot

DataCopilot is a learning-first workflow product. It turns a natural-language data request into workflow JSON that can be checked, executed, and explained.

The design principle:

> The LLM plans. The system validates. Deterministic tools execute. The user sees the plan and confirms actions that change data.

Model capability makes the system smart. Workflow and harness make it reliable. Tools make it able to act. Product design makes it useful.

## The idea

A stronger model is not a complete data product. Around the model, the system needs context, a contract, validation, execution, a trace, and a place for the user to step in.

DataCopilot is that system, applied to one uploaded CSV:

```text
User request
-> context: schema, dataset profile, transformation docs
-> workflow JSON
-> validator and policy checks
-> preview, then confirmation when data will change
-> pandas execution
-> explanation grounded in the run result
```

Workflow JSON is the contract between planning and execution. The validator rejects unknown step types, missing columns, and invalid parameters. The executor runs pandas. The explainer summarizes the real output.

Responsibility is split on purpose:

```text
Intent understanding     model-led
Plan generation          model-assisted
Validation               rule-led
Execution                code-led
Result calculation       code-led
Result explanation       model-assisted
```

The closer a step is to the final number, the less the model is allowed to own it.

## Why workflow comes first

Many products jump to an agent: give the model a goal and let it keep acting. That story is attractive. It is also hard to verify, repeat, audit, or hand back to a person.

Workflow is the more useful first product when the job has a stable shape. A workflow can be inspected, tested, reproduced, and plugged into an existing process.

The direction I want is agent over workflow, not an agent that skips the workflow:

```text
Chat interface
-> RAG for tool and schema context
-> workflow as the contract
-> validator as the boundary
-> executor as the action
-> a controlled agent only after that contract is stable
```

`master` is the workflow-first product. `experiment/agent-loop` keeps the earlier exploration: observe, choose an action, evaluate, then continue, ask, or stop. That work shaped observation, policy, and trace. It is not the demo path. An open loop is harder to explain, and self-repair can hide risk when the contract is still soft.

## How a request is handled

```text
user query
-> query classification
-> ask mode / deterministic tool / LLM planner / clarification / unsupported
-> workflow JSON
-> validator and policy checks
-> preview
-> user confirmation when needed
-> pandas execution
-> grounded explanation and result panels
```

- Ask Mode answers schema and dataset overview questions and does not change the data.
- Deterministic tools cover high-confidence read-only work: missing values, profiling, group comparison, correlation.
- The LLM planner is still used for transformations. Every planned step must pass validation.
- Broad or ambiguous requests return clarification choices.
- Workflows that change data are previewed before confirmation.
- Unsupported requests are rejected in the open: prediction, forecasting, machine learning, arbitrary Python, and autonomous multi-agent analysis.

## What you see

The workspace has three panels:

- Dataset sidebar: upload a CSV, inspect the schema, view run history.
- Data panel: preview the upload and confirmed results.
- Chat panel: ask, see the route, preview the workflow, and confirm execution.

Each answer shows which path was taken: Ask Mode, Deterministic, LLM Planner, Clarification, or Unsupported. Warnings, route decisions, and validation failures stay visible.

## Demo

Use an orders-style CSV:

```text
order_id, region, category, amount, quantity, status
```

Ask Mode:

- `What columns are in this dataset?`

Deterministic analysis:

- `Check for missing values`
- `Compare average amount by region`

LLM workflow preview:

- `Sort by amount descending`
- `Filter rows where amount > 1000`

Clarification and schema boundary:

- `Analyze this dataset for issues`
- `Sort by revenue descending`

These prompts are there to show the route, not to prove the system can answer every data question.

## Architecture

```text
frontend/   React + TypeScript notebook, preview, timeline, route and result panels
backend/    FastAPI planning, RAG, validation, pandas execution, run history
docker/     PostgreSQL + pgvector, API, tests
```

The backend follows the same split as the product idea:

- `workflow/planning`: classification, routing, parameter resolution, workflow building, LLM planning.
- `workflow/validation`: schema and contract checks.
- `workflow/execution`: pandas.
- `workflow/observation`: warnings and diagnostic signals. Signals suggest a next action. They do not start another loop.
- `workflow/response`: explanation from the execution result.
- `services`: dataset storage, run storage, profiling.

RAG supplies transformation docs and examples. It does not replace validation.

## Boundaries

The project is judged by whether the loop closes, not by coverage of every question.

A good run selects the right route, shows an inspectable workflow, catches invalid columns, surfaces warnings, executes deterministically, and explains only what the run produced.

Current limits:

- One uploaded CSV at a time.
- No multi-file joins.
- No authentication or multi-user workspace.
- No arbitrary Python execution.
- No production-scale database integration.
- No autonomous multi-agent loop on `master`.

## Tech stack

- Backend: Python, FastAPI, Pydantic, pandas, PostgreSQL / pgvector for optional RAG storage.
- Frontend: React, TypeScript, Vite, Playwright.

## Running locally

### Backend

From `backend/`:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Optional settings in `backend/.env`:

```text
LLM_API_KEY=
LLM_MODEL=gpt-4o-mini
LLM_BASE_URL=https://api.openai.com/v1
RETRIEVAL_METHOD=keyword
```

### Frontend

From `frontend/`:

```bash
pnpm install
pnpm dev
```

### Docker

From the repository root:

```bash
docker compose -f docker/docker-compose.yml up --build
```

## Testing

```bash
cd backend
python -m pytest
```

```bash
cd frontend
pnpm lint
pnpm build
pnpm test:ui
```

## Repository

`master` is the workflow-first product and the recommended demo. `experiment/agent-loop` is the architectural research branch.
