def format_price_range(price_min: int | None, price_max: int | None) -> str:
    if price_min is not None and price_max is not None:
        return f"¥{price_min:,} – ¥{price_max:,}"
    if price_min is not None:
        return f"from ¥{price_min:,}"
    if price_max is not None:
        return f"up to ¥{price_max:,}"
    return "any price"


def normalize_price(value: int) -> int | None:
    return value if value > 0 else None


def preset_to_price(value: int) -> int | None:
    """Map inline preset callback value to stored price. 0 = custom input requested."""
    if value == 0:
        return None
    if value < 0:
        return None
    return value
