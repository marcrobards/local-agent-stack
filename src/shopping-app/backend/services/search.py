import json
import logging
import os
import re

from anthropic import AsyncAnthropic
from browser_use_sdk.v3 import AsyncBrowserUse

logger = logging.getLogger(__name__)

anthropic_client = AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
browser_client = AsyncBrowserUse()


async def execute_search(spec: dict, messages: list[dict]) -> list[dict]:
    """Execute product search using Browser Use Cloud. Returns list of product dicts."""

    site_prompt = f"""Given this shopping search specification:
{json.dumps(spec, indent=2)}

Suggest 2-4 retail websites that would be the best places to search for this item. Consider the item type, price range, and style.

Return ONLY a JSON array of objects with "site_name" and "search_url" keys. The search_url should be the search results page URL with an appropriate query.

Example: [{{"site_name": "Etsy", "search_url": "https://www.etsy.com/search?q=blue+linen+tote+bag"}}]"""

    site_response = await anthropic_client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        messages=[{"role": "user", "content": site_prompt}],
    )

    sites_text = site_response.content[0].text
    logger.info("Site selection response: %s", sites_text[:300])
    json_match = re.search(r"\[.*\]", sites_text, re.DOTALL)
    sites = json.loads(json_match.group(0)) if json_match else []
    logger.info("Will search %d sites: %s", len(sites), [s.get("site_name") for s in sites])

    all_products = []

    for site in sites[:4]:
        task = f"""Go to {site['search_url']} and find products matching this description:
- Item: {spec.get('item_description', '')}
- Color: {spec.get('color', 'any')}
- Max price: {spec.get('price_max', 'no limit')}
- Notes: {spec.get('notes', '')}

Extract up to 5 products. For each product, extract:
1. name: the product name
2. price: the price as displayed (e.g. "$34.00")
3. store: "{site['site_name']}"
4. product_url: the direct URL to the product page (NOT the search results page)
5. image_url: the product image URL (if visible)

Return the results as a JSON array. Example:
[{{"name": "Blue Linen Tote", "price": "$34.00", "store": "{site['site_name']}", "product_url": "https://...", "image_url": "https://..."}}]

If you can't find matching products, return an empty array: []"""

        try:
            logger.info("Searching %s: %s", site["site_name"], site["search_url"])
            result = await browser_client.run(task)
            logger.info("Browser Use result for %s: %s", site["site_name"], str(result.output)[:300] if result.output else "None")
            if result.output:
                output_match = re.search(r"\[.*\]", result.output, re.DOTALL)
                if output_match:
                    products = json.loads(output_match.group(0))
                    logger.info("Found %d products from %s", len(products), site["site_name"])
                    all_products.extend(products)
        except Exception as e:
            logger.error("Error searching %s: %s", site["site_name"], e, exc_info=True)
            continue

    return all_products
