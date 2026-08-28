from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
from typing import Optional
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

from ai_digest.models import FeedEntry, Source


USER_AGENT = "ai-digest/1.0"


class HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def text(self) -> str:
        return " ".join(part.strip() for part in self.parts if part.strip())


def fetch_feed_xml(source: Source) -> str:
    request = Request(source.url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8")


def strip_html(value: str) -> str:
    extractor = HTMLTextExtractor()
    extractor.feed(unescape(value))
    return extractor.text()


def parse_datetime(raw_value: str) -> datetime:
    try:
        published_at = parsedate_to_datetime(raw_value)
    except (TypeError, ValueError, IndexError):
        published_at = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))

    if published_at.tzinfo is None:
        return published_at.replace(tzinfo=timezone.utc)
    return published_at.astimezone(timezone.utc)


def element_text(element: Optional[ET.Element], default: str = "") -> str:
    if element is None or element.text is None:
        return default
    return element.text.strip()


def parse_rss_items(source: Source, root: ET.Element) -> list[FeedEntry]:
    items = root.findall("./channel/item")
    entries = [
        FeedEntry(
            source=source,
            title=element_text(item.find("title")),
            link=element_text(item.find("link")),
            summary=strip_html(
                element_text(item.find("description"))
                or element_text(item.find("{http://purl.org/rss/1.0/modules/content/}encoded"))
            ),
            published_at=parse_datetime(
                element_text(item.find("pubDate")) or datetime.now(timezone.utc).isoformat()
            ),
        )
        for item in items
        if element_text(item.find("title")) and element_text(item.find("link"))
    ]
    return entries


def parse_atom_items(source: Source, root: ET.Element) -> list[FeedEntry]:
    namespace = {"atom": "http://www.w3.org/2005/Atom"}
    items = root.findall("./atom:entry", namespace)
    entries = []
    for item in items:
        link = ""
        for link_element in item.findall("atom:link", namespace):
            href = link_element.attrib.get("href", "")
            rel = link_element.attrib.get("rel", "alternate")
            if href and rel == "alternate":
                link = href
                break

        title = element_text(item.find("atom:title", namespace))
        summary = element_text(item.find("atom:summary", namespace))
        if not summary:
            summary = element_text(item.find("atom:content", namespace))
        published_raw = (
            element_text(item.find("atom:published", namespace))
            or element_text(item.find("atom:updated", namespace))
            or datetime.now(timezone.utc).isoformat()
        )

        if title and link:
            entries.append(
                FeedEntry(
                    source=source,
                    title=title,
                    link=link,
                    summary=strip_html(summary),
                    published_at=parse_datetime(published_raw),
                )
            )
    return entries


def parse_feed(source: Source, xml_text: str) -> list[FeedEntry]:
    root = ET.fromstring(xml_text)
    if root.tag.endswith("rss"):
        return parse_rss_items(source, root)
    return parse_atom_items(source, root)
