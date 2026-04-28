"""Twitter producer — connects to v2 filtered stream and publishes raw events to Kafka."""

import logging
import os
from datetime import datetime, timezone

import tweepy

from ingestion.config.kafka_config import TOPIC_RAW, create_producer, publish_with_retry
from ingestion.models import RawEvent, make_event_id

logger = logging.getLogger(__name__)


class _TweetStreamListener(tweepy.StreamingClient):
    """Processes incoming tweets and publishes them to Kafka."""

    def __init__(self, bearer_token: str, kafka_producer, **kwargs) -> None:
        super().__init__(bearer_token, wait_on_rate_limit=True, **kwargs)
        self._kafka_producer = kafka_producer

    def on_tweet(self, tweet: tweepy.Tweet) -> None:
        try:
            event = _build_event(tweet)
            publish_with_retry(
                self._kafka_producer,
                TOPIC_RAW,
                event.to_kafka_payload(),
                key=event.event_id,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to publish tweet %s: %s", tweet.id, exc)

    def on_errors(self, errors: object) -> None:
        logger.error("Twitter stream errors: %s", errors)

    def on_disconnect(self) -> None:
        logger.warning("Twitter stream disconnected — tweepy will attempt reconnect")


def _build_event(tweet: tweepy.Tweet) -> RawEvent:
    metrics = tweet.public_metrics or {}
    engagement = (
        metrics.get("like_count", 0)
        + metrics.get("retweet_count", 0)
        + metrics.get("reply_count", 0)
        + metrics.get("quote_count", 0)
    )
    tweet_url = f"https://twitter.com/i/web/status/{tweet.id}"
    author = str(tweet.author_id) if tweet.author_id else ""

    return RawEvent(
        event_id=make_event_id("twitter", str(tweet.id)),
        source="twitter",
        collected_at=tweet.created_at or datetime.now(tz=timezone.utc),
        raw_text=tweet.text,
        url=tweet_url,
        author=author,
        engagement_score=float(engagement),
        metadata={
            "tweet_id": str(tweet.id),
            "like_count": metrics.get("like_count", 0),
            "retweet_count": metrics.get("retweet_count", 0),
            "reply_count": metrics.get("reply_count", 0),
            "quote_count": metrics.get("quote_count", 0),
            "conversation_id": str(tweet.conversation_id) if tweet.conversation_id else None,
        },
    )


class TwitterProducer:
    """Connects to the Twitter v2 filtered stream and publishes matching tweets."""

    def __init__(self) -> None:
        bearer_token = os.environ.get("TWITTER_BEARER_TOKEN", "")
        if not bearer_token:
            raise EnvironmentError("TWITTER_BEARER_TOKEN is not set")

        self._filter_terms: list[str] = [
            t.strip()
            for t in os.environ.get("TWITTER_FILTER_TERMS", "").split(",")
            if t.strip()
        ]
        if not self._filter_terms:
            logger.warning(
                "TWITTER_FILTER_TERMS is empty — stream will match nothing. "
                "Set it to comma-separated handles or keywords."
            )

        producer = create_producer()
        self._stream = _TweetStreamListener(bearer_token=bearer_token, kafka_producer=producer)

    def run(self) -> None:
        """Configure stream rules and block until the stream is disconnected."""
        self._configure_rules()
        logger.info("TwitterProducer connecting to filtered stream")
        self._stream.filter(
            tweet_fields=["author_id", "public_metrics", "created_at", "conversation_id"],
        )

    def _configure_rules(self) -> None:
        existing = self._stream.get_rules()
        if existing.data:
            ids = [rule.id for rule in existing.data]
            self._stream.delete_rules(ids)
            logger.info("Deleted %d existing stream rules", len(ids))

        for term in self._filter_terms:
            self._stream.add_rules(tweepy.StreamRule(term))
        logger.info("Twitter stream rules configured: %s", self._filter_terms)


if __name__ == "__main__":
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    TwitterProducer().run()
