import random

EYE_COLORS = ["dark brown", "medium brown", "light brown", "hazel", "green", "blue", "gray", "amber"]
EYE_SHAPES = ["almond-shaped", "rounded", "narrow", "gently upturned", "gently downturned"]
EYELIDS = ["visible upper eyelid creases", "hooded upper eyelids", "monolid upper eyelids"]
EYE_SPACING = ["average eye spacing", "slightly wide-set eyes", "slightly close-set eyes"]


def get_eyes(use_rare=False):
    return {
        "color": random.choice(EYE_COLORS),
        "shape": random.choice(EYE_SHAPES),
        "eyelids": random.choice(EYELIDS),
        "spacing": random.choice(EYE_SPACING),
    }
