import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { uploadOrdersCsv } from './testHelpers'

// ─── shared mock data ───────────────────────────────────────────────────────

const datasetProfile = {
  filename: 'orders.csv',
  row_count: 30,
  column_count: 6,
  columns: [
    { name: 'order_id', dtype: 'int64', missing_count: 0, missing_pct: 0 },
    { name: 'region', dtype: 'object', missing_count: 0, missing_pct: 0 },
    { name: 'category', dtype: 'object', missing_count: 0, missing_pct: 0 },
    { name: 'amount', dtype: 'float64', missing_count: 3, missing_pct: 10.0 },
    { name: 'quantity', dtype: 'int64', missing_count: 0, missing_pct: 0 },
    { name: 'status', dtype: 'object', missing_count: 0, missing_pct: 0 },
  ],
  preview: [
    { order_id: 1, region: 'North', category: 'A', amount: 1200, quantity: 3, status: 'completed' },
    { order_id: 2, region: 'South', category: 'B', amount: 800, quantity: 2, status: 'pending' },
    { order_id: 3, region: 'East', category: 'A', amount: 2200, quantity: 5, status: 'completed' },
  ],
}

const ragContext = {
  query: '',
  retrieved_docs: [],
  dataset_summary: {
    filename: 'orders.csv',
    row_count: 30,
    column_count: 6,
    columns: datasetProfile.columns,
  },
  debug: { method: 'keyword', query_tokens: [], all_scores: {} },
}

function makeRouteDecision(
  route: string,
  queryType: string,
  confidence: number,
  reason: string,
  selectedTool: string | null = null,
) {
  return { route, query_type: queryType, confidence, reason, selected_tool: selectedTool, fallback_route: null, evidence: [] }
}

async function mockDemoPathApi(page: Page) {
  await page.route('**/api/datasets/upload', async route => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ dataset_id: 'demo-1', profile: datasetProfile }),
    })
  })
  await page.route('**/api/datasets/demo-1/rows**', async route => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ rows: datasetProfile.preview, total_rows: 30, offset: 0, limit: 50 }),
    })
  })

  await page.route('**/api/chat', async route => {
    const body = route.request().postDataJSON()
    const query = String(body?.query ?? '').toLowerCase()

    // M7-01 / M7-02 — Ask Mode
    if (query.includes('字段') || query.includes('columns') || query.includes('多少行') || query.includes('how many rows')) {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          query: body.query,
          planned_steps: [],
          step_results: [],
          has_warnings: false,
          has_errors: false,
          rag_context: { ...ragContext, query: body.query },
          explanation: 'The dataset has 30 rows and 6 columns: order_id, region, category, amount, quantity, status. The amount column has 3 missing values (10.0%).',
          execution_result: null,
          run_id: null,
          needs_clarification: false,
          state: 'executed',
          is_read_only: true,
          ask_mode_type: 'schema_overview',
          evidence_source: 'schema',
          route_decision: makeRouteDecision('ask_mode', 'ask', 0.95, 'Schema question answered in Ask Mode.'),
        }),
      })
      return
    }

    // M7-03 — Broad analysis clarification
    if (query.includes('什么问题') || query.includes('broad') || query.includes('analyse') || query.includes('analyze')) {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          query: body.query,
          planned_steps: [],
          step_results: [],
          has_warnings: false,
          has_errors: false,
          rag_context: { ...ragContext, query: body.query },
          explanation: null,
          execution_result: null,
          run_id: null,
          needs_clarification: true,
          clarification_question: 'What aspect of the data would you like to investigate?',
          broad_analysis_choices: [
            { id: 'missing', label: 'Check for missing values', description: 'Scan all columns for null / NaN values.', query: 'Check for missing values', tool: 'detect_missing_values' },
            { id: 'duplicates', label: 'Check for duplicate rows', description: 'Identify records that appear more than once.', query: 'Check for duplicate rows', tool: 'deduplicate_rows' },
            { id: 'profile_amount', label: 'Profile the amount column', description: 'Show distribution and statistics for amount.', query: 'Profile the amount column', tool: 'profile_column' },
          ],
          state: 'needs_clarification',
          route_decision: makeRouteDecision('clarification', 'broad_analysis_request', 0.88, 'Broad analysis request requires user to select a direction.'),
        }),
      })
      return
    }

    // M7-04 — detect_missing_values
    if (query.includes('missing values') || query.includes('缺失值')) {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          query: body.query,
          planned_steps: [{ type: 'detect_missing_values' }],
          step_results: [{
            step_index: 0,
            step_type: 'detect_missing_values',
            status: 'success',
            issues: [],
            input_row_count: 30,
            output_row_count: 6,
            input_column_count: 6,
            output_column_count: 3,
            affected_rows: 3,
            match_rate: null,
            affected_rate: null,
            preview: [
              { column: 'amount', missing_count: 3, missing_pct: '10.0%' },
              { column: 'order_id', missing_count: 0, missing_pct: '0.0%' },
              { column: 'region', missing_count: 0, missing_pct: '0.0%' },
              { column: 'category', missing_count: 0, missing_pct: '0.0%' },
              { column: 'quantity', missing_count: 0, missing_pct: '0.0%' },
              { column: 'status', missing_count: 0, missing_pct: '0.0%' },
            ],
            message: '1 column has missing values. amount: 3 missing (10.0%).',
          }],
          has_warnings: false,
          has_errors: false,
          rag_context: { ...ragContext, query: body.query },
          explanation: null,
          execution_result: null,
          run_id: null,
          needs_clarification: false,
          state: 'preview_ready',
          route_decision: makeRouteDecision('deterministic_tool', 'diagnosis', 0.93, 'Missing value detection matched deterministic tool.', 'detect_missing_values'),
        }),
      })
      return
    }

    // M7-06 — compare_groups (deterministic)
    if (query.includes('compare') || query.includes('average amount by region')) {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          query: body.query,
          planned_steps: [{ type: 'compare_groups', group_column: 'region', value_column: 'amount', agg: 'mean' }],
          step_results: [{
            step_index: 0,
            step_type: 'compare_groups',
            status: 'success',
            issues: [],
            input_row_count: 30,
            output_row_count: 4,
            input_column_count: 6,
            output_column_count: 3,
            affected_rows: 0,
            match_rate: null,
            affected_rate: null,
            preview: [
              { region: 'East', mean: 1950.0, count: 8 },
              { region: 'North', mean: 1100.0, count: 9 },
              { region: 'South', mean: 850.0, count: 7 },
              { region: 'West', mean: 1300.0, count: 6 },
            ],
            message: "Compared 'amount' by 'region' (mean): 4 groups.",
          }],
          has_warnings: false,
          has_errors: false,
          rag_context: { ...ragContext, query: body.query },
          explanation: null,
          execution_result: null,
          run_id: null,
          needs_clarification: false,
          state: 'preview_ready',
          route_decision: makeRouteDecision('deterministic_tool', 'comparison', 0.91, 'Group comparison query matched deterministic compare_groups tool.', 'compare_groups'),
        }),
      })
      return
    }

    // M7-07 — sort by revenue (missing column clarification)
    if (query.includes('revenue')) {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          query: body.query,
          planned_steps: [],
          step_results: [],
          has_warnings: false,
          has_errors: false,
          rag_context: { ...ragContext, query: body.query },
          explanation: null,
          execution_result: null,
          run_id: null,
          needs_clarification: true,
          clarification_question: "Column 'revenue' is not in this dataset. Which available column should I use instead? Available columns: order_id, region, category, amount, quantity, status.",
          state: 'needs_clarification',
          route_decision: makeRouteDecision('clarification', 'sorting', 0.84, 'Missing column revenue requires user clarification.'),
        }),
      })
      return
    }

    // M7-10 / M7-11 — filter rows (large_row_removal warning + observation + timeline)
    if (query.includes('filter') || query.includes('amount > 1000')) {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          query: body.query,
          planned_steps: [{ type: 'filter_rows', column: 'amount', operator: '>', value: 1000 }],
          step_results: [{
            step_index: 0,
            step_type: 'filter_rows',
            status: 'warning',
            issues: [{ severity: 'warning', code: 'large_row_removal', message: '8 of 30 rows remain (73% removed).' }],
            input_row_count: 30,
            output_row_count: 8,
            input_column_count: 6,
            output_column_count: 6,
            affected_rows: 22,
            match_rate: 0.267,
            affected_rate: 0.733,
            preview: datasetProfile.preview,
            message: '8 of 30 rows matched.',
          }],
          has_warnings: true,
          has_errors: false,
          rag_context: { ...ragContext, query: body.query },
          explanation: null,
          execution_result: null,
          run_id: null,
          needs_clarification: false,
          state: 'warning_review',
          route_decision: makeRouteDecision('llm_planner', 'filtering', 0.87, 'Mutating filter workflow sent to LLM planner.'),
          observation: {
            status: 'warning',
            signals: ['large_row_removal'],
            message: '73% of rows will be removed.',
            possible_causes: ['The filter threshold may be too strict.'],
            recommended_next_action: 'confirm',
            workflow_state: 'warning_review',
            diagnostic_explanation: 'A large proportion of rows will be removed by this filter. Verify that the threshold is intentional.',
            candidate_fixes: [
              { id: 'relax', label: 'Relax filter', description: 'Try a lower threshold to keep more rows.', action_type: 'relax_filter', query: 'Filter rows where amount > 500' },
              { id: 'inspect', label: 'Inspect amount column', description: 'Profile the amount column to understand the distribution.', action_type: 'inspect_column', query: 'Profile the amount column' },
            ],
          },
        }),
      })
      return
    }

    // M7-13 — unsupported (prediction)
    if (query.includes('predict') || query.includes('forecast')) {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          query: body.query,
          planned_steps: [],
          step_results: [],
          has_warnings: false,
          has_errors: true,
          rag_context: { ...ragContext, query: body.query },
          explanation: null,
          execution_result: null,
          run_id: null,
          needs_clarification: false,
          state: 'unsupported',
          route_decision: makeRouteDecision('unsupported', 'unsupported_request', 0.94, 'Forecasting and ML predictions are not supported.'),
        }),
      })
      return
    }

    // Default — sort by amount (corrected workflow after clarification)
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        query: body.query,
        planned_steps: [{ type: 'sort_values', column: 'amount', ascending: false }],
        step_results: [{
          step_index: 0,
          step_type: 'sort_values',
          status: 'success',
          issues: [],
          input_row_count: 30,
          output_row_count: 30,
          input_column_count: 6,
          output_column_count: 6,
          affected_rows: 30,
          match_rate: 1,
          affected_rate: 1,
          preview: datasetProfile.preview,
          message: 'Sorted by amount descending.',
        }],
        has_warnings: false,
        has_errors: false,
        rag_context: { ...ragContext, query: body.query },
        explanation: null,
        execution_result: null,
        run_id: null,
        needs_clarification: false,
        state: 'preview_ready',
        route_decision: makeRouteDecision('llm_planner', 'sorting', 0.88, 'Sort workflow after clarification resolved.'),
      }),
    })
  })

  await page.route('**/api/workflows/confirm', async route => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        query: 'Sort by amount descending',
        planned_steps: [{ type: 'sort_values', column: 'amount', ascending: false }],
        execution_result: {
          row_count: 30,
          column_count: 6,
          columns: ['order_id', 'region', 'category', 'amount', 'quantity', 'status'],
          preview: datasetProfile.preview,
          step_results: [],
          logs: [],
          has_summary: false,
        },
        explanation: 'Rows sorted by amount in descending order. The highest amount is 2200 in the East region.',
        run_id: 'run-demo-1',
        state: 'executed',
      }),
    })
  })
}

// ─── tests ──────────────────────────────────────────────────────────────────

// M7-01: Ask Mode — schema query shows Ask Mode badge
test('M7-01: Ask Mode badge and read-only answer for schema query', async ({ page }) => {
  await mockDemoPathApi(page)
  await page.goto('/')
  await uploadOrdersCsv(page)

  await page.getByPlaceholder('Ask a question about your data…').fill('这个数据有哪些字段？')
  await page.keyboard.press('Enter')

  await expect(page.getByText('Ask Mode')).toBeVisible()
  await expect(page.getByText('read-only')).toBeVisible()
  await expect(page.getByText(/order_id.*region.*category|6 columns/i)).toBeVisible()
})

// M7-03: Broad analysis returns clarification choices not a workflow
test('M7-03: Broad analysis query returns clarification choices', async ({ page }) => {
  await mockDemoPathApi(page)
  await page.goto('/')
  await uploadOrdersCsv(page)

  await page.getByPlaceholder('Ask a question about your data…').fill('帮我看看这个数据有什么问题')
  await page.keyboard.press('Enter')

  await expect(page.getByText('Check for missing values')).toBeVisible()
  await expect(page.getByText('Check for duplicate rows')).toBeVisible()
})

// M7-04: Diagnostic detect_missing_values — Deterministic badge + data quality result
test('M7-04: detect_missing_values shows Deterministic badge and data quality panel', async ({ page }) => {
  await mockDemoPathApi(page)
  await page.goto('/')
  await uploadOrdersCsv(page)

  await page.getByPlaceholder('Ask a question about your data…').fill('Check for missing values')
  await page.keyboard.press('Enter')

  await expect(page.getByText('Deterministic')).toBeVisible()
  await expect(page.locator('[data-testid="analytics-summary-panel"]')).toBeVisible()
})

// M7-06: compare_groups routes deterministically and shows Group Comparison panel
test('M7-06: compare_groups shows Deterministic badge and Group Comparison panel', async ({ page }) => {
  await mockDemoPathApi(page)
  await page.goto('/')
  await uploadOrdersCsv(page)

  await page.getByPlaceholder('Ask a question about your data…').fill('Compare average amount by region')
  await page.keyboard.press('Enter')

  await expect(page.getByText('Deterministic')).toBeVisible()
  await expect(page.locator('[data-testid="analytics-summary-panel"]')).toBeVisible()
  await expect(page.getByText('Group Comparison')).toBeVisible()
  await expect(page.getByText('East')).toBeVisible()
})

// M7-07: Missing column triggers clarification (slot validation)
test('M7-07: Sort by missing column revenue triggers clarification', async ({ page }) => {
  await mockDemoPathApi(page)
  await page.goto('/')
  await uploadOrdersCsv(page)

  await page.getByPlaceholder('Ask a question about your data…').fill('Sort by revenue descending')
  await page.keyboard.press('Enter')

  await expect(page.getByText(/revenue.*not in this dataset|Column.*revenue/i)).toBeVisible()
  await expect(page.getByText(/available columns|amount/i)).toBeVisible()
})

// M7-10: Filter with large_row_removal shows ObservationPanel with signal and fix buttons
test('M7-10: ObservationPanel shows large_row_removal signal and candidate fix buttons', async ({ page }) => {
  await mockDemoPathApi(page)
  await page.goto('/')
  await uploadOrdersCsv(page)

  await page.getByPlaceholder('Ask a question about your data…').fill('Filter rows where amount > 1000')
  await page.keyboard.press('Enter')

  await expect(page.locator('[data-testid="observation-panel"]')).toBeVisible()
  await expect(page.getByText('large_row_removal')).toBeVisible()
})

// M7-11: WorkflowTimeline is visible after filter response
test('M7-11: WorkflowTimeline is visible in filter response', async ({ page }) => {
  await mockDemoPathApi(page)
  await page.goto('/')
  await uploadOrdersCsv(page)

  await page.getByPlaceholder('Ask a question about your data…').fill('Filter rows where amount > 1000')
  await page.keyboard.press('Enter')

  await expect(page.locator('[data-testid="workflow-timeline"]')).toBeVisible()
  await expect(page.getByText('Plan')).toBeVisible()
  await expect(page.getByText('Execute')).toBeVisible()
})

// M7-12: RouteDecisionPanel collapsed and expandable for compare_groups
test('M7-12: RouteDecisionPanel collapsed by default and expands on click', async ({ page }) => {
  await mockDemoPathApi(page)
  await page.goto('/')
  await uploadOrdersCsv(page)

  await page.getByPlaceholder('Ask a question about your data…').fill('Compare average amount by region')
  await page.keyboard.press('Enter')

  await expect(page.getByText('Route Decision Debug')).toBeVisible()
  await page.getByText('Route Decision Debug').click()
  await expect(page.getByText('Group comparison query matched deterministic compare_groups tool.')).toBeVisible()
})

// M7-13: Unsupported request shows Unsupported badge
test('M7-13: Unsupported prediction request shows Unsupported badge', async ({ page }) => {
  await mockDemoPathApi(page)
  await page.goto('/')
  await uploadOrdersCsv(page)

  await page.getByPlaceholder('Ask a question about your data…').fill("Predict next month's sales")
  await page.keyboard.press('Enter')

  await expect(page.getByText('Unsupported')).toBeVisible()
})
