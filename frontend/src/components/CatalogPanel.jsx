import React from 'react';
import { Library, ShoppingBag, X } from 'lucide-react';

function CatalogCard({ item, onSelectProduct }) {
  const [imageSrc, setImageSrc] = React.useState(item.image);

  return (
    <article className="catalog-product-card">
      {imageSrc ? (
        <img
          className="catalog-product-image"
          src={imageSrc}
          alt={item.name}
          referrerPolicy="no-referrer"
          onError={() => setImageSrc(null)}
        />
      ) : (
        <div className="catalog-image-fallback" aria-label={`${item.category || 'Product'} image unavailable`}>
          {item.category || 'Product'}
        </div>
      )}
      <div className="catalog-product-details">
        <span className="catalog-product-category">{item.category || 'Product'}</span>
        <h4>{item.name}</h4>
        <div className="catalog-product-meta">
          <span>₹{Number(item.price || 0).toLocaleString()}</span>
          <span>{item.stock > 0 ? `${item.stock} available` : 'Out of stock'}</span>
        </div>
        <button type="button" className="catalog-select-button" disabled={!item.stock} onClick={() => onSelectProduct(item, 1)}>
          <ShoppingBag size={14} />
          {item.stock ? 'Select product' : 'Unavailable'}
        </button>
      </div>
    </article>
  );
}

export default function CatalogPanel({ open, onClose, products, onSelectProduct }) {
  return (
    <aside className={`audit-drawer catalog-drawer ${open ? 'open' : ''}`}>
      <div className="drawer-header">
        <div className="drawer-title">
          <Library size={16} color="#6366f1" />
          <span>Browse Catalog</span>
        </div>
        <button type="button" onClick={onClose} className="icon-btn" style={{ padding: '4px' }}>
          <X size={16} />
        </button>
      </div>

      <div className="drawer-metrics catalog-metrics">
        <div className="stat-box">
          <span className="label">Products</span>
          <span className="val">{products.length}</span>
        </div>
      </div>

      <div className="drawer-feed catalog-grid">
        {products.length === 0 ? (
          <div className="catalog-empty-state">Loading catalog products…</div>
        ) : products.map((item) => <CatalogCard key={item.sku} item={item} onSelectProduct={onSelectProduct} />)}
      </div>
    </aside>
  );
}
