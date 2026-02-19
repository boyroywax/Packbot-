"""Pokemon TCG API client for card lookup and data retrieval."""

import os
import requests
from typing import Optional


POKEMON_TCG_API_BASE = "https://api.pokemontcg.io/v2"


def _get_headers() -> dict:
    headers = {"Content-Type": "application/json"}
    api_key = os.getenv("POKEMON_TCG_API_KEY", "")
    if api_key:
        headers["X-Api-Key"] = api_key
    return headers


def search_cards(query: str, page: int = 1, page_size: int = 20) -> dict:
    """Search for cards using the Pokemon TCG API query syntax.

    Args:
        query: Pokemon TCG API query string (e.g., 'name:Charizard set.id:base1')
        page: Page number for pagination
        page_size: Number of results per page (max 250)

    Returns:
        dict with 'data' list of card objects and pagination info
    """
    params = {
        "q": query,
        "page": page,
        "pageSize": page_size,
        "select": "id,name,number,set,rarity,images,tcgplayer,cardmarket",
    }
    try:
        resp = requests.get(
            f"{POKEMON_TCG_API_BASE}/cards",
            headers=_get_headers(),
            params=params,
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        return {"error": str(e), "data": [], "totalCount": 0}


def get_card(card_id: str) -> Optional[dict]:
    """Fetch a single card by its ID.

    Args:
        card_id: Card ID in format '{set_id}-{number}' (e.g., 'base1-4')

    Returns:
        Card object dict or None if not found
    """
    try:
        resp = requests.get(
            f"{POKEMON_TCG_API_BASE}/cards/{card_id}",
            headers=_get_headers(),
            timeout=10,
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json().get("data")
    except requests.RequestException:
        return None


def get_sets(page: int = 1, page_size: int = 250) -> dict:
    """Fetch all Pokemon TCG sets.

    Returns:
        dict with 'data' list of set objects
    """
    try:
        resp = requests.get(
            f"{POKEMON_TCG_API_BASE}/sets",
            headers=_get_headers(),
            params={"page": page, "pageSize": page_size, "orderBy": "-releaseDate"},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        return {"error": str(e), "data": []}


def search_by_name(name: str, page_size: int = 10) -> list:
    """Convenience wrapper to search cards by Pokémon name.

    Args:
        name: Pokémon name (partial matches supported)

    Returns:
        List of matching card objects
    """
    result = search_cards(f'name:"{name}"', page_size=page_size)
    return result.get("data", [])


def get_card_price(card_id: str) -> Optional[dict]:
    """Get market price data for a card.

    Returns a simplified price dict with keys: market, low, mid, high (USD).
    """
    card = get_card(card_id)
    if not card:
        return None

    prices = {}

    # TCGPlayer prices
    tcgplayer = card.get("tcgplayer", {})
    if tcgplayer:
        for condition, price_data in tcgplayer.get("prices", {}).items():
            prices[condition] = {
                "source": "tcgplayer",
                "low": price_data.get("low"),
                "mid": price_data.get("mid"),
                "high": price_data.get("high"),
                "market": price_data.get("market"),
                "url": tcgplayer.get("url"),
            }

    # Cardmarket prices (EU)
    cardmarket = card.get("cardmarket", {})
    if cardmarket:
        cm_prices = cardmarket.get("prices", {})
        prices["cardmarket"] = {
            "source": "cardmarket",
            "low": cm_prices.get("lowPrice"),
            "average": cm_prices.get("averageSellPrice"),
            "trend": cm_prices.get("trendPrice"),
            "url": cardmarket.get("url"),
        }

    return prices if prices else None
