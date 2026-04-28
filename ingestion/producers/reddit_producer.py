"""Reddit producer — polls configured subreddits and publishes raw events to Kafka."""

import logging
import os
import time
from datetime import datetime, timezone

import praw
import praw.models
from praw.exceptions import PRAWException, RedditAPIException

from ingestion.config.kafka_config import TOPIC_RAW, create_producer, publish_with_retry
from ingestion.models import RawEvent, make_event_id

logger = logging.getLogger(__name__)

_POSTS_PER_POLL = 25


class RedditProducer:
    """Polls subreddits every REDDIT_POLL_INTERVAL seconds and publishes to raw_signals."""

    def __init__(self) -> None:
        client_id = os.environ["REDDIT_CLIENT_ID"]
        client_secret = os.environ["REDDIT_CLIENT_SECRET"]
        user_agent = os.environ.get("REDDIT_USER_AGENT", "trend-arbitrage/1.0")

        self._subreddits: list[str] = [
            s.strip()
            for s in os.environ.get(
                "REDDIT_SUBREDDITS", "technology,marketing,entrepreneur"
            ).split(",")
            if s.strip()
        ]
        self._poll_interval: int = int(os.environ.get("REDDIT_POLL_INTERVAL", "90"))

        self._reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent,
        )
        self._producer = create_producer()
        logger.info(
            "RedditProducer ready — subreddits=%s interval=%ds",
            self._subreddits,
            self._poll_interval,
        )

    def run(self) -> None:
        """Poll indefinitely. Catches per-subreddit errors and continues the loop."""
        logger.info("RedditProducer starting")
        while True:
            for name in self._subreddits:
                try:
                    self._poll_subreddit(name)
                except RedditAPIException as exc:
                    logger.warning("Reddit API error for r/%s: %s", name, exc)
                except PRAWException as exc:
                    logger.warning("PRAW error for r/%s: %s", name, exc)
                except Exception as exc:  # noqa: BLE001 — unknown third-party errors
                    logger.error("Unexpected error polling r/%s: %s", name, exc)
            time.sleep(self._poll_interval)

    def _poll_subreddit(self, subreddit_name: str) -> None:
        subreddit = self._reddit.subreddit(subreddit_name)
        for post in subreddit.new(limit=_POSTS_PER_POLL):
            event = self._build_event(post, subreddit_name)
            publish_with_retry(
                self._producer,
                TOPIC_RAW,
                event.to_kafka_payload(),
                key=event.event_id,
            )

    def _build_event(self, post: praw.models.Submission, subreddit_name: str) -> RawEvent:
        body = (post.selftext or "").strip()
        text = f"{post.title}\n{body}".strip() if body else post.title
        return RawEvent(
            event_id=make_event_id("reddit", post.id),
            source="reddit",
            collected_at=datetime.now(tz=timezone.utc),
            raw_text=text,
            url=f"https://reddit.com{post.permalink}",
            author=str(post.author) if post.author else "[deleted]",
            engagement_score=float(post.score),
            metadata={
                "post_id": post.id,
                "subreddit": subreddit_name,
                "upvote_ratio": float(post.upvote_ratio),
                "num_comments": int(post.num_comments),
                "flair": post.link_flair_text,
            },
        )


if __name__ == "__main__":
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    RedditProducer().run()
