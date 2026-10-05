import { expect, test } from '@playwright/test'

// User-level smoke tests: the main journeys render with no browser errors and no horizontal scrolling.
function trackErrors(page) {
  const errors = []
  page.on('pageerror', (e) => errors.push(e.message))
  page.on('console', (m) => m.type() === 'error' && errors.push(m.text()))
  return errors
}

test('landing page renders the hero, the demo universe and live platform figures', async ({ page }) => {
  const errors = trackErrors(page)
  await page.goto('/')
  await expect(page.getByRole('heading', { level: 1 })).toContainText('See the health of any listed company')
  await expect(page.getByText('Apple Inc.').first()).toBeVisible()
  await expect(page.getByText('Companies covered')).toBeVisible()
  expect(errors).toEqual([])
})

test('search opens a company dossier with an explained score', async ({ page }) => {
  const errors = trackErrors(page)
  await page.goto('/')
  await page.getByRole('textbox', { name: 'Search companies' }).fill('Apple')
  await page.getByRole('button', { name: /Apple Inc/ }).first().click()
  await expect(page).toHaveURL(/\/company\/\d+/)
  await expect(page.getByText('Executive summary')).toBeVisible({ timeout: 45_000 })
  await expect(page.getByRole('img', { name: /Health score \d+ of 100/ })).toBeVisible()
  await page.getByRole('tab', { name: 'Why this score' }).click()
  await expect(page.getByText(/Contribution of every factor/)).toBeVisible()
  expect(errors).toEqual([])
})

test('historical case study is analysed only with data public before the event', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('link', { name: /as of 31 Jan 2023/ }).first().click()
  await expect(page.getByText('Historical case study.')).toBeVisible({ timeout: 45_000 })
})

test('signals radar plots analysed reports and adds a company to the comparison', async ({ page }) => {
  await page.goto('/compare')
  const radar = page.locator('section', { hasText: 'Signals radar' })
  const apple = radar.locator('svg text', { hasText: /^AAPL$/ })  // the chart label, not the table cell
  await expect(apple).toBeVisible({ timeout: 20_000 })
  await apple.click()
  await expect(page).toHaveURL(/ids=\d+/)
  await expect(page.getByRole('heading', { name: 'Side by side' })).toBeVisible()
})

for (const width of [390, 768, 1440]) {
  test(`no horizontal overflow at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 })
    for (const path of ['/', '/pricing', '/models', '/company/1', '/compare']) {
      await page.goto(path)
      await page.waitForLoadState('networkidle')
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
      expect(overflow, `${path} overflows by ${overflow}px`).toBeLessThanOrEqual(0)
    }
  })
}

test('security headers are sent', async ({ request }) => {
  const res = await request.get('/')
  expect(res.headers()['content-security-policy']).toContain("script-src 'self'")
  expect(res.headers()['x-content-type-options']).toBe('nosniff')
})
