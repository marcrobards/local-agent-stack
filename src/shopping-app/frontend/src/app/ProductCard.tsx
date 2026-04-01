import { useState } from "react";

interface Product {
  name: string;
  price: string;
  store: string;
  image_url: string | null;
  product_url: string;
}

export function ProductCard({ product }: { product: Product }) {
  const [imgError, setImgError] = useState(false);

  const handleClick = () => {
    window.open(product.product_url, "_blank");
  };

  return (
    <div className="product-card" onClick={handleClick}>
      {product.image_url && !imgError ? (
        <img
          className="product-card-image"
          src={product.image_url}
          alt={product.name}
          onError={() => setImgError(true)}
          loading="lazy"
        />
      ) : (
        <div className="product-card-placeholder">🛍️</div>
      )}
      <div className="product-card-body">
        <div className="product-card-name">{product.name}</div>
        <div className="product-card-price">{product.price}</div>
        <div className="product-card-store">{product.store}</div>
      </div>
    </div>
  );
}
