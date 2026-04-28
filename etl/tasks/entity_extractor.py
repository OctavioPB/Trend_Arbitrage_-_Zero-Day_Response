"""Entity extractor — derives audience proxy attributes from a cluster of enriched signals.

Used by the golden record generator (Sprint 4) to populate audience_proxy JSONB.
Operates on dicts that include both raw event fields (metadata, url, source) and
classification results (topic_tags).
"""

import logging
import re
import urllib.parse
from collections import Counter
from typing import Any

logger = logging.getLogger(__name__)

_REDDIT_URL_RE = re.compile(r"https?://(?:www\.)?reddit\.com/r/([^/]+)")
_MAX_TOPICS = 10


def extract_audience_proxy(signals: list[dict]) -> dict[str, Any]:
    """Extract audience proxy attributes from an enriched signal cluster.

    Args:
        signals: List of enriched signal dicts (raw + classification fields combined).

    Returns:
        Dict with keys: subreddits, twitter_handles, site_sections, top_topics.
    """
    subreddits: list[str] = []
    twitter_handles: list[str] = []
    site_sections: list[str] = []

    for signal in signals:
        source = signal.get("source", "")
        url = signal.get("url", "")
        metadata = signal.get("metadata", {})

        if source == "reddit":
            sub = _extract_subreddit(url, metadata)
            if sub:
                subreddits.append(sub)

        elif source == "twitter":
            handle = _extract_twitter_handle(signal)
            if handle:
                twitter_handles.append(handle)

        elif source == "scraper":
            section = _extract_site_section(url)
            if section:
                site_sections.append(section)

    return {
        "subreddits": _dedup(subreddits),
        "twitter_handles": _dedup(twitter_handles),
        "site_sections": _dedup(site_sections),
        "top_topics": _aggregate_topic_tags(signals),
    }


def group_by_topic(
    signals: list[dict],
    min_cluster_size: int = 2,
) -> dict[str, list[dict]]:
    """Group enriched signals by their primary topic tag.

    Signals with no topic_tags are assigned to the "__untagged__" cluster.
    Clusters smaller than min_cluster_size are discarded.
    """
    clusters: dict[str, list[dict]] = {}

    for signal in signals:
        tags = signal.get("topic_tags", [])
        primary = tags[0].lower() if tags else "__untagged__"
        clusters.setdefault(primary, []).append(signal)

    return {
        topic: sigs
        for topic, sigs in clusters.items()
        if len(sigs) >= min_cluster_size
    }


# ── private helpers ───────────────────────────────────────────────────────────


def _extract_subreddit(url: str, metadata: dict) -> str | None:
    match = _REDDIT_URL_RE.match(url)
    if match:
        return f"r/{match.group(1)}"
    sub = metadata.get("subreddit")
    return f"r/{sub}" if sub else None


def _extract_twitter_handle(signal: dict) -> str | None:
    author = signal.get("author", "")
    if not author:
        return None
    return f"@{author}" if not author.startswith("@") else author


def _extract_site_section(url: str) -> str | None:
    if not url:
        return None
    parsed = urllib.parse.urlparse(url)
    return parsed.netloc or None


def _aggregate_topic_tags(signals: list[dict]) -> list[str]:
    counter: Counter = Counter()
    for s in signals:
        for tag in s.get("topic_tags", []):
            counter[tag.lower()] += 1
    return [tag for tag, _ in counter.most_common(_MAX_TOPICS)]


def _dedup(items: list[str]) -> list[str]:
    """Deduplicate preserving insertion order."""
    return list(dict.fromkeys(items))
