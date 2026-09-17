"""Truth table for the alert ladders.

There is no way to try these by hand: the interesting cases are sequences —
fire, stay silent, re-arm, fire again — and each depends on the state the
previous one left behind. Standard library only, same as check.py, so this
runs anywhere Python does.
"""
import unittest

from alert_levels import FALL_LEVELS, LEVELS, RISE_LEVELS, decide, normalise_state


def fresh() -> dict:
    return normalise_state(None)


def run(changes: list[float]) -> list[float | None]:
    """Feeds readings through decide() in order, carrying state, and returns
    what was announced at each step."""
    armed, fired = fresh(), []
    for change in changes:
        level, armed = decide(change, armed)
        fired.append(level)
    return fired


class Ladders(unittest.TestCase):
    def test_levels_are_the_five_asked_for(self):
        self.assertEqual(sorted(RISE_LEVELS), [5.0, 10.0])
        self.assertEqual(sorted(FALL_LEVELS), [-6.0, -4.0, -2.0])
        self.assertEqual(len(LEVELS), 5)

    def test_quiet_zone_says_nothing(self):
        self.assertEqual(run([0.0, 1.9, -1.9, 4.9, 3.0]), [None] * 5)

    def test_fall_fires_once_and_then_stays_quiet(self):
        self.assertEqual(run([-2.5, -2.6, -2.5, -2.9]), [-2.0, None, None, None])

    def test_each_deeper_level_is_its_own_event(self):
        self.assertEqual(run([-2.5, -4.5, -6.5]), [-2.0, -4.0, -6.0])

    def test_one_message_for_a_jump_past_several_levels(self):
        self.assertEqual(run([-7.0, -7.5]), [-6.0, None])

    def test_fall_rearms_only_after_retreating_past_the_nearer_point(self):
        # -2 re-arms above -1, so -1.5 is not yet enough.
        self.assertEqual(run([-2.5, -1.5, -2.5]), [-2.0, None, None])
        self.assertEqual(run([-2.5, -0.5, -2.5]), [-2.0, None, -2.0])

    def test_rise_side_still_behaves_as_before(self):
        self.assertEqual(run([6.0, 11.0]), [5.0, 10.0])
        self.assertEqual(run([11.0]), [10.0])
        self.assertEqual(run([6.0, 3.0, 6.0]), [5.0, None, 5.0])

    def test_a_fall_does_not_consume_the_rise_ladder(self):
        armed = fresh()
        _, armed = decide(-6.5, armed)
        level, _ = decide(11.0, armed)
        self.assertEqual(level, 10.0)

    def test_whipsaw_in_one_cycle_rearms_and_fires(self):
        # Fires at -4, and a single later reading back at -4.5 must fire again
        # only once the move has been above -3 in between.
        self.assertEqual(run([-4.5, -2.0, -4.5]), [-4.0, None, -4.0])


class State(unittest.TestCase):
    def test_new_levels_default_to_armed(self):
        # State written before the fall ladder existed knows only the rises.
        legacy = normalise_state({"armed": {"5.0": False, "10.0": False}})
        self.assertEqual(legacy["-2.0"], True)
        self.assertEqual(legacy["5.0"], False)
        self.assertEqual(decide(-2.5, legacy)[0], -2.0)

    def test_oldest_single_flag_format_still_loads(self):
        self.assertEqual(normalise_state({"armed": True}), {str(l): True for l in LEVELS})
        self.assertEqual(normalise_state({"armed": False}), {str(l): False for l in LEVELS})

    def test_missing_state_arms_everything(self):
        self.assertEqual(fresh(), {str(l): True for l in LEVELS})


if __name__ == "__main__":
    unittest.main()
