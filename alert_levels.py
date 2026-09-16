"""Two-tier rise alerts with independent arming.

One threshold answers "did something happen". Two answer "how big" — a move
through 5% is worth knowing about, a move through 10% is worth knowing about
separately, and the second must not be swallowed just because the first
already fired.

Each level arms and disarms on its own, so:
  +6%  -> one message about the 5% level, 10% still armed
  +11% -> one message about the 10% level, without repeating the 5% one
  back to +3% -> both re-arm, ready for the next move

A move that jumps straight past both levels sends ONE message naming the
highest level crossed, not two. Nobody wants two notifications about the
same jump.
"""

# level -> the value it must fall back below before it can fire again. The gap
# is what stops a price hovering at the threshold from notifying every cycle.
LEVELS = {5.0: 4.0, 10.0: 8.0}


def normalise_state(raw) -> dict:
    """Accepts the old single-flag format {"armed": true} and the current
    per-level one, so an existing state.json keeps working after deploy."""
    armed = (raw or {}).get("armed")
    if isinstance(armed, dict):
        return {str(level): bool(armed.get(str(level), True)) for level in LEVELS}
    # Old format, or nothing at all: everything armed.
    return {str(level): True if armed is None else bool(armed) for level in LEVELS}


def decide(change_percent: float, armed: dict) -> tuple[float | None, dict]:
    """Returns (level to alert about, new armed map).

    level is None when nothing should be sent — which is the normal case.
    """
    new_armed = dict(armed)

    # Re-arm first: a level that the move has fallen back below is ready again,
    # and doing this before the firing check means a single cycle can both
    # re-arm and fire if the price whipsawed between polls.
    for level, rearm_at in LEVELS.items():
        if change_percent < rearm_at:
            new_armed[str(level)] = True

    crossed = [lvl for lvl in LEVELS if change_percent >= lvl and new_armed.get(str(lvl), True)]
    if not crossed:
        return None, new_armed

    highest = max(crossed)
    # Disarm everything at or below what we are announcing, so a 11% jump does
    # not also queue a 5% message on the next cycle.
    for level in LEVELS:
        if level <= highest:
            new_armed[str(level)] = False
    return highest, new_armed
