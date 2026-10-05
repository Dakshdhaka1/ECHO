import { request } from '@playwright/test'

// A fresh stack (CI) has an empty database: register the demo universe and generate the reports the tests
// open, so no test depends on data left behind by an earlier run. Exposes company ids via the environment.
async function waitForReport(api, path, timeoutMs = 180_000) {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    const res = await api.get(path)
    if (res.status() === 200 && (await res.json()).status === 'READY') return
    await new Promise((r) => setTimeout(r, 3000))
  }
  throw new Error(`report not ready in time: ${path}`)
}

export default async function globalSetup(config) {
  const api = await request.newContext({ baseURL: config.projects[0].use.baseURL })
  const universe = await (await api.get('/api/universe')).json()
  const id = (ticker) => universe.find((u) => u.ticker === ticker)?.companyId
  process.env.E2E_AAPL_ID = String(id('AAPL'))
  process.env.E2E_BBBY_ID = String(id('BBBY'))
  await waitForReport(api, `/api/companies/${id('AAPL')}/report`)
  await waitForReport(api, `/api/companies/${id('BBBY')}/report?asOf=2023-01-31`)
  await api.dispose()
}
