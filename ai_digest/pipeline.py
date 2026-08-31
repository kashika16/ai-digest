from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo
import re

from ai_digest.config import DigestConfig
from ai_digest.models import DigestBuildResult, FeedEntry, Source, SourceFetchFailure
from ai_digest.rss import fetch_feed_xml, parse_feed


WINDOW_STEP_HOURS = 24


class SourceFetchOutcome:
    def __init__(
        self,
        source: Source,
        entries: Optional[list[FeedEntry]] = None,
        failure: Optional[SourceFetchFailure] = None,
    ) -> None:
        self.source = source
        self.entries = entries or []
        self.failure = failure


def fetch_entries_for_source(source: Source) -> list[FeedEntry]:
    xml_text = fetch_feed_xml(source)
    entries = parse_feed(source, xml_text)
    entries = filter_entries_for_source(entries, source)
    return sorted(entries, key=lambda entry: entry.published_at, reverse=True)[: source.max_items]


def fetch_source_outcome(source: Source) -> SourceFetchOutcome:
    try:
        return SourceFetchOutcome(source=source, entries=fetch_entries_for_source(source))
    except Exception as error:
        return SourceFetchOutcome(source=source, failure=SourceFetchFailure(source.name, summarize_source_error(error)))


def summarize_source_error(error: Exception) -> str:
    message = " ".join(str(error).split())
    if not message:
        return type(error).__name__
    return f"{type(error).__name__}: {message}"


def fetch_all_entries(sources: list[Source]) -> tuple[list[FeedEntry], list[SourceFetchFailure]]:
    if not sources:
        return [], []

    source_order = {source: index for index, source in enumerate(sources)}
    outcomes: list[SourceFetchOutcome] = []
    with ThreadPoolExecutor(max_workers=min(len(sources), 8)) as executor:
        futures = [executor.submit(fetch_source_outcome, source) for source in sources]
        for future in as_completed(futures):
            outcomes.append(future.result())

    outcomes.sort(key=lambda outcome: source_order[outcome.source])
    entries: list[FeedEntry] = []
    unavailable_sources: list[SourceFetchFailure] = []
    for outcome in outcomes:
        entries.extend(outcome.entries)
        if outcome.failure is not None:
            unavailable_sources.append(outcome.failure)
    return entries, unavailable_sources


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


def select_entries_for_window(
    config: DigestConfig,
    entries: list[FeedEntry],
    now_utc: datetime,
    ignore_seen: bool,
    seen_links: set[str],
) -> tuple[int, list[FeedEntry]]:
    hours_back = config.hours_back
    while True:
        cutoff = recent_cutoff_for_hours(now_utc, hours_back)
        current_entries = filter_recent_entries(entries, cutoff)
        current_entries = dedupe_entries(current_entries)
        if not ignore_seen:
            current_entries = filter_unseen_entries(current_entries, seen_links)
        current_entries = rank_entries(current_entries)
        current_entries = clamp_entries(current_entries, config.max_items)
        if len(current_entries) >= config.min_digest_items or hours_back >= config.max_digest_hours_back:
            return hours_back, current_entries
        next_hours = min(hours_back + WINDOW_STEP_HOURS, config.max_digest_hours_back)
        if next_hours == hours_back:
            return hours_back, current_entries
        hours_back = next_hours


def recent_cutoff_for_hours(now_utc: datetime, hours_back: int) -> datetime:
    return now_utc - timedelta(hours=hours_back)


def unique_links(entries: list[FeedEntry]) -> list[str]:
    links: list[str] = []
    seen_links: set[str] = set()
    for entry in entries:
        if entry.link in seen_links:
            continue
        seen_links.add(entry.link)
        links.append(entry.link)
    return links


def prune_seen_links(current_seen_links: set[str], entries: list[FeedEntry], max_seen_links: int) -> set[str]:
    recent_links = unique_links(entries)
    pruned_links = recent_links + sorted(current_seen_links - set(recent_links))
    return set(pruned_links[:max_seen_links])


def build_digest_entries(
    config: DigestConfig,
    sources: list[Source],
    ignore_seen: bool = False,
    seen_links: Optional[set[str]] = None,
) -> DigestBuildResult:
    now_utc = utc_now()
    current_seen_links = seen_links or set()
    entries, unavailable_sources = fetch_all_entries(sources)
    coverage_hours, selected_entries = select_entries_for_window(
        config,
        entries,
        now_utc,
        ignore_seen,
        current_seen_links,
    )
    new_seen_links = prune_seen_links(current_seen_links | {entry.link for entry in selected_entries}, selected_entries, config.max_seen_links)
    return DigestBuildResult(
        now_local=local_now(config),
        coverage_hours=coverage_hours,
        entries=selected_entries,
        new_seen_links=new_seen_links,
        unavailable_sources=unavailable_sources,
    )
