"""FR-15: small-sample statistics for routing evals (stdlib only)."""
import math
import random


def wilson(k, n, z=1.96):
    """95% Wilson score interval for k successes out of n."""
    if n == 0:
        return 0.0, 1.0
    p = k / n
    den = 1 + z * z / n
    mid = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, mid - half), min(1.0, mid + half)


def mcnemar(a, b):
    """Two-sided exact McNemar p-value for paired boolean outcomes a, b."""
    only_a = sum(x and not y for x, y in zip(a, b))
    only_b = sum(y and not x for x, y in zip(a, b))
    n = only_a + only_b
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(min(only_a, only_b) + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def split(items, holdout_per_team=1, seed=20261107):
    """Seeded stratified split: `holdout_per_team` random tasks per team become holdout."""
    rng = random.Random(seed)
    by_team = {}
    for i, it in enumerate(items):
        by_team.setdefault(it["team"], []).append(i)
    hold = set()
    for team in sorted(by_team):
        hold.update(rng.sample(by_team[team], min(holdout_per_team, len(by_team[team]))))
    return [dict(it, split="holdout" if i in hold else "dev") for i, it in enumerate(items)]
