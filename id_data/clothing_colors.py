"""Named palettes for coordinating garments in portrait prompts."""
import random

# Each row gives base, outer layer and accessory colors.
PALETTES = {
    "neutral": [
        ("ivory", "charcoal", "slate gray"),
        ("white", "navy blue", "burgundy"),
        ("oatmeal", "chocolate brown", "cream"),
        ("pale gray", "black", "silver gray"),
        ("sand", "olive green", "dark brown"),
        ("cream", "camel", "espresso brown"),
    ],
    "tonal": [
        ("powder blue", "deep navy blue", "denim blue"),
        ("pale sage", "forest green", "moss green"),
        ("blush pink", "dusty rose", "wine red"),
        ("lavender", "deep plum", "mauve"),
        ("pale peach", "terracotta", "rust orange"),
        ("light taupe", "warm brown", "dark chocolate"),
    ],
    "muted contrast": [
        ("dusty blue", "warm camel", "rust orange"),
        ("pale mint", "muted burgundy", "cream"),
        ("soft lilac", "olive green", "pale gold"),
        ("cream", "deep teal", "burnt orange"),
        ("pale yellow", "slate blue", "navy blue"),
        ("soft coral", "petrol blue", "ivory"),
    ],
    "bright accent": [
        ("white", "charcoal", "cobalt blue"),
        ("cream", "navy blue", "mustard yellow"),
        ("pale gray", "forest green", "coral red"),
        ("black", "dark plum", "turquoise"),
        ("ivory", "chocolate brown", "emerald green"),
        ("white", "denim blue", "bright red"),
    ],
}


def select_colors(strategy=None):
    """Choose a palette, returning independently addressable garment colors."""
    strategy = strategy or random.choice(list(PALETTES))
    if strategy not in PALETTES:
        raise ValueError(f"Unknown palette strategy: {strategy}")
    base, outer, accent = random.choice(PALETTES[strategy])
    return {"strategy": strategy, "base": base, "outer": outer, "accent": accent}
