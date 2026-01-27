import random

SKIN_TONES = [
    "very fair with neutral undertone",
    "fair with warm undertone",
    "light with olive undertone",
    "medium with neutral undertone",
    "medium with warm undertone",
    "tan with golden undertone",
    "deep with warm undertone",
    "deep with neutral undertone"
]

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
    "natural skin with faint sun-kissed speckling"
]


def get_skin(age, use_rare=False):
    skin_tone = random.choice(SKIN_TONES)

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
