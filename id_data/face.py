import random

FACE_SHAPES_COMMON = ["oval", "oval", "oval", "round", "round", "square", "oblong"]
FACE_SHAPES_RARE = ["heart-shaped", "diamond-shaped", "pear-shaped"]

BROW_TYPES_COMMON = ["natural brows", "straight brows", "softly arched brows", "softly arched brows"]
BROW_TYPES_RARE = ["bold brows", "thin brows", "bushy brows", "high-arched brows"]

MOUTH_SHAPES_COMMON = ["balanced lips", "subtle cupid's bow", "thin upper lip with fuller lower lip", "gentle smile lines", "wide mouth", "narrow mouth"]
MOUTH_SHAPES_RARE = ["full lips", "softly downturned corners"]

NOSE_SHAPES_COMMON = ["straight bridge", "soft rounded tip", "broad base", "narrow bridge", "high bridge"]
NOSE_SHAPES_RARE = ["slightly aquiline", "subtle dorsal hump"]

EAR_SHAPES_COMMON = ["average-sized ears", "small ears", "close-set ears", "attached earlobes", "detached earlobes", "rounded helix", "angular helix"]
EAR_SHAPES_RARE = ["slightly prominent ears"]

JAW_SHAPES_COMMON = ["soft rounded jawline", "defined jawline", "tapered jaw", "rounded chin"]
JAW_SHAPES_RARE = ["square jaw", "broad jaw", "gentle V-shaped jaw", "subtle chin cleft"]


def get_face(eye_shape, use_rare=False):
    face_shape = random.choice(FACE_SHAPES_RARE if use_rare else FACE_SHAPES_COMMON)
    brow_type = random.choice(BROW_TYPES_RARE if use_rare else BROW_TYPES_COMMON)
    mouth_shape = random.choice(MOUTH_SHAPES_RARE if use_rare else MOUTH_SHAPES_COMMON)
    nose_shape = random.choice(NOSE_SHAPES_RARE if use_rare else NOSE_SHAPES_COMMON)
    ear_shape = random.choice(EAR_SHAPES_RARE if use_rare else EAR_SHAPES_COMMON)
    jaw_shape = random.choice(JAW_SHAPES_RARE if use_rare else JAW_SHAPES_COMMON)

    # Nudges
    if face_shape in ["diamond-shaped", "square", "oblong"] and random.randint(1, 3) == 1:
        jaw_shape = "defined jawline"

    if eye_shape == "monolid" and brow_type == "high-arched brows" and random.randint(1, 2) != 1:
        brow_type = "straight brows"

    return {
        "shape": face_shape,
        "brow": brow_type,
        "mouth": mouth_shape,
        "nose": nose_shape,
        "ear": ear_shape,
        "jaw": jaw_shape
    }
