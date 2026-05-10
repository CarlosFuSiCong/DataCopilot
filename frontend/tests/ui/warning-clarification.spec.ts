import { expect, test } from '@playwright/test'
import { mockMvp3Api, uploadOrdersCsv } from './testHelpers'

test('covers warning banner and clarification panel', async ({ page }) => {
  await mockMvp3Api(page)
  await page.goto('/')
  await uploadOrdersCsv(page)

  await page.getByPlaceholder('Ask a question about your data…').fill('warning filter')
  await page.keyboard.press('Enter')
  await expect(page.getByText('Workflow has warnings — review before confirming.')).toBeVisible()

  await page.getByPlaceholder('Ask a question about your data…').fill('missing revenue')
  await page.keyboard.press('Enter')
  await expect(page.getByText("Column 'revenue' is not in this dataset. Which available column should I use instead?")).toBeVisible()
  await expect(page.getByPlaceholder('Type your answer…')).toBeVisible()
})
