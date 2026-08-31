from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Source:
    name: str
    url: str
    category: str
    priority: int
    max_items: int
    include_keywords: tuple[str, ...] = ()
    exclude_keywords: tuple[str, ...] = ()


@dataclass(frozen=True)
class FeedEntry:
    source: Source
    title: str
    link: str
    summary: str
    published_at: datetime


@dataclass(frozen=True)
class BriefingItem:
    entry: FeedEntry
    section: str
    key_points: tuple[str, ...]
    why_it_matters: str


@dataclass(frozen=True)
class SourceFetchFailure:
    source_name: str
    detail: str


@dataclass
class DigestBuildResult:
    now_local: datetime
    coverage_hours: int
    entries: list[FeedEntry]
    new_seen_links: set[str]
    unavailable_sources: list[SourceFetchFailure]
