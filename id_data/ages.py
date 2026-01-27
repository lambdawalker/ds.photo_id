from __future__ import annotations

import random
from typing import List, Sequence, Tuple

# (percentage, start_inclusive, end_inclusive)
Bucket = Tuple[float, int, int]


def _allocate_counts(n: int, percentages: Sequence[float], rng: random.Random) -> List[int]:
    """Largest-remainder allocation to make counts sum exactly to n."""
    raw = [p * n for p in percentages]
    base = [int(x) for x in raw]
    remainder = n - sum(base)

    fracs = [x - b for x, b in zip(raw, base)]
    idx = list(range(len(fracs)))
    rng.shuffle(idx)  # random tie-breaks
    idx.sort(key=lambda i: fracs[i], reverse=True)

    for i in idx[:remainder]:
        base[i] += 1

    return base


def sample_bucketed_integers(
        n: int,
        *buckets: Bucket,
        shuffle: bool = True,
        seed: int | None = None,
) -> List[int]:
    """
    Generate n random integers according to bucket distribution.

    Buckets are tuples: (percentage, start_inclusive, end_inclusive)

    Example:
        sample_bucketed_integers(
            1000,
            (0.10, 18, 25),  # 10% ages 18-25
            (0.20, 26, 30),  # 20% ages 26-30
            (0.70, 31, 65),  # 70% ages 31-65
            shuffle=True,
            seed=123
        )

    Returns a list of length n (shuffled if shuffle=True).
    """
    if n < 0:
        raise ValueError("n must be >= 0")
    if not buckets or n == 0:
        return []

    rng = random.Random(seed)

    # Validate buckets + collect
    percentages: List[float] = []
    ranges: List[Tuple[int, int]] = []
    for (p, a, b) in buckets:
        if p < 0:
            raise ValueError(f"Bucket percentage must be >= 0, got {p}")
        if a > b:
            raise ValueError(f"Invalid range [{a}, {b}]: start must be <= end")
        percentages.append(float(p))
        ranges.append((a, b))

    total_p = sum(percentages)
    if total_p <= 0:
        raise ValueError("Sum of bucket percentages must be > 0")

    # Normalize if they don't sum to 1 exactly
    percentages = [p / total_p for p in percentages]

    counts = _allocate_counts(n, percentages, rng)

    out: List[int] = []
    for count, (a, b) in zip(counts, ranges):
        # inclusive both ends -> randint(a, b)
        out.extend(rng.randint(a, b) for _ in range(count))

    if shuffle:
        rng.shuffle(out)

    return out


# --- quick demo ---
if __name__ == "__main__":
    nums = sample_bucketed_integers(
        30,
        (0.10, 18, 25),
        (0.20, 26, 30),
        (0.70, 31, 40),
        shuffle=False,
        seed=42,
    )
    print(nums)
