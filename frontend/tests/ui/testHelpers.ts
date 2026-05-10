import type { Page } from '@playwright/test'

const datasetProfile = {
  filename: 'orders.csv',
  row_count: 2,
  column_count: 3,
  columns: [
    { name: 'order_id', dtype: 'int64', missing_count: 0, missing_pct: 0 },
    { name: 'region', dtype: 'object', missing_count: 0, missing_pct: 0 },
    { name: 'amount', dtype: 'float64', missing_count: 0, missing_pct: 0 },
  ],
  preview: [
    { order_id: 1, region: 'North', amount: 1200 },
    { order_id: 2, region: 'South', amount: 800 },
  ],
}

const stepResult = {
  step_index: 0,
  step_type: 'filter_rows',
  status: 'success',
  issues: [],
  input_row_count: 2,
  output_row_count: 1,
  input_column_count: 3,
  output_column_count: 3,
  affected_rows: 1,
  match_rate: 0.5,
  affected_rate: 0.5,
  preview: [{ order_id: 1, region: 'North', amount: 1200 }],
  message: 'Filtered amount > 1000.',
}

const ragContext = {
  query: 'Filter rows where amount > 1000',
  retrieved_docs: [
    {
      type: 'transformation',
      description: 'Filter rows by comparing a column with a value.',
      keywords: ['filter'],
      parameters: [],
      example: { type: 'filter_rows', column: 'amount', operator: '>', value: 1000 },
      score: 1,
    },
  ],
  dataset_summary: {
    filename: 'orders.csv',
    row_count: 2,
    column_count: 3,
    columns: datasetProfile.columns,
  },
  debug: {
    method: 'keyword',
    query_tokens: ['filter', 'amount'],
    all_scores: { filter_rows: 1 },
  },
}

export async function mockMvp3Api(page: Page) {
  await page.route('**/api/datasets/upload', async route => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ dataset_id: 'dataset-1', profile: datasetProfile }),
    })
  })
  await page.route('**/api/datasets/dataset-1/rows**', async route => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ rows: datasetProfile.preview, total_rows: 2, offset: 0, limit: 50 }),
    })
  })
  await page.route('**/api/chat', async route => {
    const body = route.request().postDataJSON()
    if (String(body.query).includes('warning')) {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          query: body.query,
          planned_steps: [{ type: 'filter_rows', column: 'amount', operator: '>', value: 9999 }],
          step_results: [{ ...stepResult, status: 'warning', issues: [{ severity: 'warning', code: 'empty_output', message: 'No rows matched.' }], output_row_count: 0, preview: [] }],
          has_warnings: true,
          has_errors: false,
          rag_context: ragContext,
          explanation: null,
          execution_result: null,
          run_id: null,
          needs_clarification: false,
          state: 'warning_review',
        }),
      })
      return
    }
    if (String(body.query).includes('missing')) {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          query: body.query,
          planned_steps: [],
          step_results: [],
          has_warnings: false,
          has_errors: false,
          rag_context: ragContext,
          explanation: null,
          execution_result: null,
          run_id: null,
          needs_clarification: true,
          clarification_question: "Column 'revenue' is not in this dataset. Which available column should I use instead?",
          state: 'needs_clarification',
        }),
      })
      return
    }
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        query: body.query,
        planned_steps: [{ type: 'filter_rows', column: 'amount', operator: '>', value: 1000 }],
        step_results: [stepResult],
        has_warnings: false,
        has_errors: false,
        rag_context: ragContext,
        explanation: null,
        execution_result: null,
        run_id: null,
        needs_clarification: false,
        state: 'preview_ready',
      }),
    })
  })
  await page.route('**/api/workflows/confirm', async route => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        query: 'Filter rows where amount > 1000',
        planned_steps: [{ type: 'filter_rows', column: 'amount', operator: '>', value: 1000 }],
        execution_result: {
          row_count: 1,
          column_count: 3,
          columns: ['order_id', 'region', 'amount'],
          preview: [{ order_id: 1, region: 'North', amount: 1200 }],
          step_results: [stepResult],
          logs: [{ step_index: 0, step_type: 'filter_rows', rows_before: 2, rows_after: 1, message: 'Filtered.' }],
          has_summary: false,
        },
        explanation: 'One order matched the filter.',
        run_id: 'run-1',
        state: 'executed',
      }),
    })
  })
  await page.route('**/api/runs?**', async route => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        runs: [{
          run_id: 'run-1',
          dataset_id: 'dataset-1',
          query: 'Filter rows where amount > 1000',
          status: 'executed',
          step_count: 1,
          row_count: 1,
          created_at: new Date().toISOString(),
          parent_run_id: null,
        }],
        total: 1,
      }),
    })
  })
  await page.route('**/api/runs/run-1', async route => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        run_id: 'run-1',
        dataset_id: 'dataset-1',
        query: 'Filter rows where amount > 1000',
        status: 'executed',
        step_count: 1,
        row_count: 1,
        created_at: new Date().toISOString(),
        parent_run_id: null,
        explanation: 'One order matched the filter.',
        planned_steps: [{ type: 'filter_rows', column: 'amount', operator: '>', value: 1000 }],
        state: 'executed',
        attempts: [{
          attempt_index: 0,
          query: 'Filter rows where amount > 1000',
          retrieval_method: 'keyword',
          retrieved_docs: [],
          planner_raw_output: '{"steps":[]}',
          parsed_steps: [{ type: 'filter_rows', column: 'amount', operator: '>', value: 1000 }],
          validation_result: { ok: true },
          repair_reason: null,
          final_status: 'executed',
          summary: {
            attempt_index: 0,
            query: 'Filter rows where amount > 1000',
            retrieval_method: 'keyword',
            retrieved_docs: ['filter_rows'],
            planner_raw_output: '{"steps":[]}',
            parsed_step_types: ['filter_rows'],
            validation_status: 'passed',
            preview_status: 'passed',
            warning_count: 0,
            error_count: 0,
            repair_reason: null,
            final_status: 'executed',
          },
        }],
        context_summary: {
          query: 'Filter rows where amount > 1000',
          dataset_hash: 'abc123',
          schema_columns: ['order_id', 'region', 'amount'],
          row_count: 2,
          retrieved_docs: ['filter_rows'],
          planned_step_types: ['filter_rows'],
          status: 'executed',
          boundary: 'executed',
          validation_status: 'passed',
          warning_count: 0,
          error_count: 0,
        },
      }),
    })
  })
  await page.route('**/api/runs/run-1/rerun', async route => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        planned_steps: [{ type: 'filter_rows', column: 'amount', operator: '>', value: 1000 }],
        step_results: [stepResult],
        has_warnings: false,
        has_errors: false,
        blocked_at_step: null,
      }),
    })
  })
}

export async function uploadOrdersCsv(page: Page) {
  await page.locator('input[type="file"]').setInputFiles('../sample_data/orders.csv')
}
