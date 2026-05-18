# DataCopilot

DataCopilot is a learning-first AI workflow prototype that demonstrates how natural-language data requests can be converted into inspectable, validated, and executable workflows.

The project is built around one core idea: the LLM should not directly invent final data answers. Instead, it should help plan a structured workflow, while deterministic code validates the plan, executes it on real data, and explains the result from actual execution evidence.

## What This Project Demonstrates

DataCopilot is designed as a demonstration project for reliable AI workflow architecture, not a production analytics platform. It demonstrates how an AI data assistant can be made more trustworthy by separating:

- Intent understanding from execution.
- Workflow planning from validation.
- Read-only questions from dataset-changing transformations.
- Preview from confirmed execution.
- Explanations from actual run results.

The current demo supports one uploaded CSV at a time and focuses on transparent workflow execution rather than broad autonomous analysis.

## Two Branch Ideas

This repository has explored two product directions.

### 1. Workflow-First Product Branch

Main branch idea: `baseline/workflow-no-loop`

This is the current recommended demo path.

The workflow-first branch treats workflow JSON as the contract between AI planning and deterministic execution:

```text
user query
-> query classification
-> ask mode / deterministic tool / LLM planner / clarification / unsupported
-> workflow JSON
-> validator and policy checks
-> preview
-> user confirmation when needed
-> deterministic pandas execution
-> grounded explanation and UI result panels
```

Why this direction:

- Easier to explain to viewers.
- More stable for demos.
- Clearer trust boundary.
- Better suited to MVP evaluation.
- Avoids hidden autonomous loops.

Important behaviors:

- Ask Mode answers schema or dataset overview questions without mutating data.
- Deterministic analytical tools handle high-confidence read-only tasks such as missing-value checks, profiling, group comparison, and correlation summaries.
- LLM planning is still available for transformations, but every planned step must pass validation.
- Broad or ambiguous requests produce clarification choices instead of guessing.
- Mutating workflows are previewed before confirmation.

### 2. Agent-Loop Exploration Branch

Example branch idea: `experiment/agent-loop` and earlier Agent-oriented feature branches.

The Agent-loop direction explored a more autonomous assistant architecture:

```text
user task
-> agent state
-> retrieve context
-> select action
-> plan workflow
-> execute or observe
-> evaluate result
-> decide whether to continue, retry, replan, ask user, or stop
```

Why this direction was useful:

- It explored how an AI data assistant might manage multi-step tasks.
- It introduced concepts such as observation, policy decisions, evaluation, and agent trace.
- It helped identify what should be deterministic before adding more autonomy.

Why it is not the current main demo path:

- Autonomous loops are harder to make reliable in a small MVP.
- The user-facing behavior is harder to explain.
- Replanning and self-repair can hide risk if not tightly controlled.
- The product is more convincing when the workflow contract is explicit first.

In short: the Agent work informed the architecture, but the current product branch intentionally narrows the system into a workflow-first AI product.

## Current Product Flow

The current frontend presents a three-panel workspace:

- Dataset sidebar: upload CSV, inspect schema, view run history.
- Data panel: preview uploaded data and confirmed results.
- Chat panel: ask questions, choose query mode, inspect route decisions, preview workflows, and confirm execution.

The chat UI exposes several productized states:

- `Ask Mode`: read-only dataset questions.
- `Deterministic`: high-confidence analytical tools.
- `LLM Planner`: transformation workflows planned from natural language.
- `Clarification`: schema-aware or ambiguity-aware follow-up choices.
- `Unsupported`: explicit rejection of out-of-scope requests.

## Demo Path

A typical demo uses an orders-style CSV with fields such as:

```text
order_id, region, category, amount, quantity, status
```

Suggested demo prompts by route:

Ask Mode:

- `What columns are in this dataset?`

Deterministic Analysis:

- `Check for missing values`
- `Compare average amount by region`

LLM Workflow Preview:

- `Sort by amount descending`
- `Filter rows where amount > 1000`

Clarification / Boundary:

- `Analyze this dataset for issues`
- `Sort by revenue descending`

These prompts are intended to make route decisions visible: Ask Mode, deterministic analysis, LLM workflow preview, warning review, clarification, and schema boundary handling.

## Architecture Overview

```text
frontend/
  React + TypeScript UI
  Notebook-style chat
  Dataset preview and result panels
  Workflow timeline, route decision, observation, and analytics panels

backend/
  FastAPI API
  Workflow planning and routing
  RAG context retrieval
  Validation and policy checks
  Pandas execution engine
  Run history and local artifact storage

docker/
  PostgreSQL + pgvector service
  Backend API service
  Backend test service
```

Core backend areas:

- `workflow/planning`: query classification, route decision, tool routing, parameter resolution, workflow building, LLM planning.
- `workflow/validation`: schema and workflow contract validation.
- `workflow/execution`: deterministic pandas execution.
- `workflow/observation`: warning and diagnostic signal generation.
- `workflow/response`: grounded result explanation.
- `services`: dataset storage, run storage, profiling.

## Trust And Safety Boundaries

DataCopilot intentionally keeps several boundaries visible:

- It does not execute arbitrary model-generated code.
- It rejects unknown workflow step types.
- It validates column references against the active dataset.
- It does not silently mutate the dataset for read-only questions.
- It does not hide warnings, route decisions, or validation failures.
- It treats prediction, forecasting, machine learning, and autonomous multi-agent analysis as unsupported for the MVP.

## Evaluation Mindset

The project is evaluated by whether it closes the workflow loop, not by whether it can answer every data question.

Good outcomes:

- The system selects the right route.
- The workflow is inspectable.
- Invalid columns are caught.
- Warnings are visible.
- Execution is deterministic.
- Explanations are grounded in real outputs.

Known MVP limits:

- One uploaded CSV at a time.
- No multi-file joins.
- No authentication or multi-user workspace.
- No arbitrary Python execution.
- No production-scale database integration.
- No autonomous multi-agent loop in the main product branch.

## Tech Stack

Backend:

- Python
- FastAPI
- Pydantic
- pandas
- PostgreSQL / pgvector for optional RAG storage

Frontend:

- React
- TypeScript
- Vite
- Playwright UI tests

## Running Locally

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

Optional environment variables can be placed in `backend/.env`:

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

### Docker Backend Stack

From the repository root:

```bash
docker compose -f docker/docker-compose.yml up --build
```

## Testing

Backend:

```bash
cd backend
python -m pytest
```

Frontend:

```bash
cd frontend
pnpm lint
pnpm build
pnpm test:ui
```

## Repository Status

The current product direction is workflow-first. The Agent-loop direction remains useful as architectural research, but the recommended showcase path is the stable workflow product branch.
