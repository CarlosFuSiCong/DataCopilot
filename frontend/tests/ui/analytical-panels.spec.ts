import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { uploadOrdersCsv } from './testHelpers'

// ─── shared helpers ────────────────────────────────────────────────────────────

const datasetProfile = {
  filename: 'orders.csv',
  row_count: 4,
  column_count: 3,
  columns: [
    { name: 'order_id', dtype: 'int64', missing_count: 0, missing_pct: 0 },
    { name: 'region', dtype: 'object', missing_count: 0, missing_pct: 0 },
    { name: 'amount', dtype: 'float64', missing_count: 0, missing_pct: 0 },
  ],
  preview: [
    { order_id: 1, region: 'North', amount: 1200 },
    { order_id: 2, region: 'South', amount: 800 },
    { order_id: 3, region: 'North', amount: 500 },
    { order_id: 4, region: 'East', amount: 2200 },
  ],
}

const ragContext = {
  query: 'test',
  retrieved_docs: [],
  dataset_summary: {
    filename: 'orders.csv',
    row_count: 4,
    column_count: 3,
    columns: datasetProfile.columns,
  },
  debug: { method: 'keyword', query_tokens: [], all_scores: {} },
}

async function mockAnalyticsApi(page: Page) {
  await page.route('**/api/datasets/upload', async route => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ dataset_id: 'dataset-1', profile: datasetProfile }),
    })
  })
  await page.route('**/api/datasets/dataset-1/rows**', async route => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ rows: datasetProfile.preview, total_rows: 4, offset: 0, limit: 50 }),
    })
  })

  await page.route('**/api/chat', async route => {
    const body = route.request().postDataJSON()
    const query = String(body?.query ?? '')

    // profile_column response
    if (query.includes('profile')) {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          query,
          planned_steps: [{ type: 'profile_column', column: 'amount' }],
          step_results: [{
            step_index: 0,
            step_type: 'profile_column',
            status: 'success',
            issues: [],
            input_row_count: 4,
            output_row_count: 8,
            input_column_count: 3,
            output_column_count: 2,
            affected_rows: 0,
            match_rate: null,
            affected_rate: null,
            preview: [
              { stat: 'column', value: 'amount' },
              { stat: 'dtype', value: 'float64' },
              { stat: 'total_rows', value: 4 },
              { stat: 'non_null_count', value: 4 },
              { stat: 'missing_pct', value: '0.0%' },
              { stat: 'unique_count', value: 4 },
              { stat: 'top_values', value: '2200(1), 1200(1)' },
              { stat: 'min', value: 500 },
              { stat: 'max', value: 2200 },
              { stat: 'mean', value: 1175 },
            ],
            message: "Profile of 'amount': float64, 0.0% missing, 4 unique values.",
          }],
          has_warnings: false,
          has_errors: false,
          rag_context: ragContext,
          explanation: null,
          execution_result: null,
          run_id: null,
          needs_clarification: false,
          state: 'preview_ready',
          route_decision: {
            route: 'deterministic_tool',
            query_type: 'profiling',
            confidence: 0.92,
            reason: 'High-confidence profiling query matched deterministic tool.',
            selected_tool: 'profile_column',
            fallback_route: 'llm_planner',
            evidence: ['amount'],
          },
        }),
      })
      return
    }

    // compare_groups response
    if (query.includes('compare') || query.includes('region')) {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          query,
          planned_steps: [{ type: 'compare_groups', group_column: 'region', value_column: 'amount', agg: 'mean' }],
          step_results: [{
            step_index: 0,
            step_type: 'compare_groups',
            status: 'success',
            issues: [],
            input_row_count: 4,
            output_row_count: 3,
            input_column_count: 3,
            output_column_count: 3,
            affected_rows: 0,
            match_rate: null,
            affected_rate: null,
            preview: [
              { region: 'East', mean: 2200, count: 1 },
              { region: 'North', mean: 850, count: 2 },
              { region: 'South', mean: 800, count: 1 },
            ],
            message: "Compared 'amount' by 'region' (mean): 3 groups.",
          }],
          has_warnings: false,
          has_errors: false,
          rag_context: ragContext,
          explanation: null,
          execution_result: null,
          run_id: null,
          needs_clarification: false,
          state: 'preview_ready',
          route_decision: {
            route: 'llm_planner',
            query_type: 'compare_groups',
            confidence: 0.85,
            reason: 'Group comparison query routed to LLM planner.',
            selected_tool: null,
            fallback_route: null,
            evidence: ['region', 'amount'],
          },
        }),
      })
      return
    }

    // ask_mode (read-only) response
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        query,
        planned_steps: [],
        step_results: [],
        has_warnings: false,
        has_errors: false,
        rag_context: ragContext,
        explanation: 'The dataset has 4 rows and 3 columns: order_id, region, amount.',
        execution_result: null,
        run_id: null,
        needs_clarification: false,
        state: 'executed',
        is_read_only: true,
        ask_mode_type: 'schema_overview',
        evidence_source: 'schema',
        route_decision: {
          route: 'ask_mode',
          query_type: 'ask',
          confidence: 0.95,
          reason: 'Schema overview query answered in Ask Mode.',
          selected_tool: null,
          fallback_route: null,
          evidence: [],
        },
      }),
    })
  })
}

// ─── tests ─────────────────────────────────────────────────────────────────────

test('mode badge shows Deterministic for profile_column query', async ({ page }) => {
  await mockAnalyticsApi(page)
  await page.goto('/')
  await uploadOrdersCsv(page)

  await page.getByPlaceholder('Ask a question about your data…').fill('profile amount column')
  await page.keyboard.press('Enter')

  await expect(page.getByText('Deterministic', { exact: true })).toBeVisible()
  await expect(page.locator('[data-testid="workflow-timeline"]').getByText('Preview')).toBeVisible()
})

test('analytics summary panel renders for profile_column result', async ({ page }) => {
  await mockAnalyticsApi(page)
  await page.goto('/')
  await uploadOrdersCsv(page)

  await page.getByPlaceholder('Ask a question about your data…').fill('profile amount column')
  await page.keyboard.press('Enter')

  await expect(page.locator('[data-testid="analytics-summary-panel"]')).toBeVisible()
  await expect(page.getByText('Column Profile · amount')).toBeVisible()
  await expect(page.locator('[data-testid="analytics-summary-panel"]').getByText('float64')).toBeVisible()
})

test('route decision debug panel is collapsed by default and expands on click', async ({ page }) => {
  await mockAnalyticsApi(page)
  await page.goto('/')
  await uploadOrdersCsv(page)

  await page.getByPlaceholder('Ask a question about your data…').fill('profile amount column')
  await page.keyboard.press('Enter')

  // Panel exists but details are collapsed
  await expect(page.getByText('Route Decision Debug')).toBeVisible()
  // Collapsed state shows summary inline
  await expect(page.getByText('deterministic_tool · profiling')).toBeVisible()

  // Expand panel
  await page.getByText('Route Decision Debug').click()
  await expect(page.getByText('High-confidence profiling query matched deterministic tool.')).toBeVisible()
})

test('ask mode badge and read-only answer shown for schema query', async ({ page }) => {
  await mockAnalyticsApi(page)
  await page.goto('/')
  await uploadOrdersCsv(page)

  await page.getByPlaceholder('Ask a question about your data…').fill('what columns are in this dataset')
  await page.keyboard.press('Enter')

  await expect(page.getByText('Ask Mode', { exact: true })).toBeVisible()
  await expect(page.getByText('read-only')).toBeVisible()
  await expect(page.locator('[data-testid="ask-mode-panel"]')).toBeVisible()
})

test('compare_groups result shows group comparison panel with bar chart', async ({ page }) => {
  await mockAnalyticsApi(page)
  await page.goto('/')
  await uploadOrdersCsv(page)

  await page.getByPlaceholder('Ask a question about your data…').fill('compare amount by region')
  await page.keyboard.press('Enter')

  await expect(page.locator('[data-testid="analytics-summary-panel"]')).toBeVisible()
  await expect(page.getByText('Group Comparison')).toBeVisible()
  await expect(page.locator('[data-testid="analytics-summary-panel"]').getByText('East')).toBeVisible()
})
