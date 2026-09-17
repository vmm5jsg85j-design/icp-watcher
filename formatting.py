"""Number and message formatting.

Deliberately imports NOTHING, so the dependency-free cron script and the
always-on bot share the same wording.
"""


def _amount(value: float) -> str:
    """Thousands separated by a narrow space — readable at a glance on a phone."""
    return f"{value:,.0f}".replace(",", " ")


def _usd(value: float) -> str:
    if abs(value) >= 1_000_000_000:
        return f"${value / 1_000_000_000:.2f} млрд"
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:.2f} млн"
    if abs(value) >= 1_000:
        return f"${value / 1_000:.1f} тыс"
    return f"${value:.2f}"


def _signed(percent: float) -> str:
    mark = "🟢 +" if percent > 0 else ("🔴 " if percent < 0 else "⚪ ")
    return f"{mark}{percent:.2f}%"


def format_snapshot(s) -> str:
    lines = [
        "📊 <b>Internet Computer (ICP)</b>",
        "",
        f"💵 Цена: <b>${s.price:.3f}</b>   {_signed(s.change_percent)} за 24 ч",
        f"📈 Максимум: ${s.high:.3f}    📉 Минимум: ${s.low:.3f}",
    ]
    if getattr(s, "market_cap", 0):
        lines.append(f"🏦 Капитализация: {_usd(s.market_cap)}")

    lines += [
        "",
        "<b>🔄 Оборот ICP за 24 часа</b>",
        f"• На всех биржах: {_usd(s.volume_usd)}",
    ]
    if getattr(s, "venue_volume_coin", 0):
        # Also in dollars, or "из них" would be comparing coins to dollars.
        lines.append(
            f"• Из них на Coinbase: {_amount(s.venue_volume_coin)} ICP"
            f" (~{_usd(s.venue_volume_coin * s.price)})"
        )

    lines += [
        "",
        f"<b>⚖️ Кто активнее — последние {_amount(s.trade_count)} сделок</b>",
        f"• Покупали: {_amount(s.bought_coin)} ICP — {_usd(s.bought_usd)} ({s.bought_share:.1f}%)",
        f"• Продавали: {_amount(s.sold_coin)} ICP — {_usd(s.sold_usd)} ({s.sold_share:.1f}%)",
        "",
        "<i>Соотношение считается по свежим сделкам на Coinbase, а не за все "
        "сутки: это срез того, кто продавливает цену прямо сейчас. У каждой "
        "сделки есть и покупатель, и продавец — сторона определяется по тому, "
        "кто её инициировал.</i>",
    ]
    if getattr(s, "generated_at", ""):
        lines += ["", f"<i>Данные на {s.generated_at}</i>"]
    return "\n".join(lines)


def format_alert(s, level: float) -> str:
    """One wording for both ladders. `level` carries the direction: positive
    for a rise, negative for a fall. The headline reads the change itself, so
    a -4.7% drop announced under the -4% level says -4.7%, not -4%."""
    if level > 0:
        headline = f"🚀 <b>ICP вырос на {s.change_percent:.1f}% за 24 часа</b>"
    else:
        headline = f"🔻 <b>ICP упал на {abs(s.change_percent):.1f}% за 24 часа</b>"
    return "\n".join([
        headline,
        f"<i>(порог уведомления — {level:+.0f}%)</i>",
        "",
        f"💵 Цена: <b>${s.price:.3f}</b>",
        f"🔄 Оборот по рынку за сутки: {_usd(s.volume_usd)}",
        f"⚖️ По свежим сделкам: покупали {s.bought_share:.1f}% / продавали {s.sold_share:.1f}%",
        "",
        "Это не инвестиционная рекомендация.",
    ])
