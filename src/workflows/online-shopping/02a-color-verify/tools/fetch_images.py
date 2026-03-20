"""
Image fetcher — Stage 02a (Color Verify)
Fetches product images from a URL for color assessment by the vision model.
"""

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

# Minimum image dimensions to filter out icons/thumbnails (pixels)
MIN_IMAGE_SIZE = 200


def fetch_images(url: str, max_images: int = 5) -> list[str]:
    """
    Fetch product images from a product page URL.

    The primary/hero image is returned first. Subsequent images are
    additional product photos useful for color verification when the
    primary image is ambiguous.

    Args:
        url: The product page URL.
        max_images: Maximum number of image URLs to return.

    Returns:
        List of absolute image URLs, hero image first.
    """
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except requests.RequestException:
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    images = []
    seen = set()

    # Strategy 1: Look for Open Graph image (often the hero image)
    og_image = soup.find("meta", property="og:image")
    if og_image and og_image.get("content"):
        img_url = og_image["content"]
        if img_url not in seen:
            images.append(img_url)
            seen.add(img_url)

    # Strategy 2: Look for product image containers (common patterns)
    product_selectors = [
        "img[data-testid='hero-image']",
        "img.product-image",
        "#main-image img",
        ".product-gallery img",
        "img[itemprop='image']",
        "[data-component='image'] img",
    ]
    for selector in product_selectors:
        for img in soup.select(selector):
            img_url = _resolve_img_url(img, url)
            if img_url and img_url not in seen and _is_product_image(img):
                images.append(img_url)
                seen.add(img_url)
                if len(images) >= max_images:
                    return images

    # Strategy 3: Fall back to all large images on the page
    for img in soup.find_all("img"):
        img_url = _resolve_img_url(img, url)
        if img_url and img_url not in seen and _is_product_image(img):
            images.append(img_url)
            seen.add(img_url)
            if len(images) >= max_images:
                break

    return images


def _resolve_img_url(img_tag, base_url: str) -> str | None:
    """Resolve an image tag to an absolute URL."""
    src = img_tag.get("src") or img_tag.get("data-src") or img_tag.get("data-lazy-src")
    if not src:
        return None
    if src.startswith("data:"):
        return None
    return urljoin(base_url, src)


def _is_product_image(img_tag) -> bool:
    """Heuristic check: is this likely a product image (not an icon/logo)?"""
    width = img_tag.get("width")
    height = img_tag.get("height")

    if width and height:
        try:
            if int(width) < MIN_IMAGE_SIZE or int(height) < MIN_IMAGE_SIZE:
                return False
        except ValueError:
            pass

    # Skip common non-product image patterns
    src = (img_tag.get("src") or "").lower()
    skip_patterns = ["logo", "icon", "sprite", "pixel", "tracking", "badge", "banner"]
    return not any(p in src for p in skip_patterns)


if __name__ == "__main__":
    import json
    import sys

    url = sys.argv[1] if len(sys.argv) > 1 else "https://www.example.com"
    imgs = fetch_images(url)
    print(json.dumps(imgs, indent=2))
