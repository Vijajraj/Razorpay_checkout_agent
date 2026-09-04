import React from 'react';
import { Library, X } from 'lucide-react';
import { ProductCard } from './ChatPanel';

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
        ) : products.map((item) => (
          <ProductCard key={item.sku} item={item} onSelectForPurchase={onSelectProduct} />
        ))}
      </div>
    </aside>
  );
}
