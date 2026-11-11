import random

GENDERS = ["woman", "man"]

EXPRESSIONS = [
    "neutral",
    "soft approachable smile",
    "calm and composed",
    "friendly and professional",
    "subtle closed-mouth smile",
    "a broad relaxed smile with upper teeth visible",
    "a small asymmetric smile with relaxed brows",
    "a warm smile with gently raised cheeks",
    "a restrained smile with lips gently pressed together",
    "a thoughtful expression with relaxed lips",
    "a serious expression with softly lowered brows",
    "a mildly curious expression with slightly raised eyebrows",
    "a gently amused expression with a small smile",
    "a composed expression with lips slightly parted",
    "a quietly confident expression with relaxed jaw",
    "a slightly concerned expression with gently drawn brows",
    "a mildly surprised expression with raised brows and parted lips"
]

LENSES = ["35mm", "50mm", "85mm"]

LIGHTING_SETUPS = [
    "high-key studio lighting with soft key light",
    "high-key lighting with gentle fill, minimal shadows",
    "even studio lighting with slightly softer contrast",
    "studio lighting with subtle key-to-fill ratio variation"
]

QUALITY_PROFILES = [
    "ultra-sharp focus",
    "sharp focus with mild sensor noise",
    "sharp focus with light compression artifacts",
    "sharp focus with very subtle softness"
]

GLASSES_STYLES = ["thin metal-frame glasses", "classic rectangular glasses", "round acetate frames", "subtle rimless glasses"]

HEAD_TILT = ["perfectly level head", "slight head tilt (~2°)", "slight head tilt (~3°)", "very subtle head tilt (~1°)"]
HEAD_YAW = ["straight-on", "almost straight-on (micro yaw ~2°)", "slight yaw (~3°)"]
SHOULDERS = ["square shoulders", "slightly relaxed shoulders", "very subtle shoulder angle"]

GROOMING_STYLES = ["neat and well-groomed", "relaxed and natural", "sleek and professional", "slightly tousled for a modern look", "clean and understated"]
MAKEUP = ["natural makeup", "soft professional makeup", "no makeup"]

HATS_MEN = ["a classic fitted baseball cap", "a wool flat cap", "a minimalist beanie", "a structured fedora", "a vintage newsboy cap", "a clean-lined bucket hat"]
HATS_WOMEN = ["a wide-brim felt hat", "a chic beret", "a minimalist beanie", "a structured fedora with a slim band", "a stylish bucket hat", "a small brim cloche-inspired hat"]


def get_metadata(gender):
    lens = random.choice(["50mm", "50mm", "85mm", "35mm"])
    has_motion_hint = random.randint(1, 100) <= 2
    motion_hint = "a barely perceptible motion softness" if has_motion_hint else ""

    wears_glasses = random.randint(1, 100) <= 18
    glasses_desc = random.choice(GLASSES_STYLES) if wears_glasses else ""
    glare_desc = "with a faint lens reflection/glare" if wears_glasses and random.randint(1, 100) <= 25 else ""

    extra_headwear = ""
    if random.randint(1, 400) == 1:
        extra_headwear = random.choice(["a simple headband", "a light hood loosely framing the head", "a neat hair wrap", "a thin scarf around the head"])

    jewelry_desc = ""
    if gender == "woman" and random.randint(1, 100) <= 25:
        jewelry_desc = random.choice(["small stud earrings", "simple hoop earrings", "a delicate necklace", "minimalist earrings"])

    body_detail = ""
    if random.randint(1, 300) == 1:
        body_detail = random.choice(["a small nose stud", "a tiny eyebrow piercing", "a subtle neck tattoo barely visible"])

    has_hat = random.randint(1, 20) == 1
    hat_desc = random.choice(HATS_MEN if gender == "man" else HATS_WOMEN) if has_hat else ""

    return {
        "gender": gender,
        "expression": random.choice(EXPRESSIONS),
        "lens": lens,
        "lighting": random.choice(LIGHTING_SETUPS),
        "quality_profile": random.choice(QUALITY_PROFILES),
        "motion_hint": motion_hint,
        "head_tilt": random.choice(HEAD_TILT),
        "head_yaw": random.choice(HEAD_YAW),
        "shoulders": random.choice(SHOULDERS),
        "grooming": random.choice(GROOMING_STYLES),
        "makeup": random.choice(MAKEUP),
        "glasses": glasses_desc,
        "glare": glare_desc,
        "extra_headwear": extra_headwear,
        "jewelry": jewelry_desc,
        "body_detail": body_detail,
        "hat": hat_desc
    }
