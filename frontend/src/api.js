// The API base is configurable; no secrets (e.g. the Groq key) ever live in the frontend.
const localApiHost = typeof window === 'undefined' ? '127.0.0.1' : window.location.hostname
export const API_BASE = (import.meta.env.VITE_API_BASE_URL || `http://${localApiHost}:8000`).replace(/\/$/, '')

async function request(path, options = {}) {
  let res
  try {
    res = await fetch(`${API_BASE}${path}`, {
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      ...options,
    })
  } catch {
    throw new Error(`Can't reach the Shopsika server at ${API_BASE}. Check that the backend is running.`)
  }
  const data = await res.json().catch(() => null)
  if (!res.ok) {
    const d = data?.detail
    const msg = typeof d === 'string' ? d : Array.isArray(d) ? d.map((e) => e.msg).join('; ') : null
    throw new Error(msg || `Request failed (${res.status})`)
  }
  return data
}

export const getHealth = () => request('/api/health')
export const getProducts = (p = {}) => {
  const qs = new URLSearchParams()
  Object.entries(p).forEach(([k, v]) => v !== '' && v != null && qs.set(k, v))
  return request(`/api/products?${qs}`)
}
export const sendChat = (body) => request('/api/chat', { method: 'POST', body: JSON.stringify(body) })
export const placeOrder = (body) => request('/api/orders', { method: 'POST', body: JSON.stringify(body) })
export const getOrder = (n) => request(`/api/orders/${encodeURIComponent(n)}`)
export const getOrders = () => request('/api/orders')
export const getAccount = () => request('/api/auth/me')
export const signUp = (body) => request('/api/auth/signup', { method: 'POST', body: JSON.stringify(body) })
export const signIn = (body) => request('/api/auth/signin', { method: 'POST', body: JSON.stringify(body) })
export const signOut = () => request('/api/auth/signout', { method: 'POST' })

export const inr = (n) =>
  new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(Number(n) || 0)
