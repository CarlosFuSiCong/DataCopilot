/**
 * Task 12: UI Smoke and Demo Path — MVP5 Agent Trace
 *
 * Five targeted smoke tests covering the Agent-loop UI scenarios added in
 * MVP5. All backend calls are intercepted with route mocks so no real
 * server is required.
 */
import { expect, test, type Page } from '@playwright/test'
import { uploadOrdersCsv } from './testHelpers'

// ─── Shared mock data ─────────────────────────────────────────────────────────

const datasetProfile = {
  filename: 'orders.csv',
  row_count: 2,
  column_count: 3,
  columns: [
    { name: 'order_id', dtype: 'int64',    missing_count: 0, missing_pct: 0 },
    { name: 'region',   dtype: 'object',   missing_count: 0, missing_pct: 0 },
    { name: 'amount',   dtype: 'float64',  missing_count: 0, missing_pct: 0 },
  ],
  preview: [
    { order_id: 1, region: 'North', amount: 1200 },
    { order_id: 2, region: 'South', amount: 800 },
  ],
}

const filterStep = { type: 'filter_rows', column: 'amount', operator: '>', value: 1000 }

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

const attempt = {
  attempt_index: 0,
  query: 'Filter rows where amount > 1000',
  retrieval_method: 'keyword',
  retrieved_docs: [],
  planner_raw_output: '{"steps":[]}',
  parsed_steps: [filterStep],
  validation_result: { ok: true },
  repair_reason: null,
  final_status: 'preview',
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
    final_status: 'preview',
  },
}

const previewReadyResponse = {
  query: 'Filter rows where amount > 1000',
  planned_steps: [filterStep],
  step_results: [stepResult],
  has_warnings: false,
  has_errors: false,
  rag_context: null,
  explanation: null,
  execution_result: null,
  run_id: null,
  needs_clarification: false,
  state: 'preview_ready',
  attempts: [attempt],
}

// ─── Setup helpers ────────────────────────────────────────────────────────────

async function setupDataset(page: Page) {
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
  // Stub run history so the sidebar doesn't produce network errors.
  await page.route('**/api/runs**', async route => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ runs: [], total: 0 }),
    })
  })
}

async function setupConfirm(page: Page) {
  await page.route('**/api/workflows/confirm', async route => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        query: 'Filter rows where amount > 1000',
        planned_steps: [filterStep],
        execution_result: {
          row_count: 1,
          column_count: 3,
          columns: ['order_id', 'region', 'amount'],
          preview: [{ order_id: 1, region: 'North', amount: 1200 }],
          step_results: [stepResult],
          logs: [],
          has_summary: false,
        },
        explanation: 'One order matched the filter.',
        run_id: 'run-1',
        state: 'executed',
      }),
    })
  })
}

// ─── Tests ────────────────────────────────────────────────────────────────────

/**
 * Scenario 1: Agent one-iteration success
 * Query → preview_ready (1 attempt) → user confirms → explanation shown.
 */
test('agent one-iteration success: trace panel and confirm button are visible', async ({ page }) => {
  await setupDataset(page)
  await page.route('**/api/chat', async route => {
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(previewReadyResponse) })
  })
  await setupConfirm(page)

  await page.goto('/')
  await uploadOrdersCsv(page)
  await page.getByPlaceholder('Ask a question about your data…').fill('Filter rows where amount > 1000')
  await page.keyboard.press('Enter')

  // Agent trace panel renders with summary.
  await expect(page.getByText('agent trace')).toBeVisible()
  // Waiting for user confirmation.
  await expect(page.getByText('needs confirm')).toBeVisible()
  // Confirm button is present (exact match avoids collision with the agent trace header button).
  await expect(page.getByRole('button', { name: 'Confirm', exact: true })).toBeVisible()

  // Confirm executes the workflow.
  await page.getByRole('button', { name: 'Confirm', exact: true }).click()
  await expect(page.getByText('One order matched the filter.')).toBeVisible()
})

/**
 * Scenario 2: Clarification answer continues to preview
 * Query with unknown column → clarification panel → user answers → preview_ready.
 */
test('clarification answer continues to workflow preview', async ({ page }) => {
  await setupDataset(page)

  let callCount = 0
  await page.route('**/api/chat', async route => {
    callCount++
    if (callCount === 1) {
      // First call: column not found → needs clarification.
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          query: 'Filter rows where revenue > 1000',
          planned_steps: [],
          step_results: [],
          has_warnings: false,
          has_errors: false,
          rag_context: null,
          explanation: null,
          execution_result: null,
          run_id: null,
          needs_clarification: true,
          clarification_question: "Column 'revenue' is not in this dataset. Which available column should I use instead?",
          clarification_context: {
            dataset_id: 'dataset-1',
            original_query: 'Filter rows where revenue > 1000',
            question: "Column 'revenue' is not in this dataset. Which available column should I use instead?",
            user_answer: null,
            resolved_parameter: null,
            affected_step: { type: 'filter_rows', column: 'revenue' },
            status: 'pending',
            scope_key: 'scope-1',
          },
          state: 'needs_clarification',
          attempts: [],
        }),
      })
    } else {
      // Second call (with clarification context) → preview_ready.
      const body = route.request().postDataJSON()
      expect(body.clarification_context).toMatchObject({
        dataset_id: 'dataset-1',
        original_query: 'Filter rows where revenue > 1000',
        user_answer: 'amount',
        affected_step: { type: 'filter_rows', column: 'revenue' },
        status: 'pending',
      })
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ ...previewReadyResponse, query: 'Filter rows where revenue > 1000' }),
      })
    }
  })

  await page.goto('/')
  await uploadOrdersCsv(page)
  await page.getByPlaceholder('Ask a question about your data…').fill('Filter rows where revenue > 1000')
  await page.keyboard.press('Enter')

  // Clarification panel appears.
  await expect(page.getByText("Column 'revenue' is not in this dataset. Which available column should I use instead?")).toBeVisible()
  await expect(page.getByPlaceholder('Type your answer…')).toBeVisible()

  // User submits the clarification answer.
  await page.getByPlaceholder('Type your answer…').fill('amount')
  await page.getByRole('button', { name: 'Send' }).click()

  // After answering, the workflow preview is shown.
  await expect(page.getByRole('button', { name: 'Confirm', exact: true })).toBeVisible()
})

/**
 * Scenario 3: Warning requires confirmation
 * Filter produces a warning → warning banner shown → Confirm button still present.
 */
test('warning state shows review banner and confirm button', async ({ page }) => {
  await setupDataset(page)

  const warningAttempt = {
    ...attempt,
    final_status: 'warning',
    summary: { ...attempt.summary, preview_status: 'warning', warning_count: 1, final_status: 'warning' },
  }

  await page.route('**/api/chat', async route => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        query: 'Filter rows where amount > 9999',
        planned_steps: [{ type: 'filter_rows', column: 'amount', operator: '>', value: 9999 }],
        step_results: [{
          ...stepResult,
          status: 'warning',
          issues: [{ severity: 'warning', code: 'empty_output', message: 'No rows matched.' }],
          output_row_count: 0,
          preview: [],
        }],
        has_warnings: true,
        has_errors: false,
        rag_context: null,
        explanation: null,
        execution_result: null,
        run_id: null,
        needs_clarification: false,
        state: 'warning_review',
        attempts: [warningAttempt],
      }),
    })
  })

  await page.goto('/')
  await uploadOrdersCsv(page)
  await page.getByPlaceholder('Ask a question about your data…').fill('Filter rows where amount > 9999')
  await page.keyboard.press('Enter')

  // Warning banner is shown.
  await expect(page.getByText('Workflow has warnings — review before confirming.')).toBeVisible()
  // Agent trace panel is visible.
  await expect(page.getByText('agent trace')).toBeVisible()
  // Confirm button is still available so the user can proceed.
  await expect(page.getByRole('button', { name: 'Confirm', exact: true })).toBeVisible()
})

/**
 * Scenario 4: Agent trace panel expands to show iteration details
 * Shows summary row → click expand → stop reason and iteration list appear.
 */
test('agent trace panel expands to show stop reason and iteration rows', async ({ page }) => {
  await setupDataset(page)
  await page.route('**/api/chat', async route => {
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(previewReadyResponse) })
  })

  await page.goto('/')
  await uploadOrdersCsv(page)
  await page.getByPlaceholder('Ask a question about your data…').fill('Filter rows where amount > 1000')
  await page.keyboard.press('Enter')

  // Collapsed summary is shown.
  await expect(page.getByText('agent trace')).toBeVisible()
  await expect(page.getByText('▼ expand')).toBeVisible()

  // Click to expand the trace panel.
  await page.getByText('▼ expand').click()

  // Expanded view shows stop reason label and collapse toggle.
  await expect(page.getByText('stop reason')).toBeVisible()
  await expect(page.getByText('▲ collapse')).toBeVisible()

  // Iteration row with step type badge is visible.
  await expect(page.getByText('filter_rows').first()).toBeVisible()
})

/**
 * Scenario 5: Blocked action rendering
 * Workflow has errors → blocked panel shown → no Confirm button.
 */
test('blocked action shows error block and no confirm button', async ({ page }) => {
  await setupDataset(page)

  const blockedAttempt = {
    ...attempt,
    final_status: 'failed',
    summary: { ...attempt.summary, preview_status: 'error', error_count: 1, final_status: 'failed' },
  }

  await page.route('**/api/chat', async route => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        query: 'Filter rows where amount > 1000',
        planned_steps: [filterStep],
        step_results: [{
          ...stepResult,
          status: 'error',
          issues: [{ severity: 'error', code: 'execution_error', message: 'Column not found.' }],
          output_row_count: 0,
          preview: [],
        }],
        has_warnings: false,
        has_errors: true,
        rag_context: null,
        explanation: null,
        execution_result: null,
        run_id: null,
        needs_clarification: false,
        state: 'preview_ready',
        attempts: [blockedAttempt],
      }),
    })
  })

  await page.goto('/')
  await uploadOrdersCsv(page)
  await page.getByPlaceholder('Ask a question about your data…').fill('Filter rows where amount > 1000')
  await page.keyboard.press('Enter')

  // Blocked message is shown.
  await expect(page.getByText('Execution blocked: the workflow has errors. Review the issues above and revise your query.')).toBeVisible()
  // Agent trace header button reflects the failed state (avoid matching hidden <option> elements).
  await expect(page.getByRole('button').filter({ hasText: 'agent trace' }).filter({ hasText: 'failed' })).toBeVisible()
  // No Confirm button when execution is blocked.
  await expect(page.getByRole('button', { name: 'Confirm', exact: true })).not.toBeVisible()
})
