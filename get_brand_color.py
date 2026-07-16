"""Brand accent colours for styled CV generation.

Returns a bare hex string (no #). Add new brands as needed.
"""

BRAND_COLORS: dict[str, str] = {
    "anthropic":  "E8650A",
    "deloitte":   "86BC25",
    "hsbc":       "DB0011",
    "lloyds":     "006A4E",
    "barclays":   "00AEEF",
    "plexal":     "00B4A0",
}

DEFAULT_COLOR = "1A1A2E"


def get_brand_color(company_name: str) -> str:
    """Return hex accent colour (no #) matched against company name."""
    name_lower = (company_name or "").lower()
    for brand, color in BRAND_COLORS.items():
        if brand in name_lower:
            return color
    return DEFAULT_COLOR
