import { expect, test } from '@playwright/test'

const password = 'SupportPilotDemo!2026'

async function login(page: import('@playwright/test').Page, email: string) {
  await page.getByLabel('邮箱').fill(email)
  await page.getByLabel('密码').fill(password)
  await page.getByRole('button', { name: '进入工作台' }).click()
}

test('streams cited guidance before a confirmed ticket reaches human handling', async ({ page }) => {
  const ticketSummary = `E2E Webhook 调试请求 ${Date.now()}`
  await page.goto('/')
  await login(page, 'alpha.admin@example.com')

  await expect(page.getByText('Alpha Admin（合成用户）')).toBeVisible()
  await page.getByRole('button', { name: '开始诊断' }).click()
  await expect(page.getByRole('heading', { name: '引用证据' })).toBeVisible({ timeout: 60_000 })
  await expect(page.getByRole('list', { name: 'Agent 执行轨迹' })).toContainText('knowledge_search')

  await page.locator('textarea').first().fill(`${ticketSummary}，请创建工单并转人工。`)
  await page.getByRole('button', { name: '开始诊断' }).click()
  await expect(page.getByRole('button', { name: '确认创建工单' })).toBeVisible({ timeout: 60_000 })
  await page.getByRole('button', { name: '确认创建工单' }).click()
  await expect(page.getByText('已按确认创建工单。')).toBeVisible({ timeout: 60_000 })

  await page.getByRole('button', { name: '退出' }).click()
  await login(page, 'support.agent@example.com')
  const ticketRow = page.getByRole('button').filter({ hasText: ticketSummary })
  await expect(ticketRow).toBeVisible({ timeout: 60_000 })
  await ticketRow.click()
  await expect(page.getByRole('heading', { name: new RegExp(ticketSummary) })).toBeVisible()

  await page.getByRole('button', { name: '认领并分诊' }).click()
  await expect(page.getByText('open → triaged')).toBeVisible()
  await page.getByRole('button', { name: '转为 in_progress' }).click()
  await expect(page.getByText('triaged → in_progress')).toBeVisible()
})
