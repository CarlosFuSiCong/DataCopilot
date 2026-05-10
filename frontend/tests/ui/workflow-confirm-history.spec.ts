import { expect, test } from '@playwright/test'
import { mockMvp3Api, uploadOrdersCsv } from './testHelpers'

test('covers upload, workflow, RAG, confirm, history, and rerun', async ({ page }) => {
  await mockMvp3Api(page)
  await page.goto('/')

  await expect(page.getByText('Explorer')).toBeVisible()
  await expect(page.getByText('No file loaded.')).toBeVisible()
  await expect(page.getByRole('button', { name: '+ Upload CSV' })).toBeVisible()
  await expect(page.getByPlaceholder('Upload a dataset to start…')).toBeVisible()
  await expect(page.getByText('Enter to send · Shift+Enter for new line')).toBeVisible()

  await uploadOrdersCsv(page)
  await expect(page.getByText('orders.csv').first()).toBeVisible()
  await expect(page.getByText('order_id').first()).toBeVisible()

  await page.getByPlaceholder('Ask a question about your data…').fill('Filter rows where amount > 1000')
  await page.keyboard.press('Enter')

  await expect(page.getByText('filter_rows')).toBeVisible()
  await expect(page.getByText('rag · 1 doc')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Confirm' })).toBeVisible()

  await page.getByRole('button', { name: 'Confirm' }).click()
  await expect(page.getByText('One order matched the filter.')).toBeVisible()
  await expect(page.getByText('Filter rows where amount > 1000').first()).toBeVisible()
  await expect(page.getByRole('button', { name: '↓ Result CSV' })).toBeVisible()

  await page.getByTestId('run-history-run-1').click()
  await expect(page.getByText('state:')).toBeVisible()
  await expect(page.getByText('attempt 0: passed / passed → executed')).toBeVisible()

  await page.getByRole('button', { name: '▶ Rerun' }).click()
  await expect(page.getByText('Review the planned workflow above, then confirm to execute.')).toBeVisible()
})
