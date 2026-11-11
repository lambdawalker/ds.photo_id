import random

DESCENTS = [
    "African descent",
    "European descent",
    "Hispanic descent",
    "East Asian descent",
    "South Asian descent",
    "Southeast Asian descent",
    "Pacific Islander ancestry",
    "Middle Eastern descent",
    "Indigenous descent",
    "Mixed ancestry"
]


def get_ancestry():
    return random.choice(DESCENTS)
