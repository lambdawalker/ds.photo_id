import random

OUTFITS_MEN_COMMON = [
    "plain crew-neck t-shirt", "v-neck t-shirt", "graphic t-shirt", "long-sleeve t-shirt", "polo shirt", "rugby shirt", "henley shirt", "casual button-down shirt", "oxford cloth button-down shirt", "flannel shirt",
    "chambray shirt", "crew-neck sweater", "v-neck sweater", "cardigan", "quarter-zip sweater", "hoodie", "zip-up hoodie", "sweatshirt", "lightweight jacket", "windbreaker", "track jacket", "denim shirt"
]

OUTFITS_MEN_RARE = [
    "turtleneck", "mock neck sweater", "shawl-collar cardigan", "cable-knit sweater", "denim jacket", "bomber jacket", "leather jacket", "suede jacket", "field jacket", "waxed jacket", "truck jacket", "overshirt jacket",
    "tailored blazer", "double-breasted blazer", "sport coat", "tailored suit jacket", "three-piece suit", "tuxedo jacket", "overcoat", "trench coat", "pea coat", "hazmat suit", "welding helmet", "welding jacket",
    "paramedic uniform", "surgeon gown", "surgical cap", "ceremonial military uniform", "judge robe", "graduation gown", "construction hi-vis vest", "construction hard hat", "work coveralls", "work cargo pants",
    "steel-toe work boots", "tool belt", "mechanic coveralls", "mechanic work shirt", "warehouse safety vest", "delivery uniform polo", "security guard uniform shirt", "security guard uniform jacket", "chef coat",
    "apron", "scrubs", "lab coat", "nurse uniform scrubs", "doctor white coat", "stethoscope", "firefighter turnout jacket", "police uniform shirt", "military camouflage uniform", "pilot uniform shirt",
    "flight attendant uniform", "construction work jacket"
]

OUTFITS_WOMEN_COMMON = [
    "plain crew-neck t-shirt", "v-neck t-shirt", "long-sleeve t-shirt", "ribbed knit top", "knit tank top", "camisole", "structured blouse", "button-down blouse", "wrap top", "peplum top", "cardigan over a camisole",
    "cardigan", "crew-neck sweater", "v-neck sweater", "hoodie", "zip-up hoodie", "sweatshirt", "denim shirt", "flannel shirt", "lightweight jacket", "windbreaker", "track jacket", "nurse scrubs", "doctor white coat",
    "lab coat", "chef coat", "apron", "construction hi-vis vest", "work coveralls", "steel-toe work boots", "warehouse safety vest", "delivery uniform polo", "security guard uniform shirt", "police uniform shirt",
    "firefighter turnout jacket", "military camouflage uniform", "pilot uniform shirt", "flight attendant uniform"
]

OUTFITS_WOMEN_RARE = [
    "silk blouse", "satin blouse", "v-neck knit top", "turtleneck", "mock neck sweater", "cashmere sweater", "shawl-collar cardigan", "denim jacket", "cropped jacket", "leather jacket", "suede jacket", "bomber jacket",
    "field jacket", "tailored blazer", "classic blazer", "double-breasted blazer", "structured coat", "trench coat", "pea coat", "hazmat suit", "paramedic uniform", "surgeon gown", "surgical mask", "judge robe",
    "ceremonial military uniform"
]

CLOTHING_CONDITIONS = ["new", "minimalist", "vintage", "retro", "classic", "modern"]
COLOR_INTENSITIES = ["dull", "faded", "rich", "vivid", "light", "intense", "muted", "satin-finish"]
CLOTHING_COLORS = ["Red", "Blue", "Yellow", "Green", "Orange", "Purple", "Pink", "Brown", "Black", "White", "Gray", "Cream", "Navy", "Burgundy", "Olive", "Teal"]
FABRIC_DETAILS = ["no pattern", "subtle texture", "subtle pattern", "fine knit texture", "micro-check pattern", "heathered fabric"]
FITS = ["tailored fit", "relaxed fit", "regular fit", "structured fit"]


def get_clothing(gender):
    rare_clothes = random.randint(1, 100) <= 25
    if gender == "man":
        outfit = random.choice(OUTFITS_MEN_RARE if rare_clothes else OUTFITS_MEN_COMMON)
    else:
        outfit = random.choice(OUTFITS_WOMEN_RARE if rare_clothes else OUTFITS_WOMEN_COMMON)

    has_layer = random.randint(1, 5) == 1
    layer = random.choice(["a light scarf", "a simple neck gaiter", "a clean-lined cardigan layer", "a subtle lapel pin", "a small collar pin"]) if has_layer else ""

    return {
        "condition": random.choice(CLOTHING_CONDITIONS),
        "outfit": outfit,
        "intensity": random.choice(COLOR_INTENSITIES),
        "color": random.choice(CLOTHING_COLORS),
        "fit": random.choice(FITS),
        "fabric": random.choice(FABRIC_DETAILS),
        "layer": layer
    }
