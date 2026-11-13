import { useState } from 'react'
import { placeOrder, inr } from './api'

const emptyForm = { customer_name: '', phone: '', email: '', delivery_address: '' }

export default function CartDrawer({ open, onClose, items, setQty, onClear, onOrderPlaced }) {
  const [step, setStep] = useState('cart')
  const [form, setForm] = useState(emptyForm)
  const [agreed, setAgreed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)

  const subtotal = items.reduce((sum, { p, qty }) => sum + p.price * qty, 0)
  const updateField = (key) => (event) => setForm((current) => ({ ...current, [key]: event.target.value }))
  const valid = form.customer_name.trim().length > 1 && /^[+\d][\d\s()-]{6,23}$/.test(form.phone.trim()) && form.delivery_address.trim().length > 7

  async function submit() {
    setBusy(true); setError('')
    try {
      const order = await placeOrder({
        customer_name: form.customer_name.trim(), email: form.email.trim(),
        phone: form.phone.trim(), delivery_address: form.delivery_address.trim(),
        items: items.map(({ p, qty }) => ({ product_id: p.id, quantity: qty })),
        payment_method: 'demo', confirm_demo_order: true,
      })
      setResult(order); onOrderPlaced?.(); setStep('done'); onClear()
    } catch (requestError) { setError(requestError.message.replace(/\bdemo\b/gi, '').replace(/\s{2,}/g, ' ').trim()) }
    finally { setBusy(false) }
  }

  function close() {
    onClose()
    if (step === 'done') { setStep('cart'); setResult(null); setForm(emptyForm); setAgreed(false); setError('') }
  }

  return (
    <>
      <div className={`scrim ${open ? 'show' : ''}`} onClick={close} />
      <aside className={`drawer ${open ? 'open' : ''}`} aria-label="Shopping cart" aria-hidden={!open}>
        <header className="drawer-head">
          <h2>{step === 'done' ? 'Order placed' : step === 'review' ? 'Review your order' : step === 'details' ? 'Delivery details' : 'Your cart'}</h2>
          <button className="icon-btn" onClick={close} aria-label="Close cart">×</button>
        </header>

        <div className="drawer-body">
          {step === 'cart' && (items.length === 0 ? (
            <div className="empty small"><p>Your cart is empty.</p><p>Ask Shopsika to find something or browse the catalog.</p></div>
          ) : items.map(({ p, qty }) => (
            <div key={p.id} className="line">
              <div><b>{p.name}</b><small>{p.brand} · {inr(p.price)}</small></div>
              <div className="qty">
                <button onClick={() => setQty(p.id, qty - 1)} aria-label={`Decrease ${p.name} quantity`}>−</button>
                <span>{qty}</span>
                <button onClick={() => setQty(p.id, qty + 1)} disabled={qty >= p.stock || qty >= 10} aria-label={`Increase ${p.name} quantity`}>+</button>
              </div>
            </div>
          )))}

          {step === 'details' && (
            <div className="form">
              <label>Full name<input value={form.customer_name} onChange={updateField('customer_name')} autoComplete="name" /></label>
              <label>Phone<input value={form.phone} onChange={updateField('phone')} inputMode="tel" autoComplete="tel" placeholder="9000000000" /></label>
              <label>Email (optional)<input type="email" value={form.email} onChange={updateField('email')} autoComplete="email" /></label>
              <label>Delivery address<textarea rows="3" value={form.delivery_address} onChange={updateField('delivery_address')} placeholder="House, street, city, state, PIN" /></label>
              <div className="payment-note"><b>Payment is not collected here</b><p>No payment details are needed. The shop has not connected a payment service.</p></div>
            </div>
          )}

          {step === 'review' && (
            <div className="summary flat">
              {items.map(({ p, qty }) => <div key={p.id} className="row"><span>{p.name} × {qty}</span><b>{inr(p.price * qty)}</b></div>)}
              <div className="row total"><span>Estimated total</span><b>{inr(subtotal)}</b></div>
              <p className="note">The shop checks current prices and stock when you place the order.</p>
              <div className="row sub"><span>Name</span><span>{form.customer_name}</span></div>
              <div className="row sub"><span>Phone</span><span>{form.phone}</span></div>
              <div className="row sub"><span>Address</span><span>{form.delivery_address}</span></div>
              <label className="check"><input type="checkbox" checked={agreed} onChange={(event) => setAgreed(event.target.checked)} /> I understand no payment will be collected and this order will be recorded by the shop.</label>
              {error && <p className="error" role="alert">{error}</p>}
            </div>
          )}

          {step === 'done' && (
            <div className="order-done big">
              <div className="tick">✓</div>
              <h3>Order placed</h3>
              {result?.order_number && <p>Order number: <b>{result.order_number}</b></p>}
              <p><b>No payment was collected.</b> Your order has been placed with the shop.</p>
            </div>
          )}
        </div>

        <footer className="drawer-foot">
          {step === 'cart' && items.length > 0 && <>
            <div className="row total"><span>Estimated total</span><b>{inr(subtotal)}</b></div>
            <button className="btn primary block" onClick={() => setStep('details')}>Continue to delivery</button>
          </>}
          {step === 'details' && <div className="split">
            <button className="btn ghost" onClick={() => setStep('cart')}>Back</button>
            <button className="btn primary" disabled={!valid} onClick={() => setStep('review')}>Review order</button>
          </div>}
          {step === 'review' && <div className="split">
            <button className="btn ghost" disabled={busy} onClick={() => setStep('details')}>Edit</button>
            <button className="btn primary" disabled={!agreed || busy} onClick={submit}>{busy ? 'Placing order…' : 'Place order'}</button>
          </div>}
          {step === 'done' && <button className="btn primary block" onClick={close}>Continue shopping</button>}
        </footer>
      </aside>
    </>
  )
}
