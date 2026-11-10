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

    return {
        "tone": skin_tone,
        "texture": skin_texture,
        "aging_note": aging_note
    }
