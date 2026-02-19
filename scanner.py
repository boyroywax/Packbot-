"""Card scanning and image processing utilities for Packbot."""

import base64
import io
import re
from typing import Optional

import numpy as np
from PIL import Image
import imagehash

import tcg_api


# ---------------------------------------------------------------------------
# Image helpers
# ---------------------------------------------------------------------------

def decode_base64_image(data_url: str) -> Image.Image:
    """Decode a base64 data URL (from <canvas>.toDataURL) into a PIL Image."""
    # Strip the 'data:image/...;base64,' prefix if present
    if "," in data_url:
        data_url = data_url.split(",", 1)[1]
    raw = base64.b64decode(data_url)
    return Image.open(io.BytesIO(raw)).convert("RGB")


def crop_card_region(image: Image.Image) -> Image.Image:
    """Attempt to isolate the Pokemon card from a photo.

    Uses a simple center-crop heuristic.  For production quality you'd run
    an edge / contour detector, but this keeps dependencies minimal.
    """
    w, h = image.size
    # Assume card occupies center 80% of the frame
    margin_x = int(w * 0.10)
    margin_y = int(h * 0.10)
    return image.crop((margin_x, margin_y, w - margin_x, h - margin_y))


def compute_phash(image: Image.Image) -> str:
    """Compute perceptual hash string for an image."""
    return str(imagehash.phash(image, hash_size=16))


def phash_distance(h1: str, h2: str) -> int:
    """Hamming distance between two hex perceptual hashes."""
    a = imagehash.hex_to_hash(h1)
    b = imagehash.hex_to_hash(h2)
    return a - b


# ---------------------------------------------------------------------------
# Text-based lookup helpers
# ---------------------------------------------------------------------------

_SET_NUMBER_RE = re.compile(
    r"([A-Za-z0-9\-]+)\s*[/#]\s*(\d+)",  # e.g. "SVI 001" or "base1/4"
    re.IGNORECASE,
)


def parse_set_number(text: str) -> Optional[tuple]:
    """Try to extract (set_code, card_number) from a string.

    Returns (set_code, number) tuple or None.
    """
    m = _SET_NUMBER_RE.search(text)
    if m:
        return m.group(1), m.group(2)
    return None


def lookup_by_name(pokemon_name: str) -> list:
    """Search the TCG API by Pokémon name and return card candidates."""
    return tcg_api.search_by_name(pokemon_name, page_size=12)


def lookup_by_set_number(set_code: str, number: str) -> Optional[dict]:
    """Fetch the exact card matching a set code + collector number."""
    results = tcg_api.search_cards(
        f'set.id:"{set_code}" number:"{number}"', page_size=1
    )
    cards = results.get("data", [])
    return cards[0] if cards else None


# ---------------------------------------------------------------------------
# Main scan entry points
# ---------------------------------------------------------------------------

def scan_from_image(
    data_url: str,
    pokemon_name: str = "",
    set_code: str = "",
    card_number: str = "",
) -> dict:
    """Process a captured card image and identify the card.

    Strategy:
    1. If set_code + card_number supplied  → exact lookup (highest confidence)
    2. If pokemon_name supplied            → name search
    3. Otherwise return an empty result

    Returns a dict with keys:
        card    – matched card object (or None)
        method  – identification method used
        confidence – 0.0 – 1.0 float
        candidates – list of alternative matches
    """
    result = {"card": None, "method": "none", "confidence": 0.0, "candidates": []}

    # -- Exact set/number lookup --
    if set_code and card_number:
        card = lookup_by_set_number(set_code.strip(), card_number.strip())
        if card:
            result.update({"card": card, "method": "set_number", "confidence": 1.0})
            return result

    # -- Name-based search --
    if pokemon_name.strip():
        candidates = lookup_by_name(pokemon_name.strip())
        if candidates:
            result.update(
                {
                    "card": candidates[0],
                    "method": "name_search",
                    "confidence": 0.75,
                    "candidates": candidates[1:],
                }
            )
            return result

    # -- Try to parse set/number from a combined text hint --
    combined = f"{set_code} {card_number}".strip()
    if combined:
        parsed = parse_set_number(combined)
        if parsed:
            card = lookup_by_set_number(*parsed)
            if card:
                result.update(
                    {"card": card, "method": "parsed_set_number", "confidence": 0.9}
                )
                return result

    return result


def scan_from_text(text: str) -> dict:
    """Attempt card identification from free-form text (e.g. OCR output).

    Returns same structure as scan_from_image.
    """
    result = {"card": None, "method": "none", "confidence": 0.0, "candidates": []}

    # Try set/number pattern first
    parsed = parse_set_number(text)
    if parsed:
        card = lookup_by_set_number(*parsed)
        if card:
            return {"card": card, "method": "text_set_number", "confidence": 0.9, "candidates": []}

    # Fall back to name search on first word(s)
    words = text.strip().split()
    if words:
        name_guess = " ".join(words[:2])
        candidates = lookup_by_name(name_guess)
        if candidates:
            return {
                "card": candidates[0],
                "method": "text_name_search",
                "confidence": 0.6,
                "candidates": candidates[1:],
            }

    return result
