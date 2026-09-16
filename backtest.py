"""Historical backtest of a few mechanical rules on ICP, with a robustness check.

Read the robustness section of the output before the returns. A backtest on one
asset, over one stretch of history, with a handful of rules is the easiest way
to fool yourself: try enough variations and the best of them always looks
convincing, because picking the maximum of many noisy outcomes is itself a way
of manufacturing a good number.

So this does not report "the winning strategy". For each family of rules it
sweeps a grid of parameters and reports the whole distribution - median, best,
worst, and how often the family beats simply holding. A rule that only works at
one exact parameter setting is a coincidence, and that shows up here as a wide
spread and a low win rate against buy-and-hold.

Costs are charged on every entry and exit, because ignoring them is what makes
frequent trading look profitable on paper.

It describes what already happened, which is a different thing from what will.
"""
import json
import statistics
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

COINBASE = "https://api.exchange.coinbase.com"
PRODUCT = "ICP-USD"
GRANULARITY = 86400  # daily candles
MAX_PER_REQUEST = 300  # Coinbase's hard cap per call
HEADERS = {"Accept": "application/json", "User-Agent": "icp-watcher-backtest/1.0"}
TIMEOUT = 30

# Cost charged on every entry and every exit, as a fraction. Coinbase retail
# taker fees sit near 0.6%, so 0.5% including slippage is the optimistic end.
# Any result below is therefore a best case, not a promise.
FEE_PER_SIDE = 0.005


def _get(url, params):
    req = urllib.request.Request(f"{url}?{urllib.parse.urlencode(params)}", headers=HEADERS)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_history(max_days=1500):
    """Daily candles, oldest first. Paged backwards because Coinbase returns at
    most 300 per call."""
    end = datetime.now(timezone.utc)
    rows = {}

    while len(rows) < max_days:
        start = end - timedelta(days=MAX_PER_REQUEST)
        batch = _get(
            f"{COINBASE}/products/{PRODUCT}/candles",
            {"granularity": GRANULARITY, "start": start.isoformat(), "end": end.isoformat()},
        )
        if not batch:
            break
        for row in batch:
            t, low, high, open_, close, volume = row
            rows[int(t)] = {
                "t": int(t),
                "low": float(low),
                "high": float(high),
                "open": float(open_),
                "close": float(close),
                "volume": float(volume),
            }
        oldest = min(int(r[0]) for r in batch)
        new_end = datetime.fromtimestamp(oldest, tz=timezone.utc) - timedelta(seconds=GRANULARITY)
        if new_end >= end:  # no progress: stop rather than loop forever
            break
        end = new_end

    return [rows[k] for k in sorted(rows)]


def sma(values, period):
    out = [None] * len(values)
    run = 0.0
    for i, v in enumerate(values):
        run += v
        if i >= period:
            run -= values[i - period]
        if i >= period - 1:
            out[i] = run / period
    return out


def rsi(values, period):
    out = [None] * len(values)
    gains = losses = 0.0
    avg_gain = avg_loss = 0.0
    for i in range(1, len(values)):
        change = values[i] - values[i - 1]
        gain, loss = max(change, 0.0), max(-change, 0.0)
        if i <= period:
            gains += gain
            losses += loss
            if i == period:
                avg_gain, avg_loss = gains / period, losses / period
                out[i] = 100.0 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss)
        else:
            avg_gain = (avg_gain * (period - 1) + gain) / period
            avg_loss = (avg_loss * (period - 1) + loss) / period
            out[i] = 100.0 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss)
    return out


def run_signals(closes, in_market):
    """Walk the signal series and return performance. A signal computed on day
    i is acted on from day i+1, so nothing here can peek at tomorrow."""
    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    trades = 0
    days_in = 0
    holding = False

    for i in range(1, len(closes)):
        want = in_market[i - 1]
        if want != holding:
            equity *= 1 - FEE_PER_SIDE
            trades += 1
            holding = want
        if holding:
            equity *= closes[i] / closes[i - 1]
            days_in += 1
        peak = max(peak, equity)
        max_dd = max(max_dd, (peak - equity) / peak)

    return {
        "return_pct": (equity - 1) * 100,
        "max_drawdown_pct": max_dd * 100,
        "trades": trades,
        "exposure_pct": days_in / max(1, len(closes) - 1) * 100,
    }


def strat_hold(closes, _params):
    return [True] * len(closes)


def strat_sma_cross(closes, params):
    fast_p, slow_p = params
    fast, slow = sma(closes, fast_p), sma(closes, slow_p)
    return [bool(f and s and f > s) for f, s in zip(fast, slow)]


def strat_rsi(closes, params):
    period, oversold = params
    values = rsi(closes, period)
    overbought = 100 - oversold
    signals = []
    holding = False
    for v in values:
        if v is not None:
            if not holding and v <= oversold:
                holding = True
            elif holding and v >= overbought:
                holding = False
        signals.append(holding)
    return signals


def strat_breakout(closes, params):
    entry_p, exit_p = params
    signals = []
    holding = False
    for i in range(len(closes)):
        if i >= entry_p:
            high = max(closes[i - entry_p:i])
            low = min(closes[max(0, i - exit_p):i])
            if not holding and closes[i] > high:
                holding = True
            elif holding and closes[i] < low:
                holding = False
        signals.append(holding)
    return signals


FAMILIES = {
    "Пересечение средних": (
        strat_sma_cross,
        [(f, s) for f in (5, 10, 20) for s in (30, 50, 100)],
    ),
    "RSI, откуп перепроданности": (
        strat_rsi,
        [(p, o) for p in (7, 14, 21) for o in (25, 30, 35)],
    ),
    "Пробой канала": (
        strat_breakout,
        [(e, x) for e in (10, 20, 30) for x in (5, 10, 20)],
    ),
}


def evaluate(closes):
    hold = run_signals(closes, strat_hold(closes, None))
    results = {}
    for name, (fn, grid) in FAMILIES.items():
        runs = []
        for params in grid:
            res = run_signals(closes, fn(closes, params))
            res["params"] = params
            runs.append(res)
        results[name] = runs
    return hold, results


def _fmt(value):
    return f"{value:+.1f}%"


def report(candles):
    closes = [c["close"] for c in candles]
    first = datetime.fromtimestamp(candles[0]["t"], tz=timezone.utc).strftime("%d.%m.%Y")
    last = datetime.fromtimestamp(candles[-1]["t"], tz=timezone.utc).strftime("%d.%m.%Y")

    hold, results = evaluate(closes)
    half = len(closes) // 2
    hold_a, results_a = evaluate(closes[:half])
    hold_b, results_b = evaluate(closes[half:])

    lines = [
        f"# Бэктест ICP: {first} - {last}",
        "",
        f"Дневных свечей: **{len(closes)}**. Комиссия и проскальзывание: "
        f"**{FEE_PER_SIDE * 100:.1f}% с каждого входа и выхода**.",
        "",
        "## База: просто купить и держать",
        "",
        "| Доходность | Максимальная просадка |",
        "|---|---|",
        f"| {_fmt(hold['return_pct'])} | -{hold['max_drawdown_pct']:.1f}% |",
        "",
        "## Семейства правил - весь перебор параметров, а не лучший вариант",
        "",
        "| Правило | Медиана | Худший | Лучший | Обошли «держать» | Сделок (медиана) |",
        "|---|---|---|---|---|---|",
    ]

    for name, runs in results.items():
        returns = sorted(r["return_pct"] for r in runs)
        beat = sum(1 for r in runs if r["return_pct"] > hold["return_pct"])
        trades = statistics.median(r["trades"] for r in runs)
        lines.append(
            f"| {name} | {_fmt(statistics.median(returns))} | {_fmt(returns[0])} | "
            f"{_fmt(returns[-1])} | {beat} из {len(runs)} | {trades:.0f} |"
        )

    lines += [
        "",
        "## Проверка на устойчивость",
        "",
        "История поделена пополам. Если правило работает, а не подогнано, его "
        "медиана должна быть похожей на обеих половинах. Расхождение в разные "
        "стороны означает, что результат на всей истории - совпадение.",
        "",
        "| Правило | Первая половина | Вторая половина | Согласуются |",
        "|---|---|---|---|",
    ]

    for name in results:
        med_a = statistics.median(r["return_pct"] for r in results_a[name])
        med_b = statistics.median(r["return_pct"] for r in results_b[name])
        agree = "да" if (med_a > 0) == (med_b > 0) else "**нет**"
        lines.append(f"| {name} | {_fmt(med_a)} | {_fmt(med_b)} | {agree} |")

    lines += [
        "",
        f"Для сравнения, «держать» на половинах: {_fmt(hold_a['return_pct'])} и "
        f"{_fmt(hold_b['return_pct'])}.",
        "",
        "## Как это читать",
        "",
        "Смотрите на медиану и на разброс, а не на лучший результат. Лучший из "
        "девяти вариантов - это максимум выборки, он завышен уже потому, что его "
        "выбрали как максимум. Если медиана ниже «держать», семейство не работает, "
        "сколько бы ни было хорошо у одного набора параметров.",
        "",
        "Колонка «Согласуются» важнее доходности. «Нет» означает, что правило вело "
        "себя по-разному на двух отрезках одной и той же истории - то есть "
        "объясняет прошлое, а не предсказывает будущее.",
        "",
        "Расчёт описывает то, что уже произошло, и не является инвестиционной "
        "рекомендацией.",
    ]
    return "\n".join(lines)


def main():
    candles = fetch_history()
    if len(candles) < 120:
        print(f"Слишком мало данных: {len(candles)} свечей")
        return 1
    print(report(candles))
    return 0


if __name__ == "__main__":
    sys.exit(main())
