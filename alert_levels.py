"""Alert levels in both directions, each armed independently.

One threshold answers "did something happen". Several answer "how big" — a
move through 5% is worth knowing about, a move through 10% is worth knowing
about separately, and the second must not be swallowed just because the first
already fired. Falls work the same way, on their own ladder.

Each level arms and disarms on its own, so:
  +6%  -> one message about the 5% level, 10% still armed
  +11% -> one message about the 10% level, without repeating the 5% one
  -4.5% -> one message about the -4% level, -6% still armed
  back to +3% or -1% -> that side re-arms, ready for the next move

A move that jumps straight past several levels on one side sends ONE message
naming the furthest level crossed, not three. Nobody wants a burst of
notifications about the same drop.

The two ladders never fire together: a single 24h reading cannot be both a
rise past +5% and a fall past -2%.
"""

# level -> the value the move must fall back BELOW before that level can fire
# again. The gap is what stops a price hovering at the threshold from
# notifying every cycle.
RISE_LEVELS = {5.0: 4.0, 10.0: 8.0}

# level -> the value the move must climb back ABOVE to re-arm. Falls are
# spaced two points apart rather than five, so the gap here is one point:
# wide enough that a price resting on the threshold stops ringing, narrow
# enough that a genuine second leg down still gets reported.
FALL_LEVELS = {-2.0: -1.0, -4.0: -3.0, -6.0: -5.0}

LEVELS = {**RISE_LEVELS, **FALL_LEVELS}


def normalise_state(raw) -> dict:
    """Accepts the old single-flag format {"armed": true} and the current
    per-level one, so existing state keeps working after deploy. Levels absent
    from stored state — every fall level, the first time this runs — come back
    armed, which is what a fresh level should be."""
    armed = (raw or {}).get("armed")
    if isinstance(armed, dict):
        return {str(level): bool(armed.get(str(level), True)) for level in LEVELS}
    # Old format, or nothing at all: everything armed.
    return {str(level): True if armed is None else bool(armed) for level in LEVELS}


def decide(change_percent: float, armed: dict) -> tuple[float | None, dict]:
    """Returns (level to alert about, new armed map).

    level is None when nothing should be sent — which is the normal case. A
    positive level means a rise crossed it, a negative one a fall.
    """
    new_armed = dict(armed)

    # Re-arm first: a level the move has retreated from is ready again, and
    # doing this before the firing check means a single cycle can both re-arm
    # and fire if the price whipsawed between polls.
    for level, rearm_at in LEVELS.items():
        retreated = change_percent < rearm_at if level > 0 else change_percent > rearm_at
        if retreated:
            new_armed[str(level)] = True

    risen = [lvl for lvl in RISE_LEVELS if change_percent >= lvl and new_armed.get(str(lvl), True)]
    fallen = [lvl for lvl in FALL_LEVELS if change_percent <= lvl and new_armed.get(str(lvl), True)]

    if risen:
        announced, ladder = max(risen), RISE_LEVELS
    elif fallen:
        announced, ladder = min(fallen), FALL_LEVELS
    else:
        return None, new_armed

    # Silence everything this move has already passed on the same ladder, so an
    # 11% jump does not also queue a 5% message on the next cycle. The opposite
    # ladder is left alone: it is nowhere near firing, and it re-arms above.
    for level in ladder:
        if abs(level) <= abs(announced):
            new_armed[str(level)] = False
    return announced, new_armed
