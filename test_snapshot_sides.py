"""The buy/sell split, pinned in both implementations at once.

icp_client and check.py each build a snapshot from the same two endpoints —
deliberate duplication, so the cron script needs no pip install. That
duplication is also how the taker side came to be inverted in both at once:
Coinbase reports the MAKER's side, the Binance field it replaced reported the
taker's, and the sign was carried over unchanged.

So these tests push the same tape through both classes and require them to
agree with each other and with what the tape actually means.
"""
import os
import unittest

# config refuses to import without a token, and this test never sends anything.
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "ci-not-a-real-token")

import check  # noqa: E402
from icp_client import MarketSnapshot  # noqa: E402

GECKO = {
    "internet-computer": {
        "usd": 2.5,
        "usd_24h_change": -3.0,
        "usd_market_cap": 1_000_000.0,
        "usd_24h_vol": 500_000.0,
    }
}
STATS = {"last": "2.5", "high": "3.0", "low": "2.0", "open": "2.6", "volume": "100"}

# `side` is the maker's side, so "sell" means the taker bought.
#   taker bought 10 @ 2.0 and 6 @ 3.0  -> 16 ICP, $38
#   taker sold    4 @ 2.5              ->  4 ICP, $10
TAPE = [
    {"side": "sell", "size": "10", "price": "2.0"},
    {"side": "buy", "size": "4", "price": "2.5"},
    {"side": "sell", "size": "6", "price": "3.0"},
]

BOTH = (MarketSnapshot, check.Snapshot)


class TakerSide(unittest.TestCase):
    def test_taker_buys_are_the_maker_sells(self):
        for cls in BOTH:
            with self.subTest(cls.__name__):
                s = cls(GECKO, STATS, TAPE)
                self.assertEqual(s.bought_coin, 16.0)
                self.assertEqual(s.sold_coin, 4.0)
                self.assertEqual(s.bought_usd, 38.0)
                self.assertEqual(s.sold_usd, 10.0)
                self.assertAlmostEqual(s.bought_share, 80.0)
                self.assertAlmostEqual(s.sold_share, 20.0)

    def test_a_tape_of_only_maker_buys_is_pure_selling(self):
        tape = [{"side": "buy", "size": "5", "price": "2.0"}] * 3
        for cls in BOTH:
            with self.subTest(cls.__name__):
                s = cls(GECKO, STATS, tape)
                self.assertEqual(s.bought_share, 0.0)
                self.assertEqual(s.sold_share, 100.0)
                self.assertEqual(s.sold_coin, 15.0)

    def test_both_implementations_agree(self):
        a, b = MarketSnapshot(GECKO, STATS, TAPE), check.Snapshot(GECKO, STATS, TAPE)
        for field in ("bought_coin", "sold_coin", "bought_usd", "sold_usd",
                      "bought_share", "sold_share", "trade_count"):
            self.assertEqual(getattr(a, field), getattr(b, field), field)

    def test_an_empty_tape_does_not_divide_by_zero(self):
        for cls in BOTH:
            with self.subTest(cls.__name__):
                s = cls(GECKO, STATS, [])
                self.assertEqual(s.trade_count, 0)
                self.assertEqual(s.bought_share, 0.0)
                self.assertEqual(s.sold_share, 0.0)


if __name__ == "__main__":
    unittest.main()
