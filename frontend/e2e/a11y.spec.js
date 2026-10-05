import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'

// WCAG 2.1 AA audit of the main pages in both themes. Serious and critical violations fail the build.
const AAPL = process.env.E2E_AAPL_ID || '1'
const PAGES = [['landing', '/'], ['report', `/company/${AAPL}`], ['pricing', '/pricing'], ['models', '/models'], ['login', '/login'], ['compare', '/compare']]

for (const theme of ['dark', 'light']) {
  for (const [name, path] of PAGES) {
    test(`${name} has no serious accessibility violations (${theme})`, async ({ page }) => {
      await page.addInitScript((t) => localStorage.setItem('echo-theme', t), theme)
      await page.emulateMedia({ reducedMotion: 'reduce' })  // settle animations so colours are final
      await page.goto(path)
      await page.waitForLoadState('networkidle')
      if (name === 'report') await expect(page.getByText('Executive summary')).toBeVisible({ timeout: 45_000 })
      const results = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze()
      const serious = results.violations.filter((v) => ['serious', 'critical'].includes(v.impact))
      const summary = serious.map((v) => `${v.id} (${v.nodes.length}): ${v.nodes.slice(0, 3).map((n) => n.target.join(' ')).join(' | ')}`)
      expect(summary, summary.join('\n')).toEqual([])
    })
  }
}
