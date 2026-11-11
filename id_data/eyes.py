import random

from .diversity import settings

EYE_COLORS = ["dark brown", "medium brown", "light brown", "hazel", "green", "blue", "gray", "amber"]
EYE_SHAPES = ["almond-shaped", "rounded", "narrow", "gently upturned", "gently downturned"]
EYELIDS = ["visible upper eyelid creases", "hooded upper eyelids", "monolid upper eyelids"]
EYE_SPACING = ["average eye spacing", "slightly wide-set eyes", "slightly close-set eyes"]


# Blindness need not have visible signs. These are fictional prompt inputs,
# never diagnoses inferred from an image or prevalence estimates.
VISION_PROFILES = {
    "blind_no_visible_difference": "a blind person with natural-looking eyes and no visible eye difference",
    "blind_unfocused_gaze": "a blind person with natural-looking eyes and a gently unfocused gaze",
    "blind_one_opaque_eye": "a blind person with one visibly opaque eye and one natural-looking eye",
    "blind_both_opaque_eyes": "a blind person with visible opacity in both eyes",
}

def get_eyes(use_rare=False, age=40, diversity=None):
    diversity = settings(diversity)
    vision = {"profile": "unspecified", "description": "", "eye_appearance": "natural"}
    if random.random() < diversity["blindness_probability"]:
        profile = random.choice(list(VISION_PROFILES))
        vision = {"profile": profile, "description": VISION_PROFILES[profile],
                  "eye_appearance": "opaque" if "opaque" in profile else "natural"}
    band = '18_39' if age < 40 else '40_59' if age < 60 else '60_74' if age < 75 else '75_plus'
    cataracts = {'profile': 'none', 'description': '', 'age_band': band}
    if random.random() < diversity['cataracts_by_age'][band]:
        profile = random.choices(['mild', 'one_visible', 'both_visible'], weights=[.5, .3, .2])[0]
        descriptions = {
            'mild': 'a person with mild cataracts and no obvious external eye change',
            'one_visible': 'a person with an advanced cataract showing gray-white lens clouding behind one pupil while the colored iris remains visible',
            'both_visible': 'a person with advanced cataracts showing gray-white lens clouding behind both pupils while the colored irises remain visible',
        }
        cataracts.update(profile=profile, description=descriptions[profile])
        if vision['profile'] != 'unspecified':
            # Cataract appearance supplies the visual description. Do not also
            # demand natural-looking eyes or an unrelated opaque eye surface.
            vision = {'profile': 'blind_with_cataracts', 'description': 'a blind person', 'eye_appearance': 'natural'}
    return {
        "cataracts": cataracts,
        "vision": vision,
        "color": random.choice(EYE_COLORS),
        "shape": random.choice(EYE_SHAPES),
        "eyelids": random.choice(EYELIDS),
        "spacing": random.choice(EYE_SPACING),
    }
