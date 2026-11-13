import { useEffect, useMemo, useState } from 'react'
import { getProducts, getHealth, getOrders, getAccount, API_BASE } from './api'
import ProductCard from './ProductCard'
import ChatPanel from './ChatPanel'
import CartDrawer from './CartDrawer'
import AccountDialog from './AccountDialog'

const HOME_FEATURED_NAMES = [
  'Orbit One 5G',
  'NovaBook Air 14',
  'Wave Bluetooth Speaker',
  'Pulse Active Watch',
  'KeyPro Mechanical Keyboard',
  'AsterBook Pro 15',
  'Luma Mini 5G',
  'Tempo Smart Watch',
  'Nova Chromebook 14',
  'Everyday Phone 128',
  'Arcade Mechanical Keyboard',
  'SoundBeat Wireless Headphones',
]

export default function App() {
  const [products, setProducts] = useState([])
  const [categories, setCategories] = useState([])
  const [q, setQ] = useState('')
  const [dq, setDq] = useState('')
  const [category, setCategory] = useState('')
  const [inStock, setInStock] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [online, setOnline] = useState(null)
  const [cartOpen, setCartOpen] = useState(false)
  const [cart, setCart] = useState({})
  const [known, setKnown] = useState({})
  const [pending, setPending] = useState(null)
  const [tick, setTick] = useState(0)
  const [orders, setOrders] = useState([])
  const [ordersLoading, setOrdersLoading] = useState(false)
  const [ordersError, setOrdersError] = useState('')
  const [accountOpen, setAccountOpen] = useState(false)
  const [user, setUser] = useState(null)
  const [authReady, setAuthReady] = useState(false)
  const [visibleCount, setVisibleCount] = useState(12)
  async function refreshOrders() {
    setOrdersLoading(true); setOrdersError('')
    try { setOrders(await getOrders()) }
    catch (error) { setOrdersError(error.message) }
    finally { setOrdersLoading(false) }
  }

  useEffect(() => {
    getAccount().then((account) => {
      const signedInUser = account.authenticated ? account : null
      setUser(signedInUser)
      if (signedInUser) refreshOrders()
    }).catch(() => setUser(null)).finally(() => setAuthReady(true))
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { const t = setTimeout(() => setDq(q.trim()), 300); return () => clearTimeout(t) }, [q])
  useEffect(() => { getHealth().then(() => setOnline(true)).catch(() => setOnline(false)) }, [tick])

  useEffect(() => {
    if (!authReady || !user) { setProducts([]); setLoading(false); return }
    let live = true
    setLoading(true); setError('')
    getProducts({ q: dq, category, in_stock: inStock ? true : '', limit: 500 })
      .then((data) => {
        if (!live) return
        const list = Array.isArray(data) ? data : []
        setProducts(list)
        setKnown((knownProducts) => ({ ...knownProducts, ...Object.fromEntries(list.map((product) => [product.id, product])) }))
        if (!dq && !category && !inStock) setCategories([...new Set(list.map((product) => product.category).filter(Boolean))].sort())
      })
      .catch((requestError) => live && setError(requestError.message))
      .finally(() => live && setLoading(false))
    return () => { live = false }
  }, [dq, category, inStock, tick, authReady, user])

  useEffect(() => { setVisibleCount(12) }, [dq, category, inStock])

  const add = (product) => {
    if (!product.in_stock || product.stock <= 0) return
    setKnown((knownProducts) => ({ ...knownProducts, [product.id]: product }))
    setCart((current) => ({ ...current, [product.id]: Math.min((current[product.id] || 0) + 1, product.stock, 10) }))
    setCartOpen(true)
  }
  const setQty = (id, quantity) => setCart((current) => {
    const next = { ...current }
    quantity <= 0 ? delete next[id] : (next[id] = Math.min(quantity, known[id]?.stock ?? quantity, 10))
    return next
  })
  const cartItems = useMemo(() => Object.entries(cart).filter(([id]) => known[id]).map(([id, quantity]) => ({ p: known[id], qty: quantity })), [cart, known])
  const count = cartItems.reduce((sum, item) => sum + item.qty, 0)
  const askAgent = (text) => {
    const request = typeof text === 'string' ? { message: text.trim(), visibleText: text.trim() } : text
    if (!request?.message?.trim()) return
    setPending(request)
    document.getElementById('sika-agent')?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }
  const filtered = Boolean(dq || category || inStock)
  const visibleProducts = useMemo(() => {
    if (filtered) return products.slice(0, visibleCount)
    const featuredRank = new Map(HOME_FEATURED_NAMES.map((name, index) => [name, index]))
    const ordered = [...products].sort((a, b) => (
      (featuredRank.get(a.name) ?? Number.MAX_SAFE_INTEGER)
      - (featuredRank.get(b.name) ?? Number.MAX_SAFE_INTEGER)
    ))
    return ordered.slice(0, visibleCount)
  }, [filtered, products, visibleCount])

  if (!authReady) return <div className="auth-loading"><div className="loading-mark"><img src="/shopsika-icon.svg" alt="" /></div><span>Opening Shopsika…</span></div>
  if (!user) return (
    <div className="auth-gate">
      <div className="auth-gate-glow" aria-hidden="true" />
      <AccountDialog open required onClose={() => { }} onAuthenticated={(account) => { setUser(account); refreshOrders() }} />
    </div>
  )

  return (
    <div className="app" id="top">
      <div className="aurora" aria-hidden="true" />
      <header className="top">
        <a className="logo" href="#top"><span className="logo-mark"><img src="/shopsika-icon.svg" alt="" /></span><span>Shopsika<span className="logo-ai">AI SHOPPING AGENT</span></span></a>
        <span className={`health ${online === false ? 'bad' : online ? 'good' : ''}`} title={API_BASE}>
          {online === false ? 'Backend offline' : online ? 'Catalog connected' : 'Connecting…'}
        </span>
        <nav>
          <a className="btn ghost" href="#sika-agent">Meet your agent</a>
          <button className="btn ghost account-nav" onClick={() => { setAccountOpen(true); refreshOrders() }}>{user ? 'My accounts' : 'Sign in'}</button>
          <button className="btn primary" onClick={() => setCartOpen(true)}>Cart{count > 0 && <span className="badge">{count}</span>}</button>
        </nav>
      </header>

      <main>
        <section className="hero agent-hero">
          <div className="hero-copy">
            <span className="agent-kicker"><span className="live-dot" /> YOUR PERSONAL SHOPPING AGENT</span>
            <h1>Meet <span>Shopsika.</span><br />Your next find<br />starts with a chat.</h1>
            <p>Tell Shopsika what you need, what you like, or what you want to spend. It searches this shop’s catalog, brings back real products, and helps you place an order.</p>
            <div className="agent-points"><span><i>✦</i> Finds real catalog items</span><span><i>✦</i> Helps you place an order</span></div>
            <a className="catalog-link" href="#catalog">Or browse the catalog <span>↓</span></a>
          </div>
          <div className="agent-stage" id="sika-agent">
            <div className="stage-orb" aria-hidden="true"><i /><i /><i /></div>
            <ChatPanel open inline onClose={() => { }} onAddToCart={add} onOrderPlaced={refreshOrders} cart={cart} pending={pending} clearPending={() => setPending(null)} />
          </div>
        </section>

        <section className="catalog" id="catalog">
          <div className="catalog-heading"><div><span className="agent-kicker">THE SHOP’S REAL INVENTORY</span><h2>Browse the <span>catalog</span></h2></div><p>Every item below comes from the Shopsika catalog.<br />Ask the agent to find the right one for you.</p></div>
          <div className="toolbar">
            <input className="search" type="search" value={q} onChange={(event) => setQ(event.target.value)} placeholder="Search products or brands…" aria-label="Search products" />
            <label className="toggle"><input type="checkbox" checked={inStock} onChange={(event) => setInStock(event.target.checked)} /> In stock only</label>
          </div>
          <div className="pills" role="group" aria-label="Categories">
            <button className={!category ? 'on' : ''} onClick={() => setCategory('')}>All</button>
            {categories.map((item) => <button key={item} className={category === item ? 'on' : ''} onClick={() => setCategory(item)}>{item}</button>)}
          </div>

          {loading ? (
            <div className="grid">{Array.from({ length: 6 }).map((_, index) => <div key={index} className="card skeleton" />)}</div>
          ) : error ? (
            <div className="empty"><h3>We couldn’t load the catalog</h3><p>{error}</p><button className="btn primary" onClick={() => setTick((value) => value + 1)}>Try again</button></div>
          ) : products.length === 0 ? (
            <div className="empty">
              <h3>{filtered ? 'That product isn’t in our catalog yet' : 'The shelves are empty right now'}</h3>
              <p>{filtered ? 'Shopsika only offers products currently in this shop. Try another search or ask the agent for something else.' : 'Please check back soon.'}</p>
              {filtered && <button className="btn primary" onClick={() => { setQ(''); setCategory(''); setInStock(false) }}>Show all catalog products</button>}
              {filtered && <button className="btn ghost empty-ask" onClick={() => askAgent(q || `Find products in ${category}`)}>Ask Shopsika instead</button>}
            </div>
          ) : (
            <>
              <p className="catalog-count">Showing {visibleProducts.length} of {products.length} catalog products</p>
              <div className="grid">{visibleProducts.map((product) => <ProductCard key={product.id} p={product} qty={cart[product.id] || 0} onAdd={add} onSelectInChat={(item) => askAgent({ message: `select product ${item.id}`, visibleText: `I’d like to order ${item.name}` })} />)}</div>
              {visibleProducts.length < products.length && <div className="catalog-more"><button className="btn ghost" onClick={() => setVisibleCount((count) => count + 12)}>Show more</button></div>}
            </>
          )}
        </section>
        <footer className="foot">Orders are recorded by this shop. Payment is not connected, so no payment is collected.</footer>
      </main>

      <CartDrawer open={cartOpen} onClose={() => setCartOpen(false)} items={cartItems} setQty={setQty} onClear={() => setCart({})} onOrderPlaced={refreshOrders} />
      <AccountDialog open={accountOpen} user={user} orders={orders} ordersLoading={ordersLoading} ordersError={ordersError} onRetryOrders={refreshOrders} onClose={() => setAccountOpen(false)} onAuthenticated={(account) => { setUser(account); refreshOrders() }} onSignedOut={() => { setUser(null); refreshOrders() }} />
    </div>
  )
}
