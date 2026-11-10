import random

from .ancestry import get_ancestry
from .clothing import get_clothing
from .eyes import get_eyes
from .face import get_face
from .hair import get_hair
from .metadata import get_metadata, GENDERS
from .skin import get_skin


def generate_sample_data(age):
    gender = random.choice(GENDERS)

    ancestry = get_ancestry()
    skin = get_skin(age, random.random() < 0.1)
    eyes = get_eyes()
    face = get_face(use_rare=random.random() < 0.25)
    hair = get_hair(gender, age)
    clothing = get_clothing(gender)
    metadata = get_metadata(gender)

    return {
        "age": age,
        "gender": gender,
        "ancestry": ancestry,
        "skin": skin,
        "eyes": eyes,
        "face": face,
        "hair": hair,
        "clothing": clothing,
        "metadata": metadata
    }
