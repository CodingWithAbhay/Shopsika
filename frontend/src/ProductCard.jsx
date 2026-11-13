import { useState } from 'react'
import { inr } from './api'

const HUES = { 0: 255, 1: 200, 2: 160, 3: 300, 4: 225 }

export default function ProductCard({ p, qty = 0, onAdd, onSelectInChat, compact = false }) {
  const [imageFailed, setImageFailed] = useState(false)
  const outOfStock = !p.in_stock || p.stock <= 0
  const lowStock = !outOfStock && p.stock <= 5
  const hue = HUES[p.id % 5]
  const atLimit = qty >= p.stock || qty >= 10

  return (
    <article className={`card ${outOfStock ? 'is-out' : ''} ${compact ? 'compact' : ''}`}>
      <div className={`card-media ${p.category?.toLowerCase() === 'phones' ? 'phone-media' : ''}`} style={{ '--h': hue }}>
        {p.image_url && !imageFailed && <img src={p.image_url} alt={p.name} loading="lazy" onError={() => setImageFailed(true)} />}
        <span className="chip chip-cat">{p.category}</span>
        {outOfStock ? <span className="stock out">Out of stock</span> : lowStock ? <span className="stock low">Only {p.stock} left</span> : <span className="stock ok">In stock</span>}
      </div>
      <div className="card-body">
        <p className="brand">{p.brand || 'Shopsika catalog'}</p>
        <h3>{p.name}</h3>
        <p className="product-rating" aria-label={`Rated ${Number(p.rating).toFixed(1)} out of 5 stars`}><span aria-hidden="true">★</span> {Number(p.rating).toFixed(1)} <small>/ 5</small></p>
        {!compact && <p className="desc">{p.description}</p>}
        {!compact && p.specifications && <p className="specs">{p.specifications}</p>}
        <div className="card-foot">
          <strong className="price">{inr(p.price)}</strong>
          <div className="card-actions">
            {onSelectInChat && !outOfStock && <button className="btn primary sm" onClick={() => onSelectInChat(p)}>Choose with Shopsika</button>}
            {onAdd && <button className="btn ghost sm" disabled={outOfStock || atLimit} onClick={() => onAdd(p)}>{outOfStock ? 'Unavailable' : atLimit ? 'Quantity limit' : qty ? `Add more (${qty})` : 'Add to cart'}</button>}
          </div>
        </div>
      </div>
    </article>
  )
}
