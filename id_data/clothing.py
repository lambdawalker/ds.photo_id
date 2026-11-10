import random

from .clothing_colors import select_colors

# Garments are restricted to the head-and-shoulders region.
CASUAL_TOPS = [
    "cotton crew-neck T-shirt", "cotton V-neck T-shirt", "cotton henley shirt",
    "pique polo shirt", "linen band-collar shirt", "chambray button-down shirt",
    "flannel shirt", "ribbed knit top", "boat-neck jersey top", "cotton sweatshirt",
    "jersey mock-neck top", "rugby shirt", "waffle-knit shirt",
]
KNIT_TOPS = [
    "fine-knit turtleneck", "cable-knit sweater", "merino crew-neck sweater",
    "V-neck wool sweater", "ribbed mock-neck sweater", "cotton knit polo",
]
SMART_TOPS = [
    "oxford button-down shirt", "poplin shirt", "linen shirt", "silk blouse",
    "crepe blouse", "satin collared blouse", "cotton tunic with an embroidered neckline",
]
OUTER_LAYERS = [
    "open cotton cardigan", "unbuttoned denim jacket", "open corduroy overshirt",
    "unzipped bomber jacket", "open chore jacket", "open knitted vest",
    "open fleece jacket", "open quilted vest",
]
SMART_LAYERS = [
    "unbuttoned tailored blazer", "open tweed jacket", "open linen blazer",
    "unbuttoned double-breasted blazer", "open wool cardigan",
]
WORK_TOPS = ["scrub top", "work shirt with chest pockets", "chef jacket", "utility coverall collar"]
SURFACE_DETAILS = ["solid fabric", "fine vertical stripes", "small checks", "a subtle woven pattern"]
FITS = ["regular fit", "relaxed fit", "close fit"]


def get_clothing(gender=None, palette=None):
    colors = select_colors(palette)
    style = random.choice(["casual", "knitwear", "smart", "workwear"])
    tops = {"casual": CASUAL_TOPS, "knitwear": KNIT_TOPS, "smart": SMART_TOPS, "workwear": WORK_TOPS}
    outfit = random.choice(tops[style])
    fit = random.choice(FITS)
    fabric = random.choice(SURFACE_DETAILS) if style in ("casual", "smart") else "solid fabric"
    pieces = [{"role": "base", "garment": outfit, "color": colors["base"]}]

    if style in ("casual", "smart") and random.random() < 0.65:
        outer = random.choice(SMART_LAYERS if style == "smart" else OUTER_LAYERS)
        pieces.append({"role": "outer", "garment": outer, "color": colors["outer"]})

    if style in ("casual", "knitwear", "smart") and random.random() < 0.3:
        accessory = "loosely draped scarf below the chin"
        if style == "smart" and outfit.endswith("shirt"):
            accessory = random.choice(["narrow tie", accessory])
        pieces.append({"role": "accessory", "garment": accessory, "color": colors["accent"]})

    descriptions = [f"{piece['color']} {piece['garment']}" for piece in pieces]
    return {
        "outfit": outfit, "color": colors["base"], "fit": fit, "fabric": fabric,
        "condition": "clean", "intensity": "", "layer": ", ".join(descriptions[1:]),
        "style": style, "palette": colors["strategy"], "pieces": pieces,
        "description": f"{', '.join(descriptions)}, {fit}, base garment with {fabric}",
    }

