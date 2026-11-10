import random

HAIR_COLORS = ["Jet Black", "Warm Brown", "Ash Blonde", "Honey Blonde", "Auburn", "Salt and Pepper", "Silver"]
HAIR_TEXTURES = ["straight", "wavy", "curly", "coily"]

HAIR_WOMEN = {
    "straight": ["long straight", "sleek low bun", "straight bob", "layered shoulder-length", "high ponytail"],
    "wavy": ["long wavy", "layered shoulder-length", "wavy bob", "half-up style", "loose waves"],
    "curly": ["curly shoulder-length", "curly bob", "defined curls", "curly updo", "curly ponytail"],
    "coily": ["twists", "braided", "locs", "coily afro", "protective updo"]
}

HAIR_MEN = {
    "straight": ["short cropped", "fade haircut", "side-parted", "slicked back", "buzz cut", "textured crop"],
    "wavy": ["short cropped", "fade haircut", "wavy medium length", "textured crop", "side-parted"],
    "curly": ["short cropped", "fade haircut", "curly", "curly top with fade", "textured crop"],
    "coily": ["coily", "short cropped", "fade haircut", "locs", "buzz cut"]
}

MALE_BALDNESS = [
    "a mild receding hairline",
    "thinning at the temples",
    "slight thinning at the crown",
    "moderate thinning at the crown",
    "a pronounced receding hairline",
    "a closely shaved head with visible stubble"
]
FEMALE_THINNING = [
    "subtle overall thinning",
    "mild widening of the part line",
    "slight thinning near the temples",
    "diffuse thinning at the crown",
    "fine baby hairs along the hairline"
]


def get_hair(gender, age):
    texture = random.choice(HAIR_TEXTURES)
    base_color = random.choice(HAIR_COLORS)

    gray_roll = random.randint(1, 100)
    gray_desc = ""
    if age < 35:
        if gray_roll <= 3: gray_desc = "with a few early gray strands"
    elif age < 50:
        if gray_roll <= 20: gray_desc = "with a light peppered gray"
    elif age < 65:
        if gray_roll <= 45: gray_desc = "with noticeable salt-and-pepper graying"
    else:
        if gray_roll <= 70: gray_desc = "with prominent gray/silver tones"

    if gender == "woman":
        style = random.choice(HAIR_WOMEN[texture])
    else:
        style = random.choice(HAIR_MEN[texture])

    baldness_note = ""
    if age >= 35:
        roll = random.randint(1, 100)
        if gender == "man":
            thr = 25 if age < 45 else (40 if age < 55 else (55 if age < 65 else 65))
            if roll <= thr:
                baldness_note = random.choice(MALE_BALDNESS)
                if "shaved" in baldness_note:
                    style = "bald"
                elif "crown" in baldness_note and style in ["wavy medium length", "slicked back"]:
                    style = "short cropped"
        else:
            thr = 8 if age < 45 else (15 if age < 55 else (25 if age < 65 else 35))
            if roll <= thr:
                baldness_note = random.choice(FEMALE_THINNING)

    facial_hair = ""
    if gender == "man":
        fh_roll = random.randint(1, 100)
        fh_thr = 25 if age < 25 else (35 if age < 50 else 45)
        if fh_roll <= fh_thr:
            if age < 25:
                facial_hair = random.choice(["light stubble", "short stubble"])
            elif age < 65:
                facial_hair = random.choice(["light stubble", "short boxed beard", "neatly trimmed beard", "trimmed mustache"])
            else:
                facial_hair = random.choice(["neatly trimmed beard", "short boxed beard", "trimmed mustache", "light stubble"])

            if age >= 60 and random.randint(1, 100) <= 45:
                facial_hair += " with some gray hairs"

    stray_hair = ""
    longish = style in ["long straight", "long wavy", "layered shoulder-length", "high ponytail", "loose waves", "half-up style"]
    if longish and random.randint(1, 100) <= 15:
        stray_hair = "a few loose strands partially crossing the forehead"
    elif random.randint(1, 100) <= 5:
        stray_hair = "a couple of stray hairs near the hairline"

    return {
        "color": base_color,
        "texture": texture,
        "style": style,
        "gray_desc": gray_desc,
        "baldness_note": baldness_note,
        "facial_hair": facial_hair,
        "stray_hair": stray_hair
    }
