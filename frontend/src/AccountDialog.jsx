import { useState } from 'react'
import { signIn, signOut, signUp } from './api'

export default function AccountDialog({ open, user, orders = [], ordersLoading = false, ordersError = '', onRetryOrders, onClose, onAuthenticated, onSignedOut, required = false }) {
  const [mode, setMode] = useState('signin')
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  if (!open) return null

  async function submit(event) {
    event.preventDefault()
    setError('')
    if (mode === 'signup' && password !== confirm) { setError('Those passwords do not match.'); return }
    setBusy(true)
    try {
      const result = mode === 'signup'
        ? await signUp({ name, email, password })
        : await signIn({ email, password })
      onAuthenticated(result)
      onClose()
      setPassword(''); setConfirm('')
    } catch (requestError) { setError(requestError.message) }
    finally { setBusy(false) }
  }

  async function logout() {
    setBusy(true); setError('')
    try { await signOut(); onSignedOut(); onClose() }
    catch (requestError) { setError(requestError.message) }
    finally { setBusy(false) }
  }

  return (
    <div className={`account-backdrop ${required ? 'required' : ''}`} onMouseDown={(event) => { if (!required && event.target === event.currentTarget) onClose() }}>
      <section className={`account-dialog ${user ? 'has-account' : ''}`} role="dialog" aria-modal="true" aria-labelledby="account-title">
        {!required && <button className="account-close icon-btn" onClick={onClose} aria-label="Close account window">×</button>}
        <div className="account-brand"><img src="/shopsika-icon.svg" alt="" /><span>My accounts</span></div>
        {user ? (
          <div className="account-profile">
            <span className="account-avatar">{user.name?.slice(0, 1)?.toUpperCase() || 'S'}</span>
            <h2 id="account-title">Welcome, {user.name}</h2>
            <p>Your orders are saved to your account.</p>
            <div className="account-email">{user.email}</div>
            <section className="account-orders">
              <div className="account-orders-head"><h3>My orders</h3><span>{orders.length}</span></div>
              {ordersLoading ? <p className="account-orders-empty">Loading orders…</p> : ordersError ? <div className="account-order-error"><span>{ordersError}</span><button onClick={onRetryOrders}>Retry</button></div> : orders.length === 0 ? <p className="account-orders-empty">Your placed orders will appear here.</p> : (
                <div className="account-order-list">{orders.map((order) => <article className="account-order" key={order.order_number}>
                  <div className="account-order-top"><div><b>{order.order_number}</b><small>{order.created_at ? new Date(order.created_at).toLocaleDateString() : 'Date unavailable'}</small></div><span>{order.order_status || 'confirmed'}</span></div>
                  <div className="account-order-items">{(order.items || []).map((item, index) => <div key={`${item.product_id}-${index}`}><span>{item.product_name} × {item.quantity}</span><b>{new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(item.line_total || 0)}</b></div>)}</div>
                  <div className="account-order-total"><span>Order total</span><b>{new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(order.total || 0)}</b></div>
                  <div className="account-order-address"><b>Delivery to</b><span>{order.customer_name}{order.delivery_address ? ` · ${order.delivery_address}` : ''}</span></div>
                </article>)}</div>
              )}
            </section>
            {error && <p className="account-error" role="alert">{error}</p>}
            <button className={`btn block account-signout ${busy ? 'is-signing-out' : ''}`} disabled={busy} onClick={logout}>{busy ? 'Signing out…' : 'Sign out'}</button>
          </div>
        ) : (
          <>
            <h2 id="account-title">{mode === 'signup' ? 'Create your account' : 'Welcome back'}</h2>
            <p className="account-intro">{mode === 'signup' ? 'Save your orders and pick up where you left off.' : 'Sign in to see your orders on any device.'}</p>
            <div className="account-tabs" role="tablist" aria-label="Account options">
              <button className={mode === 'signin' ? 'active' : ''} onClick={() => { setMode('signin'); setError('') }}>Sign in</button>
              <button className={mode === 'signup' ? 'active' : ''} onClick={() => { setMode('signup'); setError('') }}>Create account</button>
            </div>
            <form className="account-form" onSubmit={submit}>
              {mode === 'signup' && <label>Your name<input required minLength="2" maxLength="100" autoComplete="name" value={name} onChange={(event) => setName(event.target.value)} placeholder="Alex Morgan" /></label>}
              <label>Email address<input required type="email" maxLength="254" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@example.com" /></label>
              <label>Password<input required type="password" minLength={mode === 'signup' ? 8 : 1} maxLength="128" autoComplete={mode === 'signup' ? 'new-password' : 'current-password'} value={password} onChange={(event) => setPassword(event.target.value)} placeholder={mode === 'signup' ? 'At least 8 characters' : 'Your password'} /></label>
              {mode === 'signup' && <label>Confirm password<input required type="password" minLength="8" maxLength="128" autoComplete="new-password" value={confirm} onChange={(event) => setConfirm(event.target.value)} placeholder="Enter your password again" /></label>}
              {error && <p className="account-error" role="alert">{error}</p>}
              <button className="btn primary block account-submit" disabled={busy}>{busy ? 'Please wait…' : mode === 'signup' ? 'Create account' : 'Sign in'}</button>
            </form>
            <p className="account-privacy">Your password is protected. Orders are stored by Shopsika.</p>
          </>
        )}
      </section>
    </div>
  )
}
