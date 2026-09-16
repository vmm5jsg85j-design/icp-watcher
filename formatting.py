"""Number and message formatting.

Deliberately imports NOTHING: both the always-on bot and the dependency-free
cron script build the same shaped snapshot object and share this wording, so a
change to the text lands in both without dragging httpx into a cron job.
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
    arrow = "🟢 +" if percent > 0 else ("🔴 " if percent < 0 else "⚪ ")
    return f"{arrow}{percent:.2f}%"


def format_snapshot(s) -> str:
    return "\n".join([
        "📊 <b>Internet Computer (ICP)</b>",
        "",
        f"💵 Цена: <b>${s.price:.3f}</b>   {_signed(s.change_percent)} за 24 ч",
        f"📈 Максимум: ${s.high:.3f}    📉 Минимум: ${s.low:.3f}",
        "",
        "<b>🔄 Оборот за 24 часа</b>",
        f"• {_amount(s.volume_coin)} ICP — {_usd(s.volume_usd)}",
        f"• Сделок: {_amount(s.trades)}",
        "",
        "<b>⚖️ Кто был активнее</b>",
        f"• Покупали: {_amount(s.bought_coin)} ICP — {_usd(s.bought_usd)} ({s.bought_share:.1f}%)",
        f"• Продавали: {_amount(s.sold_coin)} ICP — {_usd(s.sold_usd)} ({s.sold_share:.1f}%)",
        "",
        "<i>Разбивка — по инициатору сделки. У каждой сделки есть и покупатель, "
        "и продавец, поэтому это оценка того, кто продавливал цену, а не буквальный "
        "подсчёт купленного и проданного.</i>",
    ])


def format_alert(s, threshold: float) -> str:
    return "\n".join([
        f"🚀 <b>ICP вырос на {s.change_percent:.1f}% за 24 часа</b>",
        f"<i>(порог уведомления — {threshold:.0f}%)</i>",
        "",
        f"💵 Цена: <b>${s.price:.3f}</b>   было ${s.open_price:.3f}",
        f"🔄 Оборот: {_amount(s.volume_coin)} ICP — {_usd(s.volume_usd)}",
        f"⚖️ Покупали {s.bought_share:.1f}% / продавали {s.sold_share:.1f}%",
        "",
        "Это не инвестиционная рекомендация.",
    ])
