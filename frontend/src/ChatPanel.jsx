import { useEffect, useRef, useState } from 'react'
import { sendChat, inr } from './api'
import ProductCard from './ProductCard'

const SESSION_KEY = 'shopsika.session_id'
const WELCOME = { role: 'assistant', content: "Hi, I'm Shopsika, your shopping agent. Tell me what you're looking for and I'll search the products available here." }
const SUGGESTIONS = ['Find wireless headphones under 2000', 'Find a portable speaker', 'Show me products under 1000']

function customerSafeReply(value = '') {
  return value
    .replace(/demo order/gi, 'order')
    .replace(/demo payment/gi, 'payment')
    .replace(/\bthis is a demo\b/gi, 'this is a sample')
    .replace(/\bdemo\b/gi, '')
    .replace(/[ \t]{2,}/g, ' ')
    .trim()
}

function renderInline(text) {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, index) =>
    part.startsWith('**') && part.endsWith('**')
      ? <strong key={index}>{part.slice(2, -2)}</strong>
      : part
  )
}

function MessageContent({ content = '' }) {
  const lines = content.split('\n')
  const blocks = []
  for (let index = 0; index < lines.length;) {
    if (lines[index].includes('|') && lines[index + 1]?.replace(/[|:\-\s]/g, '') === '') {
      const rows = []
      while (index < lines.length && lines[index].includes('|')) {
        const cells = lines[index].split('|').slice(1, -1).map((cell) => cell.trim())
        if (cells.some(Boolean) && !cells.every((cell) => /^:?-+:?$/.test(cell))) rows.push(cells)
        index++
      }
      if (rows.length) blocks.push(<div className="message-table-wrap" key={`table-${index}`}><table className="message-table"><thead><tr>{rows[0].map((cell, i) => <th key={i}>{renderInline(cell)}</th>)}</tr></thead><tbody>{rows.slice(1).map((row, ri) => <tr key={ri}>{row.map((cell, ci) => <td key={ci}>{renderInline(cell)}</td>)}</tr>)}</tbody></table></div>)
      continue
    }
    const paragraph = []
    while (index < lines.length && lines[index].trim() && !(lines[index].includes('|') && lines[index + 1]?.replace(/[|:\-\s]/g, '') === '')) paragraph.push(lines[index++])
    if (paragraph.length) blocks.push(<p key={`p-${index}`}>{renderInline(paragraph.join(' '))}</p>)
    else index++
  }
  return <div className="message-content">{blocks}</div>
}

export default function ChatPanel({ open, inline = false, onClose, onAddToCart, onOrderPlaced, cart, pending, clearPending }) {
  const [messages, setMessages] = useState([WELCOME])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [stage, setStage] = useState('shopping')
  const [hideProductResults, setHideProductResults] = useState(false)
  const [needsConfirm, setNeedsConfirm] = useState(false)
  const sessionRef = useRef(localStorage.getItem(SESSION_KEY) || null)
  const historyRef = useRef([])
  const chatLogRef = useRef(null)
  const handledPending = useRef(null)
  const busyRef = useRef(false)

  useEffect(() => {
    const log = chatLogRef.current
    if (log) log.scrollTo({ top: log.scrollHeight, behavior: 'smooth' })
  }, [messages, busy])

  async function send(text, { addVisibleMessage = true, visibleText } = {}) {
    const message = (text ?? input).trim()
    if (!message || busyRef.current) return
    const shownMessage = visibleText || message
    busyRef.current = true
    const history = historyRef.current.slice(-10)
    if (addVisibleMessage) {
      historyRef.current = [...historyRef.current, { role: 'user', content: shownMessage }].slice(-10)
      setMessages((items) => [...items, { role: 'user', content: shownMessage }])
    }
    setInput(''); setBusy(true)
    try {
      let response = await sendChat({ message, session_id: sessionRef.current || undefined, history })
      if (response.session_id) { sessionRef.current = response.session_id; localStorage.setItem(SESSION_KEY, response.session_id) }

      // The API requires a payment-method value for this checkout flow. Send that
      // implementation value privately and explain the real payment state plainly.
      if (response.order_stage === 'payment_selection' && !response.order_result) {
        response = await sendChat({ message: 'demo payment', session_id: sessionRef.current, history })
      }

      const completed = Boolean(response.order_result)
      if (response.order_stage !== 'shopping' || response.order_summary) setHideProductResults(true)
      else if (response.products?.length) setHideProductResults(false)
      if (completed) onOrderPlaced?.()
      setStage(completed ? 'shopping' : response.order_stage || 'shopping')
      setNeedsConfirm(!!response.requires_confirmation && !completed)
      const productSearch = /\b(find|looking for|recommend|suggest|want to buy|need a|show me|do you have|is there|available|in stock|compare|headphones?|earbuds?|keyboards?|mice|mouse|lamps?|backpacks?)\b/i.test(message)
      const reply = response.order_stage === 'shopping' && !response.order_result && !response.products?.length && productSearch
        ? "That product isn’t in this shop’s catalog right now. Try another description or ask me to find a similar item."
        : customerSafeReply(response.reply)
      historyRef.current = [...historyRef.current, { role: 'assistant', content: reply }].slice(-10)
      const needsPaymentNotice = response.order_summary && (response.order_stage === 'awaiting_confirmation' || response.requires_confirmation)
      setMessages((items) => [...items, {
        role: 'assistant',
        content: [reply, needsPaymentNotice ? 'Payment is not set up here. No payment details are needed, and no payment will be collected.' : ''].filter(Boolean).join('\n\n'),
        products: response.products || [], summary: response.order_summary,
        result: response.order_result, mode: response.mode, stage: response.order_stage,
        missing: response.missing_fields, searched: true,
      }])
      if (completed) { sessionRef.current = null; historyRef.current = []; localStorage.removeItem(SESSION_KEY) }
    } catch (error) {
      setMessages((items) => [...items, { role: 'assistant', content: customerSafeReply(error.message), error: true }])
    } finally { busyRef.current = false; setBusy(false) }
  }

  useEffect(() => {
    if (!pending) { handledPending.current = null; return }
    if (open && handledPending.current !== pending) {
      handledPending.current = pending
      send(pending.message, { visibleText: pending.visibleText })
      clearPending()
    }
  }, [pending, open]) // eslint-disable-line react-hooks/exhaustive-deps

  function reset() {
    sessionRef.current = null; localStorage.removeItem(SESSION_KEY)
    historyRef.current = []
    handledPending.current = null
    setMessages([WELCOME]); setStage('shopping'); setNeedsConfirm(false); setHideProductResults(false)
  }
  const checkingOut = stage !== 'shopping'

  return (
    <section id="sika-chat-panel" className={`chat ${inline ? 'inline' : ''} ${open ? 'open' : ''}`} aria-hidden={!open} aria-label="Shopsika AI shopping agent">
      <header className="chat-head">
        <div className="orb" aria-hidden="true"><img src="/shopsika-icon.svg" alt="" /></div>
        <div className="chat-title"><h2>Shopsika</h2><p className="agent-subtitle"><span className="chat-online-dot" /> <span>AI agent · searches this shop’s catalog</span></p></div>
        <button className="icon-btn restart-btn" onClick={reset} disabled={busy} title="Start a new chat">↻ <span>New chat</span></button>
        {!inline && <button className="icon-btn" onClick={onClose} aria-label="Close assistant">×</button>}
      </header>

      <div className="chat-log" ref={chatLogRef} role="log" aria-live="polite">
        {messages.map((message, index) => (
          <div key={index} className={`msg ${message.role} ${message.error ? 'err' : ''}`}>
            <div className="bubble"><MessageContent content={message.content} /></div>
            {message.summary && <OrderSummary summary={message.summary} />}
            {message.result && (
              <div className="order-success">
                <strong>✓ Order Placed</strong>
                {message.result.order_number && <p>Order number: <b>{message.result.order_number}</b></p>}
                <p>No payment was collected.</p>
              </div>
            )}
            {message.products?.length > 0 && message.stage === 'shopping' && !message.summary && !message.result && !checkingOut && !hideProductResults && !busy && (
              <div className="chat-products">
                {message.products.map((product) => (
                  <ProductCard key={product.id} p={product} compact qty={cart[product.id] || 0} onAdd={checkingOut || busy ? undefined : onAddToCart} onSelectInChat={checkingOut || busy ? undefined : (item) => send(`select product ${item.id}`, { visibleText: `I’d like to order ${item.name}` })} />
                ))}
              </div>
            )}
          </div>
        ))}
        {busy && <div className="msg assistant"><div className="bubble typing"><i /><i /><i /></div></div>}
      </div>

      {messages.length === 1 && (
        <div className="suggest"><span>Try asking</span>{SUGGESTIONS.map((suggestion) => <button key={suggestion} onClick={() => send(suggestion)}>{suggestion}</button>)}</div>
      )}

      {checkingOut && (
        <div className="checkout-bar">
          <span>{needsConfirm ? 'Review your order above, then confirm to place it.' : 'Order details are being collected.'}</span>
          <div className="checkout-actions">
            {needsConfirm && <button className="btn primary sm" disabled={busy} onClick={() => send('confirm')}>Confirm &amp; place order</button>}
            <button className="btn ghost sm" disabled={busy} onClick={() => send('cancel checkout')}>Cancel</button>
          </div>
        </div>
      )}

      <form className="chat-input" onSubmit={(event) => { event.preventDefault(); send() }}>
        <input value={input} onChange={(event) => setInput(event.target.value)} placeholder="Tell Shopsika what you’re looking for…" aria-label="Message Shopsika" />
        <button className="btn primary" disabled={busy || !input.trim()}>Send</button>
      </form>
      <p className="fineprint">Only products in this shop’s catalog can be ordered. No payment details are requested.</p>
    </section>
  )
}

function OrderSummary({ summary }) {
  const items = summary.items || []
  const total = summary.total ?? summary.total_amount ?? summary.grand_total
  return (
    <div className="summary">
      <h4>Review your order</h4>
      {items.map((item, index) => (
        <div key={index} className="row"><span>{item.name || item.product_name || `Product ${item.product_id}`} × {item.quantity ?? 1}</span>{(item.line_total ?? item.price) != null && <b>{inr(item.line_total ?? item.price)}</b>}</div>
      ))}
      {['customer_name', 'phone', 'delivery_address'].filter((key) => summary[key]).map((key) => (
        <div key={key} className="row sub"><span>{key.replaceAll('_', ' ')}</span><span>{summary[key]}</span></div>
      ))}
      {total != null && <div className="row total"><span>Total</span><b>{inr(total)}</b></div>}
    </div>
  )
}
