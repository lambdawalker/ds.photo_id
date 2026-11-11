import random

# Descriptive prompt categories, sampled uniformly for coverage.
# Shape-specific jaws keep the outline internally consistent.
FACE_PROFILES = {
    "oval": ("gently rounded forehead", "balanced cheekbone width", "softly tapered jawline"),
    "round": ("rounded forehead", "full rounded cheeks", "soft rounded jawline"),
    "square": ("broad forehead", "cheekbones aligned with the jaw", "angular broad jawline"),
    "oblong": ("tall forehead", "elongated cheeks", "long gently rounded jawline"),
    "rectangular": ("broad tall forehead", "straight lateral facial contours", "long angular jawline"),
    "heart-shaped": ("broad forehead", "high cheekbones", "narrow tapered chin"),
    "diamond-shaped": ("narrow forehead", "prominent wide cheekbones", "narrow angular chin"),
    "pear-shaped": ("narrow forehead", "full lower cheeks", "broad softly rounded jawline"),
    "triangular": ("narrow forehead", "cheeks widening toward the jaw", "wide angular jawline"),
    "inverted-triangular": ("wide forehead", "cheeks tapering downward", "small pointed chin"),
}

BROW_DENSITIES = ["fine sparse", "medium-density", "thick", "bushy"]
BROW_CURVES = ["straight", "gently arched", "high-arched", "softly angled"]
LIP_SHAPES = [
    "balanced medium-full lips", "full upper and lower lips", "thin upper and lower lips",
    "thin upper lip with fuller lower lip", "full upper lip with thinner lower lip",
    "a defined cupid's bow", "a softly rounded upper lip",
]
MOUTH_WIDTHS = ["a narrow mouth", "a medium-width mouth", "a wide mouth"]
NOSE_BRIDGES = [
    "a straight narrow bridge", "a straight broad bridge", "a low bridge",
    "a high bridge", "a gently concave bridge", "a softly convex bridge",
    "a bridge with a subtle dorsal hump",
]
NOSE_TIPS = [
    "a rounded tip", "a softly squared tip", "a subtly upturned tip", "a downward-pointing tip",
    "a softly bulbous tip", "a narrow defined tip", "a broad rounded tip", "a gently projecting tip",
    "a short softly lifted tip", "a gently bifid tip",
]
NOSE_WIDTHS = ["a narrow nose base", "a medium-width nose base", "a broad nose base", "a very broad nose base"]
NOSTRILS = ["small rounded nostrils", "oval nostrils", "wide softly flared nostrils", "narrow nostrils", "slightly asymmetric nostrils"]
EAR_SIZES = ["small ears", "medium-sized ears", "large ears"]
EAR_LOBES = ["attached earlobes", "partially attached earlobes", "free earlobes"]
FACIAL_DETAILS = [
    "slight natural asymmetry between the eyebrows", "a subtle chin cleft",
    "a small cheek dimple", "a shallow chin dimple", "slightly unequal lip corners",
]


def get_face(eye_shape=None, use_rare=False):
    shape = random.choice(list(FACE_PROFILES))
    forehead, cheeks, jaw = FACE_PROFILES[shape]
    width, nostrils = random.choice(NOSE_WIDTHS), random.choice(NOSTRILS)
    return {
        "shape": shape,
        "forehead": forehead,
        "cheeks": cheeks,
        "jaw": jaw,
        "brow": f"{random.choice(BROW_DENSITIES)} {random.choice(BROW_CURVES)} brows",
        "mouth": f"{random.choice(MOUTH_WIDTHS)} with {random.choice(LIP_SHAPES)}",
        "nose": f"{random.choice(NOSE_BRIDGES)}, {random.choice(NOSE_TIPS)}, {width}, and {nostrils}",
        "nose_width": width,
        "nostrils": nostrils,
        "ear": f"{random.choice(EAR_SIZES)} with {random.choice(EAR_LOBES)}",
        "detail": random.choice(FACIAL_DETAILS) if use_rare else "",
    }
