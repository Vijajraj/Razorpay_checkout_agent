import catalog from '../src/data/catalog.json' with { type: 'json' };

const images = new Map();
const invalid = [];

for (const product of catalog) {
  if (typeof product.image !== 'string' || product.image.trim() === '') {
    invalid.push(`${product.sku} has no image`);
    continue;
  }

  const products = images.get(product.image) ?? [];
  products.push(product);
  images.set(product.image, products);
}

const duplicates = [...images.values()].filter((products) => products.length > 1);

console.log(`Catalog SKUs: ${catalog.length}`);
console.log(`Unique image URLs: ${images.size}`);

if (invalid.length > 0) {
  console.error('\nInvalid image entries:');
  invalid.forEach((message) => console.error(`- ${message}`));
}

if (duplicates.length > 0) {
  console.error(`\nDuplicate image URL groups: ${duplicates.length}`);
  duplicates.forEach((products) => {
    console.error(`- ${products.map(({ sku }) => sku).join(', ')}`);
  });
}

if (invalid.length > 0 || duplicates.length > 0) {
  process.exitCode = 1;
} else {
  console.log('\nEvery SKU has one unique image URL.');
}
