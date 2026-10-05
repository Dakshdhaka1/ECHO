import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api, tokenStore } from '../services/api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const qc = useQueryClient()
  const [token, setToken] = useState(tokenStore.get())

  const me = useQuery({
    queryKey: ['me', token],
    queryFn: () => api.get('/auth/me'),
    enabled: !!token,
    staleTime: 30_000,
    retry: false,
  })

  const accept = useCallback((res) => {
    tokenStore.set(res.token)
    setToken(res.token)
    qc.invalidateQueries()
    return res
  }, [qc])

  const logout = useCallback(() => {
    tokenStore.set(null)
    setToken(null)
    qc.clear()
  }, [qc])

  useEffect(() => {
    const onLogout = () => setToken(null)
    window.addEventListener('echo:logout', onLogout)
    return () => window.removeEventListener('echo:logout', onLogout)
  }, [])

  const value = useMemo(() => ({
    token,
    me: me.data,
    user: me.data?.user,
    plan: me.data?.plan,
    loading: !!token && me.isLoading,
    isAdmin: me.data?.user?.role === 'ADMIN',
    login: (email, password) => api.post('/auth/login', { email, password }).then(accept),
    register: (email, password, displayName) => api.post('/auth/register', { email, password, displayName }).then(accept),
    logout,
    refresh: () => qc.invalidateQueries({ queryKey: ['me'] }),
  }), [token, me.data, me.isLoading, accept, logout, qc])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export const useAuth = () => useContext(AuthContext)
