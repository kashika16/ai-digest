import re

from ai_digest.models import BriefingItem, FeedEntry


SECTION_ORDER = [
    "Launches and Product",
    "Product and Strategy",
    "Market and Startups",
    "Policy and Safety",
    "Community Signal",
    "Research",
    "Other",
]

LAUNCH_KEYWORDS = ("launch", "release", "ship", "introduce", "announce", "rollout", "debut", "gemini")
PRODUCT_KEYWORDS = ("product", "podcast", "builder", "founder", "pm", "workflow", "cursor", "chatgpt", "codex")
MARKET_KEYWORDS = ("raise", "raises", "raised", "acquire", "acquires", "acquisition", "valuation", "startup", "funding")
POLICY_KEYWORDS = ("policy", "safety", "regulation", "regulatory", "watermark", "trust", "governance", "preparedness")
ABBREVIATION_PATTERN = re.compile(r"\b(?:vs|e\.g|i\.e|mr|mrs|ms|dr|prof|u\.s|u\.k)\.", re.IGNORECASE)


def build_briefing_items(entries: list[FeedEntry]) -> list[BriefingItem]:
    return [build_briefing_item(entry) for entry in entries]


def build_briefing_item(entry: FeedEntry) -> BriefingItem:
    section = derive_section(entry)
    key_points = tuple(derive_key_points(entry))
    why_it_matters = derive_why_it_matters(entry, section)
    return BriefingItem(entry=entry, section=section, key_points=key_points, why_it_matters=why_it_matters)


def derive_section(entry: FeedEntry) -> str:
    category = entry.source.category.lower()
    blob = entry_blob(entry)
    if category == "research":
        return "Research"
    if category == "community":
        return "Community Signal"
    if contains_any(blob, POLICY_KEYWORDS):
        return "Policy and Safety"
    if contains_any(blob, MARKET_KEYWORDS):
        return "Market and Startups"
    if category == "product":
        return "Product and Strategy"
    if contains_any(blob, LAUNCH_KEYWORDS):
        return "Launches and Product"
    if contains_any(blob, PRODUCT_KEYWORDS):
        return "Product and Strategy"
    if category == "company":
        return "Launches and Product"
    if category == "news":
        return "Market and Startups"
    return "Other"


def derive_key_points(entry: FeedEntry) -> list[str]:
    sentences = extract_sentences(summary_body(entry))
    if entry.source.category.lower() == "research":
        return research_key_points(entry, sentences)
    if entry.source.category.lower() == "community":
        return community_key_points(entry, sentences)
    if not sentences:
        return [trim_point(entry.title), fallback_detail_point(entry)]
    key_points = [trim_point(sentences[0])]
    if len(sentences) > 1:
        key_points.append(trim_point(sentences[1]))
    else:
        key_points.append(fallback_detail_point(entry))
    return key_points[:2]


def derive_why_it_matters(entry: FeedEntry, section: str) -> str:
    if section == "Launches and Product":
        return "This points to new model capability, distribution, or product surface that can change what teams can ship next."
    if section == "Product and Strategy":
        return "This is useful for product teams deciding where AI changes user behavior, workflows, or competitive positioning."
    if section == "Market and Startups":
        return "This helps track where capital, competition, and commercial momentum are moving in AI."
    if section == "Policy and Safety":
        return "This matters because governance and trust decisions can affect deployment risk and public adoption."
    if section == "Community Signal":
        return "This is an early attention signal from builders and developers rather than an official announcement."
    if section == "Research":
        return "This flags fresh technical work that may shape future models, evaluation methods, or product capabilities."
    return f"This is worth watching from {entry.source.name}."


def group_briefing_items(items: list[BriefingItem]) -> list[tuple[str, list[BriefingItem]]]:
    grouped: list[tuple[str, list[BriefingItem]]] = []
    for section in SECTION_ORDER:
        section_items = [item for item in items if item.section == section]
        if section_items:
            grouped.append((section, section_items))
    return grouped


def contains_any(blob: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in blob for keyword in keywords)


def entry_blob(entry: FeedEntry) -> str:
    return f"{entry.title} {entry.summary}".lower()


def summary_body(entry: FeedEntry) -> str:
    text = entry.summary.replace("\n", " ").strip()
    if "Abstract:" in text:
        return text.split("Abstract:", 1)[1].strip()
    return text


def extract_sentences(text: str) -> list[str]:
    if not text:
        return []
    protected_text, replacements = protect_abbreviations(text)
    candidates = re.split(r"(?<=[.!?])\s+", protected_text)
    return [restore_abbreviations(candidate.strip(), replacements) for candidate in candidates if candidate.strip()]


def protect_abbreviations(text: str) -> tuple[str, list[tuple[str, str]]]:
    replacements: list[tuple[str, str]] = []

    def replace(match: re.Match[str]) -> str:
        token = f"__abbr_{len(replacements)}__"
        replacements.append((token, match.group(0)))
        return token

    return ABBREVIATION_PATTERN.sub(replace, text), replacements


def restore_abbreviations(text: str, replacements: list[tuple[str, str]]) -> str:
    restored = text
    for token, original in replacements:
        restored = restored.replace(token, original)
    return restored


def trim_point(text: str, max_chars: int = 220) -> str:
    compact = " ".join(text.split())
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 1].rstrip() + "…"


def fallback_detail_point(entry: FeedEntry) -> str:
    return f"Published by {entry.source.name} at {entry.published_at.strftime('%Y-%m-%d %H:%M UTC')}."


def community_key_points(entry: FeedEntry, sentences: list[str]) -> list[str]:
    useful_sentences = [trim_point(sentence) for sentence in sentences if sentence.lower() != "comments"]
    unique_points: list[str] = []
    for sentence in useful_sentences:
        if sentence not in unique_points:
            unique_points.append(sentence)
    if unique_points:
        return unique_points[:2]
    return [trim_point(entry.title)]


def research_key_points(entry: FeedEntry, sentences: list[str]) -> list[str]:
    if not sentences:
        return [trim_point(entry.title), fallback_detail_point(entry)]
    primary_source = sentences[0]
    if len(primary_source) < 25 and len(sentences) > 1:
        primary_source = sentences[1]
    primary = trim_point(primary_source)
    if len(sentences) > 1:
        secondary_source = sentences[1] if primary_source == sentences[0] else sentences[0]
        return [primary, trim_point(secondary_source)]
    return [primary, "This is a newly posted research paper rather than a polished news summary."]
