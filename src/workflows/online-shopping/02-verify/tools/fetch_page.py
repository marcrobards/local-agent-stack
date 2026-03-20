"""
Page fetcher — Stage 02 (Verify)
Fetches a product URL and returns structured product data.
"""

import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


def fetch_page(url: str) -> dict:
    """
    Fetch a product page and return structured data.

    Args:
        url: The product page URL to fetch.

    Returns:
        Dict with keys: url, title, price, description, available, redirect_url, status.
        status is "LIVE" or "DEAD".
    """
    result = {
        "url": url,
        "title": None,
        "price": None,
        "description": None,
        "available": False,
        "redirect_url": None,
        "status": "DEAD",
    }

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15, allow_redirects=True)

        # Check for redirects to homepage (dead product)
        final_url = resp.url
        result["redirect_url"] = final_url if final_url != url else None

        original_domain = urlparse(url).netloc
        final_path = urlparse(final_url).path

        if resp.status_code == 404:
            return result

        if final_path in ("/", "") and urlparse(url).path not in ("/", ""):
            # Redirected to homepage — product is dead
            return result

        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        # Extract title
        title_tag = soup.find("title")
        if title_tag:
            result["title"] = title_tag.get_text(strip=True)

        # Try common meta description patterns
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc:
            result["description"] = meta_desc.get("content", "").strip()

        # Try to find price in common patterns
        for selector in [
            '[data-testid="price"]', ".price", ".product-price",
            '[itemprop="price"]', ".a-price-whole",
        ]:
            price_el = soup.select_one(selector)
            if price_el:
                result["price"] = price_el.get_text(strip=True)
                break

        # Check for out-of-stock indicators
        page_text = resp.text.lower()
        out_of_stock_signals = [
            "out of stock", "currently unavailable", "sold out",
            "no longer available", "this item is not available",
        ]
        is_unavailable = any(signal in page_text for signal in out_of_stock_signals)

        result["available"] = not is_unavailable
        result["status"] = "DEAD" if is_unavailable else "LIVE"

    except requests.RequestException:
        pass

    return result


if __name__ == "__main__":
    import json
    import sys

    url = sys.argv[1] if len(sys.argv) > 1 else "https://www.example.com"
    data = fetch_page(url)
    print(json.dumps(data, indent=2))
