import random

EYE_COLORS = ["dark brown", "medium brown", "light brown", "hazel", "green", "blue", "gray", "amber"]
EYE_SHAPES = ["almond-shaped", "rounded", "narrow", "gently upturned", "gently downturned"]
EYELIDS = ["visible upper eyelid creases", "hooded upper eyelids", "monolid upper eyelids"]
EYE_SPACING = ["average eye spacing", "slightly wide-set eyes", "slightly close-set eyes"]


# Blindness need not have visible signs. These are fictional prompt inputs,
# never diagnoses inferred from an image or prevalence estimates.
BLINDNESS_PROBABILITY = 0.05
VISION_PROFILES = {
    "blind_no_visible_difference": "a blind person with natural-looking eyes and no visible eye difference",
    "blind_unfocused_gaze": "a blind person with natural-looking eyes and a gently unfocused gaze",
    "blind_one_opaque_eye": "a blind person with one visibly opaque eye and one natural-looking eye",
    "blind_both_opaque_eyes": "a blind person with visible opacity in both eyes",
}

def get_eyes(use_rare=False):
    vision = {"profile": "unspecified", "description": "", "eye_appearance": "natural"}
    if random.random() < BLINDNESS_PROBABILITY:
        profile = random.choice(list(VISION_PROFILES))
        vision = {"profile": profile, "description": VISION_PROFILES[profile],
                  "eye_appearance": "opaque" if "opaque" in profile else "natural"}
    return {
        "vision": vision,
        "color": random.choice(EYE_COLORS),
        "shape": random.choice(EYE_SHAPES),
        "eyelids": random.choice(EYELIDS),
        "spacing": random.choice(EYE_SPACING),
    }
