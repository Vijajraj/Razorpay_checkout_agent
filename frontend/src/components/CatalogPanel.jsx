import React, { useState, useMemo } from 'react';
import { Library, ShoppingBag, X, Search, Filter } from 'lucide-react';

const PAGE_SIZE = 36;

function CatalogCard({ item, onSelectProduct }) {
  const [imageSrc, setImageSrc] = useState(item.image);

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
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span className="catalog-product-category">{item.category || 'Product'}</span>
          <span style={{ fontSize: '10px', color: 'var(--text-dim)', fontWeight: 600 }}>{item.sku}</span>
        </div>
        <h4>{item.name}</h4>
        <div className="catalog-product-meta">
          <span>₹{Number(item.price || 0).toLocaleString()}</span>
          <span>{item.stock > 0 ? `${item.stock} in stock` : 'Out of stock'}</span>
        </div>
        <button
          type="button"
          className="catalog-select-button"
          disabled={!item.stock}
          onClick={() => onSelectProduct(item, 1)}
        >
          <ShoppingBag size={14} />
          {item.stock ? 'Select product' : 'Unavailable'}
        </button>
      </div>
    </article>
  );
}

export default function CatalogPanel({ open, onClose, products, onSelectProduct }) {
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('all');
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);

  // Extract unique categories
  const categories = useMemo(() => {
    const set = new Set(products.map((p) => p.category).filter(Boolean));
    return ['all', ...Array.from(set).sort()];
  }, [products]);

  // Filter products based on search and category
  const filteredProducts = useMemo(() => {
    let list = products;
    if (selectedCategory !== 'all') {
      list = list.filter((p) => (p.category || '').toLowerCase() === selectedCategory.toLowerCase());
    }
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase().trim();
      list = list.filter((p) => {
        const name = (p.name || '').toLowerCase();
        const sku = (p.sku || '').toLowerCase();
        const cat = (p.category || '').toLowerCase();
        const tags = (p.tags || []).join(' ').toLowerCase();
        return name.includes(q) || sku.includes(q) || cat.includes(q) || tags.includes(q);
      });
    }
    return list;
  }, [products, selectedCategory, searchQuery]);

  const displayedProducts = useMemo(() => {
    return filteredProducts.slice(0, visibleCount);
  }, [filteredProducts, visibleCount]);

  const handleLoadMore = () => {
    setVisibleCount((prev) => prev + PAGE_SIZE);
  };

  return (
    <aside className={`audit-drawer catalog-drawer ${open ? 'open' : ''}`}>
      <div className="drawer-header">
        <div className="drawer-title">
          <Library size={16} color="#6366f1" />
          <span>Browse Catalog ({products.length.toLocaleString()} items)</span>
        </div>
        <button type="button" onClick={onClose} className="icon-btn" style={{ padding: '4px' }} title="Close Catalog">
          <X size={16} />
        </button>
      </div>

      <div style={{ padding: '12px 20px', borderBottom: '1px solid var(--border-subtle)', background: 'var(--bg-card)', display: 'flex', flexDirection: 'column', gap: '10px' }}>
        <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
          <Search size={15} style={{ position: 'absolute', left: '12px', color: 'var(--text-muted)' }} />
          <input
            type="text"
            placeholder="Search 10,000+ products, SKUs, categories, tags..."
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value);
              setVisibleCount(PAGE_SIZE);
            }}
            style={{
              width: '100%',
              padding: '8px 12px 8px 36px',
              borderRadius: '8px',
              border: '1px solid var(--border-subtle)',
              background: 'var(--bg-surface)',
              color: 'var(--text-main)',
              fontSize: '13px',
              outline: 'none'
            }}
          />
          {searchQuery && (
            <button
              onClick={() => {
                setSearchQuery('');
                setVisibleCount(PAGE_SIZE);
              }}
              style={{ position: 'absolute', right: '10px', background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: '14px' }}
            >
              ✕
            </button>
          )}
        </div>

        <div style={{ display: 'flex', gap: '6px', overflowX: 'auto', paddingBottom: '4px', scrollbarWidth: 'none' }}>
          {categories.map((cat) => (
            <button
              key={cat}
              onClick={() => {
                setSelectedCategory(cat);
                setVisibleCount(PAGE_SIZE);
              }}
              style={{
                padding: '4px 10px',
                borderRadius: '16px',
                fontSize: '11px',
                fontWeight: 600,
                whiteSpace: 'nowrap',
                textTransform: 'capitalize',
                border: '1px solid',
                cursor: 'pointer',
                transition: 'all 0.15s ease',
                borderColor: selectedCategory === cat ? 'var(--text-main)' : 'var(--border-subtle)',
                background: selectedCategory === cat ? 'var(--text-main)' : 'transparent',
                color: selectedCategory === cat ? 'var(--bg-primary)' : 'var(--text-muted)',
              }}
            >
              {cat}
            </button>
          ))}
        </div>
      </div>

      <div style={{ padding: '8px 24px', background: 'var(--bg-primary)', borderBottom: '1px solid var(--border-subtle)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '11.5px', color: 'var(--text-dim)' }}>
        <span>Showing <strong>{Math.min(visibleCount, filteredProducts.length).toLocaleString()}</strong> of <strong>{filteredProducts.length.toLocaleString()}</strong> products</span>
        {filteredProducts.length < products.length && (
          <button
            onClick={() => {
              setSearchQuery('');
              setSelectedCategory('all');
              setVisibleCount(PAGE_SIZE);
            }}
            style={{ background: 'none', border: 'none', color: '#6366f1', cursor: 'pointer', fontWeight: 600, fontSize: '11.5px' }}
          >
            Reset Filters
          </button>
        )}
      </div>

      <div className="drawer-feed catalog-grid">
        {displayedProducts.length === 0 ? (
          <div className="catalog-empty-state" style={{ gridColumn: '1 / -1', textAlign: 'center', padding: '40px 20px', color: 'var(--text-dim)' }}>
            No products match your search or filter.
          </div>
        ) : (
          <>
            {displayedProducts.map((item) => (
              <CatalogCard key={item.sku} item={item} onSelectProduct={onSelectProduct} />
            ))}
            {visibleCount < filteredProducts.length && (
              <div style={{ gridColumn: '1 / -1', display: 'flex', justifyContent: 'center', padding: '16px 0 24px' }}>
                <button
                  type="button"
                  onClick={handleLoadMore}
                  style={{
                    padding: '10px 28px',
                    borderRadius: '8px',
                    background: 'var(--bg-card)',
                    border: '1px solid var(--border-subtle)',
                    color: 'var(--text-main)',
                    fontSize: '13px',
                    fontWeight: 700,
                    cursor: 'pointer',
                    boxShadow: 'var(--shadow-sm)',
                    transition: 'all 0.15s ease'
                  }}
                  onMouseOver={(e) => {
                    e.currentTarget.style.borderColor = 'var(--border-strong)';
                    e.currentTarget.style.transform = 'translateY(-1px)';
                  }}
                  onMouseOut={(e) => {
                    e.currentTarget.style.borderColor = 'var(--border-subtle)';
                    e.currentTarget.style.transform = 'none';
                  }}
                >
                  Load More Products ({filteredProducts.length - visibleCount} remaining)
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </aside>
  );
}
