from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo
import re

from ai_digest.config import DigestConfig
from ai_digest.models import FeedEntry, Source
from ai_digest.rss import fetch_feed_xml, parse_feed


def fetch_entries_for_source(source: Source) -> list[FeedEntry]:
    xml_text = fetch_feed_xml(source)
    entries = parse_feed(source, xml_text)
    entries = filter_entries_for_source(entries, source)
    return sorted(entries, key=lambda entry: entry.published_at, reverse=True)[: source.max_items]


def fetch_all_entries(sources: list[Source]) -> list[FeedEntry]:
    entries: list[FeedEntry] = []
    for source in sources:
        entries.extend(fetch_entries_for_source(source))
    return entries


def recent_cutoff(config: DigestConfig, now_utc: datetime) -> datetime:
    return now_utc - timedelta(hours=config.hours_back)


def filter_recent_entries(entries: list[FeedEntry], cutoff: datetime) -> list[FeedEntry]:
    return [entry for entry in entries if entry.published_at >= cutoff]


def filter_unseen_entries(entries: list[FeedEntry], seen_links: set[str]) -> list[FeedEntry]:
    return [entry for entry in entries if entry.link not in seen_links]


def dedupe_entries(entries: list[FeedEntry]) -> list[FeedEntry]:
    deduped: list[FeedEntry] = []
    seen_links: set[str] = set()
    for entry in entries:
        if entry.link in seen_links:
            continue
        seen_links.add(entry.link)
        deduped.append(entry)
    return deduped


def rank_entries(entries: list[FeedEntry]) -> list[FeedEntry]:
    return sorted(
        entries,
        key=lambda entry: (entry.source.priority, entry.published_at),
        reverse=True,
    )


def clamp_entries(entries: list[FeedEntry], max_items: int) -> list[FeedEntry]:
    return entries[:max_items]


def filter_entries_for_source(entries: list[FeedEntry], source: Source) -> list[FeedEntry]:
    return [entry for entry in entries if entry_matches_source(entry, source)]


def entry_matches_source(entry: FeedEntry, source: Source) -> bool:
    blob = f"{entry.title} {entry.summary}".lower()
    if source.include_keywords and not any(keyword_present(blob, keyword) for keyword in source.include_keywords):
        return False
    if source.exclude_keywords and any(keyword_present(blob, keyword) for keyword in source.exclude_keywords):
        return False
    return True


def keyword_present(blob: str, keyword: str) -> bool:
    if " " in keyword:
        return keyword in blob
    return re.search(rf"\b{re.escape(keyword)}\b", blob) is not None


def local_now(config: DigestConfig) -> datetime:
    return datetime.now(ZoneInfo(config.timezone_name))


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def build_digest_entries(
    config: DigestConfig,
    sources: list[Source],
    ignore_seen: bool = False,
    seen_links: Optional[set[str]] = None,
) -> tuple[datetime, list[FeedEntry], set[str]]:
    now_utc = utc_now()
    cutoff = recent_cutoff(config, now_utc)
    current_seen_links = seen_links or set()
    entries = fetch_all_entries(sources)
    entries = filter_recent_entries(entries, cutoff)
    entries = dedupe_entries(entries)
    if not ignore_seen:
        entries = filter_unseen_entries(entries, current_seen_links)
    entries = rank_entries(entries)
    entries = clamp_entries(entries, config.max_items)
    new_seen_links = current_seen_links | {entry.link for entry in entries}
    return local_now(config), entries, new_seen_links
