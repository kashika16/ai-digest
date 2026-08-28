from datetime import datetime
from html import escape

from ai_digest.briefing import group_briefing_items
from ai_digest.models import BriefingItem


def build_subject(prefix: str, now_local: datetime) -> str:
    return f"{prefix} - {now_local.strftime('%Y-%m-%d')}"


def short_title(value: str, max_chars: int = 92) -> str:
    compact = " ".join(value.split())
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 1].rstrip() + "…"


def build_plaintext(now_local: datetime, hours_back: int, items: list[BriefingItem]) -> str:
    lines = [
        f"AI Daily Brief | {now_local.strftime('%Y-%m-%d %H:%M %Z')}",
        f"Coverage window: last {hours_back} hours",
        "",
    ]

    if not items:
        lines.append("No new items matched the digest window.")
        return "\n".join(lines)

    for section, section_items in group_briefing_items(items):
        lines.append(section)
        lines.append("-" * len(section))
        for index, item in enumerate(section_items, start=1):
            entry = item.entry
            lines.extend(
                [
                    f"{index}. {short_title(entry.title)}",
                    f"   {entry.source.name} | {entry.published_at.strftime('%H:%M UTC')}",
                    "   What happened:",
                ]
            )
            for point in item.key_points:
                lines.append(f"   - {point}")
            lines.extend(
                [
                    f"   Why it matters: {item.why_it_matters}",
                    f"   Read: {entry.link}",
                    "",
                ]
            )

    return "\n".join(lines).strip()


def build_html(now_local: datetime, hours_back: int, items: list[BriefingItem]) -> str:
    header = (
        "<html><body style=\"margin:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#eef3f8;color:#0f172a;\">"
        "<div style=\"max-width:900px;margin:0 auto;padding:28px 16px 40px;\">"
        "<div style=\"background:linear-gradient(135deg,#0f172a,#1d4ed8);color:#ffffff;border-radius:24px;padding:24px 28px 18px;box-shadow:0 18px 48px rgba(15,23,42,0.18);\">"
        "<h1 style=\"margin:0 0 10px;font-size:34px;line-height:1.1;\">AI company briefing</h1>"
        f"<div style=\"font-size:13px;opacity:0.9;\">{escape(now_local.strftime('%Y-%m-%d %H:%M %Z'))} | last {hours_back} hours</div>"
        "</div>"
    )

    if not items:
        return (
            header
            + "<div style=\"background:#ffffff;border-radius:20px;padding:24px;margin-top:18px;\"><p style=\"font-size:16px;margin:0;\">No new items matched the digest window.</p></div></div></body></html>"
        )

    sections = []
    for section, section_items in group_briefing_items(items):
        cards = []
        for item in section_items:
            entry = item.entry
            points = "".join(
                f"<li style=\"margin:0 0 6px;\">{escape(point)}</li>"
                for point in item.key_points
            )
            cards.append(
                "<article style=\"background:#ffffff;border:1px solid #dbe3ee;border-radius:18px;padding:18px 18px 16px;box-shadow:0 6px 18px rgba(15,23,42,0.05);\">"
                f"<div style=\"font-size:11px;color:#1d4ed8;font-weight:700;text-transform:uppercase;letter-spacing:0.08em;\">{escape(entry.source.name)} • {escape(entry.published_at.strftime('%H:%M UTC'))}</div>"
                f"<h3 style=\"font-size:22px;line-height:1.25;margin:10px 0 10px;\"><a href=\"{escape(entry.link)}\" style=\"color:#0f172a;text-decoration:none;\">{escape(entry.title)}</a></h3>"
                "<div style=\"font-size:13px;color:#0f172a;font-weight:700;margin-bottom:6px;\">Key points</div>"
                f"<ul style=\"margin:0 0 12px 18px;padding:0;color:#334155;line-height:1.65;\">{points}</ul>"
                f"<div style=\"background:#f8fafc;border-radius:12px;padding:12px 13px;font-size:13px;line-height:1.55;color:#334155;\"><strong style=\"color:#0f172a;\">Why it matters</strong><br>{escape(item.why_it_matters)}</div>"
                f"<div style=\"margin-top:12px;font-size:13px;\"><a href=\"{escape(entry.link)}\" style=\"color:#1d4ed8;text-decoration:none;font-weight:600;\">Open source story</a></div>"
                "</article>"
            )
        sections.append(
            f"<section style=\"margin-top:22px;\"><div style=\"display:flex;align-items:center;justify-content:space-between;margin-bottom:10px;\"><h2 style=\"font-size:18px;margin:0;color:#0f172a;\">{escape(section)}</h2><span style=\"font-size:12px;color:#64748b;\">{len(section_items)} items</span></div><div style=\"display:grid;grid-template-columns:1fr;gap:14px;\">{''.join(cards)}</div></section>"
        )

    return (
        header
        + "".join(sections)
        + "</div></body></html>"
    )
