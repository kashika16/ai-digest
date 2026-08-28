from ai_digest.briefing import build_briefing_items
from ai_digest.config import DigestConfig
from ai_digest.emailer import send_email
from ai_digest.pipeline import build_digest_entries, local_now
from ai_digest.render import build_html, build_plaintext, build_subject
from ai_digest.state import load_last_sent_date, load_seen_links, save_last_sent_date, save_seen_links
from ai_digest.sources import load_sources


def build_digest_content(config: DigestConfig, ignore_seen: bool = False) -> tuple[str, str, str, set[str]]:
    sources = load_sources(config.sources_file)
    seen_links = load_seen_links(config)
    now_local, entries, new_seen_links = build_digest_entries(
        config,
        sources,
        ignore_seen=ignore_seen,
        seen_links=seen_links,
    )
    briefing_items = build_briefing_items(entries)
    subject = build_subject(config.subject_prefix, now_local)
    plain_body = build_plaintext(now_local, config.hours_back, briefing_items)
    html_body = build_html(now_local, config.hours_back, briefing_items)
    return subject, plain_body, html_body, new_seen_links


def preview_digest(config: DigestConfig, ignore_seen: bool = False) -> str:
    subject, plain_body, _, _ = build_digest_content(config, ignore_seen=ignore_seen)
    return f"{subject}\n\n{plain_body}"


def preview_digest_html(config: DigestConfig, ignore_seen: bool = False) -> str:
    _, _, html_body, _ = build_digest_content(config, ignore_seen=ignore_seen)
    return html_body


def run_digest(config: DigestConfig, ignore_seen: bool = False) -> None:
    subject, plain_body, html_body, new_seen_links = build_digest_content(config, ignore_seen=ignore_seen)
    send_email(config, subject, plain_body, html_body)
    save_seen_links(config, new_seen_links)


def run_scheduled_digest(config: DigestConfig, target_hour: int = 7) -> str:
    now = local_now(config)
    if now.hour != target_hour:
        return f"skip: local hour is {now.hour:02d}, target is {target_hour:02d}"

    today = now.date().isoformat()
    if load_last_sent_date(config) == today:
        return f"skip: already sent on {today}"

    run_digest(config)
    save_last_sent_date(config, today)
    return f"sent: {today}"
