from .ages import sample_bucketed_integers


def generate_ages(n, seed=42):
    return sample_bucketed_integers(
        n,
        (.2, 18, 25),
        (.35, 26, 35),
        (.35, 36, 45),
        (.05, 46, 65),
        (.05, 66, 100),
        shuffle=True,
        seed=seed
    )
