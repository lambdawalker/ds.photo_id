import random

from .ancestry import get_ancestry
from .clothing import get_clothing
from .eyes import get_eyes
from .diversity import settings, apply_facial_condition
from .face import get_face
from .hair import get_hair
from .metadata import get_metadata, GENDERS
from .skin import get_skin


# Describe visible build rather than inventing kilograms or BMI from a headshot.
BUILD_PROFILES = {
    "slender": "a slender build with a lean neck and lightly defined shoulder contours",
    "lean": "a lean build with a moderately slim neck and softly defined shoulders",
    "medium": "a medium build with a moderately full neck and balanced shoulder contours",
    "broad": "a broad build with a sturdy neck and broad upper shoulders",
    "full": "a full build with a softly full neck and rounded upper shoulder contours",
    "very_full": "a very full build with a thick softly contoured neck and full upper shoulders",
}

def generate_sample_data(age, diversity=None):
    diversity = settings(diversity)
    gender = random.choice(GENDERS)

    ancestry = get_ancestry()
    skin = get_skin(age, random.random() < 0.1)
    eyes = get_eyes(age=age, diversity=diversity)
    face = get_face(use_rare=random.random() < 0.25)
    hair = get_hair(gender, age)
    clothing = get_clothing(gender)
    metadata = get_metadata(gender, diversity=diversity)
    build_category = random.choice(list(BUILD_PROFILES))

    sample = {
        "build": {"category": build_category, "description": BUILD_PROFILES[build_category]},
        "age": age,
        "gender": gender,
        "ancestry": ancestry,
        "race_ethnicity": ancestry,
        "diversity_settings": diversity,
        "skin": skin,
        "eyes": eyes,
        "face": face,
        "hair": hair,
        "clothing": clothing,
        "metadata": metadata
    }
    apply_facial_condition(sample, diversity["facial_conditions"])
    return sample
