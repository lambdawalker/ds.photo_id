import random

EYE_COLORS = ["Dark Brown", "Hazel", "Emerald Green", "Steel Blue", "Amber", "Grey", "Deep Blue", "Light Brown", "Icy Blue", "Golden Hazel"]

EYE_SHAPES_COMMON = ["almond-shaped", "almond-shaped", "slightly hooded", "round", "deep-set", "upturned", "downturned", "wide-set", "close-set", "narrow"]
EYE_SHAPES_RARE = ["monolid", "monolid"]


def get_eyes(use_rare=False):
    color = random.choice(EYE_COLORS)
    if use_rare:
        shape = random.choice(EYE_SHAPES_RARE)
    else:
        shape = random.choice(EYE_SHAPES_COMMON)
    return {
        "color": color,
        "shape": shape
    }
