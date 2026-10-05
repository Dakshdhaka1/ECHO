// Thin fetch wrapper for the ECHO backend: JWT bearer auth and RFC 7807 problem details as typed errors.
const BASE = import.meta.env.VITE_API_BASE_URL || '/api'
const TOKEN_KEY = 'echo-token'

export class ApiError extends Error {
  constructor(status, problem) {
    super(problem?.detail || problem?.title || `Request failed (${status})`)
    this.status = status
    this.type = problem?.type?.split('/').pop() || 'error'
    this.errors = problem?.errors
  }
  get isPlanLimit() { return this.type === 'plan-limit' }
}

export const tokenStore = {
  get: () => { try { return localStorage.getItem(TOKEN_KEY) } catch { return null } },
  set: (t) => { try { t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY) } catch { /* private mode */ } },
}

async function request(path, { method = 'GET', body, raw = false, withStatus = false } = {}) {
  const headers = { Accept: 'application/json' }
  const token = tokenStore.get()
  if (token) headers.Authorization = `Bearer ${token}`
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  let res
  try {
    res = await fetch(`${BASE}${path}`, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) })
  } catch {
    throw new ApiError(0, { detail: 'Cannot reach the ECHO API. Is the backend running?' })
  }
  if (res.status === 401 && token) {
    tokenStore.set(null)
    window.dispatchEvent(new Event('echo:logout'))
  }
  if (!res.ok) {
    let problem = null
    try { problem = await res.json() } catch { /* empty body */ }
    throw new ApiError(res.status, problem)
  }
  if (raw) return res
  if (res.status === 204) return null
  const data = await res.json()
  return withStatus ? { ...data, httpStatus: res.status } : data
}

export const api = {
  get: (p) => request(p),
  /** GET that also returns the HTTP status (report endpoint: 200 ready vs 202 job running). */
  getEnvelope: (p) => request(p, { withStatus: true }),
  post: (p, body = {}) => request(p, { method: 'POST', body }),
  patch: (p, body = {}) => request(p, { method: 'PATCH', body }),
  del: (p) => request(p, { method: 'DELETE' }),
  async download(path, fallbackName) {
    const res = await request(path, { raw: true })
    const disposition = res.headers.get('Content-Disposition') || ''
    const name = /filename="?([^";]+)"?/.exec(disposition)?.[1] || fallbackName
    const url = URL.createObjectURL(await res.blob())
    const a = Object.assign(document.createElement('a'), { href: url, download: name })
    document.body.appendChild(a)
    a.click()
    a.remove()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  },
}
