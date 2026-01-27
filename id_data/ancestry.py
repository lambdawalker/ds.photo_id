import random

DESCENTS = [
    "African descent",
    "European descent",
    "Hispanic descent",
    "Asian descent",
    "Middle Eastern descent",
    "Indigenous descent",
    "Mixed ancestry"
]


def get_ancestry():
    return random.choice(DESCENTS)
