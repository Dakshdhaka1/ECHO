import { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { Logo } from '../layouts/AppLayout'
import { Button } from '../components/ui'
import { useAuth } from '../context/AuthContext'

function Field({ label, error, ...props }) {
  return (
    <label className="grid gap-2">
      <span className="text-sm font-medium text-ink">{label}</span>
      <input {...props} aria-invalid={!!error} className={`field h-10 ${error ? 'border-critical/60' : ''}`} />
      {error && <span className="text-xs text-critical">{error}</span>}
    </label>
  )
}

export default function AuthPage({ mode }) {
  const { login, register } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [form, setForm] = useState({ email: '', password: '', displayName: '' })
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const isRegister = mode === 'register'
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      if (isRegister) await register(form.email, form.password, form.displayName)
      else await login(form.email, form.password)
      navigate(location.state?.from || '/', { replace: true })
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mx-auto max-w-[26rem] py-6 md:py-12">
      <div className="flex justify-center animate-rise"><Logo /></div>
      <div className="window mt-8 animate-[rise_0.9s_var(--ease-fluid)_0.1s_both]">
        <div className="window-bar"><span className="flex gap-1.5" aria-hidden>{[0, 1, 2].map((i) => <span key={i} className="h-2.5 w-2.5 rounded-full bg-line-strong" />)}</span><span className="label mx-auto">{isRegister ? 'account.create' : 'session.open'}</span><span className="w-[2.6rem]" /></div>
        <div className="p-7 md:p-8">
        <h1 className="text-2xl font-light tracking-[-0.02em] text-ink">{isRegister ? 'Create your account' : 'Sign in'}</h1>
        <p className="mt-1.5 text-sm text-ink-2">{isRegister ? 'Free plan: one watchlist, alerts and 5 fresh analyses a day.' : 'Welcome back. Your watchlists are where you left them.'}</p>
        <form onSubmit={submit} className="mt-7 space-y-5" noValidate>
          {isRegister && <Field label="Name" value={form.displayName} onChange={set('displayName')} autoComplete="name" />}
          <Field label="Email" type="email" value={form.email} onChange={set('email')} autoComplete="email" required error={error?.errors?.email} />
          <Field label="Password" type="password" value={form.password} onChange={set('password')} required minLength={8}
                 autoComplete={isRegister ? 'new-password' : 'current-password'} error={error?.errors?.password} />
          {error && !error.errors && <p role="alert" className="text-sm text-critical">{error.message}</p>}
          <Button type="submit" variant="accent" disabled={busy} className="h-10 w-full">{busy ? 'Please wait...' : isRegister ? 'Create account' : 'Sign in'}</Button>
        </form>
        <p className="mt-6 text-center text-sm text-ink-2">
          {isRegister ? <>Already have an account? <Link to="/login" className="link">Sign in</Link></>
            : <>New to ECHO? <Link to="/register" className="link">Create an account</Link></>}
        </p>
      </div></div>
    </div>
  )
}
