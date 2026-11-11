import random

SKIN_DEPTHS = ["very fair", "fair", "light", "medium", "tan", "brown", "deep brown", "very deep brown"]
SKIN_UNDERTONES = ["neutral", "warm", "cool", "olive", "golden"]


SKIN_TEXTURES_COMMON = [
    "smooth skin with natural pores",
    "visible pores and subtle peach fuzz",
    "soft matte skin with fine pores",
    "subtle skin texture with faint smile lines",
    "realistic skin with mild under-eye texture",
    "even skin with subtle blemish micro-texture"
]

SKIN_TEXTURES_RARE = [
    "slight freckles and natural pores",
    "natural skin with faint sun-kissed speckling",
    "freckles across the nose and upper cheeks",
    "a small flat cheek mole",
    "subtle healed acne marks on the cheeks",
    "a faint healed scar near one eyebrow",
    "patches of lighter pigmentation around the mouth"
]


# Coverage choices, not prevalence estimates; pigmentation is independent of skin tone.
BIRTHMARK_PROBABILITY = 0.15
BIRTHMARK_TYPES = {
    "light-brown patch": "a flat light-brown birthmark with gently irregular edges",
    "dark-brown patch": "a flat dark-brown birthmark with softly defined edges",
    "pink-red patch": "a flat pink-red birthmark with diffuse edges",
    "red-purple patch": "a flat red-purple birthmark with irregular edges",
}
BIRTHMARK_LOCATIONS = ["left cheek", "right cheek", "left temple", "right temple", "forehead", "side of the upper neck"]

def get_skin(age, use_rare=False):
    skin_tone = f"{random.choice(SKIN_DEPTHS)} with {random.choice(SKIN_UNDERTONES)} undertone"

    if use_rare:
        skin_texture = random.choice(SKIN_TEXTURES_RARE)
    else:
        skin_texture = random.choice(SKIN_TEXTURES_COMMON)

    if age < 35:
        aging_note = random.choice(["youthful skin elasticity", "minimal fine lines", "smooth skin with natural texture"])
    elif age < 50:
        aging_note = random.choice(["subtle fine lines near the eyes", "mild nasolabial folds", "slightly more defined smile lines"])
    elif age < 65:
        aging_note = random.choice(["visible fine lines and mild crow's feet", "moderate nasolabial folds", "subtle under-eye puffiness"])
    else:
        aging_note = random.choice(["pronounced fine lines and crow's feet", "more defined facial lines", "slight age-related skin texture changes"])

    birthmark = {"type": "none", "location": None, "size": None, "description": ""}
    if random.random() < BIRTHMARK_PROBABILITY:
        kind = random.choice(list(BIRTHMARK_TYPES))
        location = random.choice(BIRTHMARK_LOCATIONS)
        size = random.choice(["small", "medium-sized", "large"])
        birthmark = {"type": kind, "location": location, "size": size,
                     "description": f"{BIRTHMARK_TYPES[kind]} on the {location}, {size} in extent"}
    return {
        "birthmark": birthmark,
        "tone": skin_tone,
        "texture": skin_texture,
        "aging_note": aging_note
    }
