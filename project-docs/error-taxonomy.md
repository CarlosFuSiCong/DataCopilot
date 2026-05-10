# Error Taxonomy And Frontend Rendering Contract

DataCopilot uses structured `error_code` values so the frontend can render actionable UI instead of generic failure text.

## Contract

Backend application errors return:

```json
{
  "error": "Human-readable message",
  "error_code": "machine_readable_code",
  "context": {}
}
```

Frontend rules:

- Always show `error`.
- Use `error_code` to choose the rendering panel.
- Use `context` only as supporting detail; never rely on natural-language parsing.
- If an unknown `error_code` appears, fall back to a generic error panel.

## Error Codes

### `missing_column`

Meaning: a workflow references a column that is not available at that point in the dataset or chained workflow.

Typical context:

- `available_columns`: columns the user can choose from.

Frontend rendering:

- Show the missing-column message.
- Render available columns as selectable or copyable chips.
- Suggest rewriting the query using an available column.

Current behavior:

- Chat planning prefers clarification for missing columns.
- Runtime execution errors may still surface `missing_column` if a step fails after preview.

### `empty_workflow`

Meaning: the planner could not produce a supported workflow for the request.

Typical context:

- `planner_hint`
- `relevant_steps`
- `supported_steps`
- `example_queries`

Frontend rendering:

- Show the planner limitation.
- Prefer `relevant_steps` cards when available.
- Fall back to supported operation chips and example queries.

### `rag_no_hits`

Meaning: retrieval found no useful workflow documentation for the query.

Typical context:

- `retrieval_method`
- `query`
- `suggestion`

Frontend rendering:

- Explain that the request could not be grounded in known workflow docs.
- Show the suggestion and ask the user to rephrase with a supported operation.

### `execution_error`

Meaning: deterministic execution failed after planning and validation.

Typical context:

- `failed_step_index`
- `failed_step_type`
- `available_columns`
- `suggestion`

Frontend rendering:

- Show the failing step type and index.
- Show available columns when present.
- Preserve the execution boundary: do not auto-confirm or retry.

### `export_too_large`

Meaning: the requested result CSV export exceeds the configured backend size limit.

Typical context:

- `size_bytes`
- `limit_bytes`

Frontend rendering:

- Show the size limit.
- Suggest filtering rows or selecting fewer columns before exporting.

### `download_not_found`

Meaning: a dataset or run artifact cannot be found in storage.

Typical context:

- `suggestion`

Frontend rendering:

- Explain that the artifact may have been removed.
- Suggest re-uploading the dataset or re-executing the workflow.

## Runtime Trace Display

Run detail responses may also include:

- `state`
- `attempts`
- `context_summary`

Frontend rendering:

- Use `state` / `status` for history filtering and status chips.
- Show `context_summary` before full trace.
- Show attempt summaries by default.
- Only expand raw planner output or full trace when the user asks for details.
