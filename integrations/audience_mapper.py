"""Translate a Golden Record's audience_proxy into platform-specific targeting specs.

AudienceSpec is the common intermediate representation consumed by both
GoogleAdsAudienceSync and MetaAudienceSync. audience_mapping.json provides
topic-cluster-to-keyword expansions; topics not in the config file fall back
to the '_default' entry.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_DEFAULT_MAPPING_PATH = os.path.join(
    os.path.dirname(__file__), "..", "config", "audience_mapping.json"
)
_MAPPING_PATH_ENV = "AUDIENCE_MAPPING_PATH"


@dataclass
class AudienceSpec:
    """Platform-neutral audience definition derived from a Golden Record."""

    topic_cluster: str
    keywords: list[str] = field(default_factory=list)      # Google Ads keyword targets
    interests: list[str] = field(default_factory=list)     # Meta interest targets
    subreddits: list[str] = field(default_factory=list)    # from audience_proxy
    handles: list[str] = field(default_factory=list)       # from audience_proxy


def load_mapping() -> dict:
    """Load (and re-read each call) the audience mapping config.

    Always reads from disk so weight changes take effect without a restart.
    """
    path = os.environ.get(_MAPPING_PATH_ENV, _DEFAULT_MAPPING_PATH)
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Cannot load audience mapping from %s: %s — using empty mapping", path, exc)
        return {}


def map_audience(
    audience_proxy: dict,
    topic_cluster: str,
    mapping: dict | None = None,
) -> AudienceSpec:
    """Build an AudienceSpec from a Golden Record's audience_proxy and the mapping config.

    Args:
        audience_proxy:  JSONB dict from golden_records.audience_proxy.
        topic_cluster:   The cluster name (e.g. 'ai-chips').
        mapping:         Pre-loaded mapping dict. If None, loads from disk.
    """
    if mapping is None:
        mapping = load_mapping()

    cluster_cfg: dict = mapping.get(topic_cluster) or mapping.get("_default") or {}

    # Keywords: mapping expansion + top_topics from the proxy itself
    base_keywords: list[str] = list(cluster_cfg.get("google_ads_keywords") or [])
    proxy_topics: list[str] = list(audience_proxy.get("top_topics") or [])
    keywords = _dedupe_preserve_order(base_keywords + proxy_topics)

    # Interests: mapping expansion + proxy topics (Meta uses free-text interest names)
    base_interests: list[str] = list(cluster_cfg.get("meta_interests") or [])
    interests = _dedupe_preserve_order(base_interests + proxy_topics)

    subreddits: list[str] = list(audience_proxy.get("subreddits") or [])
    handles: list[str] = list(audience_proxy.get("handles") or [])

    return AudienceSpec(
        topic_cluster=topic_cluster,
        keywords=keywords[:50],    # platform caps
        interests=interests[:25],
        subreddits=subreddits,
        handles=handles,
    )


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result
