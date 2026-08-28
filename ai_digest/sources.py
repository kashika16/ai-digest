from pathlib import Path
import json

from ai_digest.models import Source


def load_sources(path: Path) -> list[Source]:
    raw_sources = json.loads(path.read_text())
    return [
        Source(
            name=item["name"],
            url=item["url"],
            category=item["category"],
            priority=item["priority"],
            max_items=item["max_items"],
            include_keywords=tuple(keyword.lower() for keyword in item.get("include_keywords", [])),
            exclude_keywords=tuple(keyword.lower() for keyword in item.get("exclude_keywords", [])),
        )
        for item in raw_sources
    ]
