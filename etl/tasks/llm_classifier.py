"""Async LLM classifier — batches raw events through Claude, returns EnrichedSignal dicts.

Design notes:
- Uses AsyncAnthropic + asyncio.gather for concurrent batch processing (20 at a time).
- System prompt is marked cache_control: ephemeral — saves ~90% on system-prompt tokens.
- Any API error or JSON parse failure falls back to category="noise", confidence=0.0.
- Signals with confidence < LOW_CONFIDENCE_THRESHOLD are flagged (not discarded).
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import anthropic
from anthropic import AsyncAnthropic, RateLimitError
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from etl.models import ClassificationResult, EnrichedSignal, NOISE_FALLBACK

logger = logging.getLogger(__name__)

LLM_MODEL: str = os.environ.get("LLM_MODEL", "claude-sonnet-4-20250514")
LLM_MAX_TOKENS: int = int(os.environ.get("LLM_MAX_TOKENS", "512"))
LOW_CONFIDENCE_THRESHOLD: float = 0.6
BATCH_SIZE: int = 20

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "classification_prompt.txt"


def _load_system_prompt() -> str:
    if not _PROMPT_PATH.exists():
        raise FileNotFoundError(f"Classification prompt not found: {_PROMPT_PATH}")
    return _PROMPT_PATH.read_text(encoding="utf-8")


_SYSTEM_PROMPT: str = _load_system_prompt()


def _parse_classification(raw: str) -> ClassificationResult:
    """Parse LLM text output into a ClassificationResult.

    Strips markdown code fences if present before parsing.
    Raises json.JSONDecodeError or pydantic.ValidationError on failure.
    """
    text = raw.strip()
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1].lstrip("json").strip() if len(parts) >= 2 else text
    return ClassificationResult.model_validate(json.loads(text))


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=2, min=4, max=60),
    retry=retry_if_exception_type(RateLimitError),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
async def _classify_one(
    client: AsyncAnthropic,
    event: dict,
) -> EnrichedSignal:
    """Classify a single raw event dict. Falls back to noise on any non-429 error."""
    event_id: str = event.get("event_id", "")
    raw_text: str = event.get("raw_text", "")

    classification = NOISE_FALLBACK
    try:
        response = await client.messages.create(
            model=LLM_MODEL,
            max_tokens=LLM_MAX_TOKENS,
            system=[
                {
                    "type": "text",
                    "text": _SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": raw_text}],
        )
        raw_output = response.content[0].text
        classification = _parse_classification(raw_output)
    except RateLimitError:
        # Let tenacity retry handle this
        raise
    except (json.JSONDecodeError, Exception) as exc:
        logger.warning(
            "Classification failed for event_id=%s (%s: %s) — falling back to noise",
            event_id,
            type(exc).__name__,
            exc,
        )

    low_confidence = classification.confidence < LOW_CONFIDENCE_THRESHOLD
    if low_confidence:
        logger.info(
            "Low-confidence signal flagged for review: event_id=%s confidence=%.2f category=%s",
            event_id,
            classification.confidence,
            classification.category,
        )

    return EnrichedSignal(
        event_id=event_id,
        source=event.get("source", ""),
        collected_at=event.get("collected_at", datetime.now(tz=timezone.utc)),
        raw_text=raw_text,
        url=event.get("url", ""),
        author=event.get("author", ""),
        engagement_score=float(event.get("engagement_score", 0.0)),
        metadata=event.get("metadata", {}),
        category=classification.category,
        confidence=classification.confidence,
        topic_tags=classification.topic_tags,
        sentiment=classification.sentiment,
        urgency=classification.urgency,
        reasoning=classification.reasoning,
        low_confidence=low_confidence,
        enriched_at=datetime.now(tz=timezone.utc),
    )


async def classify_batch(events: list[dict]) -> list[EnrichedSignal]:
    """Classify a list of raw event dicts concurrently in batches of BATCH_SIZE.

    Never raises — failed individual classifications fall back to noise.
    """
    if not events:
        return []

    client = AsyncAnthropic()
    results: list[EnrichedSignal] = []

    for i in range(0, len(events), BATCH_SIZE):
        chunk = events[i : i + BATCH_SIZE]
        tasks = [_classify_one(client, ev) for ev in chunk]
        chunk_results = await asyncio.gather(*tasks, return_exceptions=True)

        for ev, outcome in zip(chunk, chunk_results):
            if isinstance(outcome, BaseException):
                logger.error(
                    "Unrecoverable error classifying event_id=%s: %s",
                    ev.get("event_id", "?"),
                    outcome,
                )
                # Build a noise fallback signal so the event is not silently lost
                results.append(
                    EnrichedSignal(
                        event_id=ev.get("event_id", ""),
                        source=ev.get("source", ""),
                        collected_at=ev.get("collected_at", datetime.now(tz=timezone.utc)),
                        raw_text=ev.get("raw_text", ""),
                        url=ev.get("url", ""),
                        author=ev.get("author", ""),
                        engagement_score=float(ev.get("engagement_score", 0.0)),
                        metadata=ev.get("metadata", {}),
                        **NOISE_FALLBACK.model_dump(),
                        low_confidence=True,
                        enriched_at=datetime.now(tz=timezone.utc),
                    )
                )
            else:
                results.append(outcome)

    logger.info("Classified %d events (batch_size=%d)", len(results), BATCH_SIZE)
    return results


def classify_batch_sync(events: list[dict]) -> list[dict]:
    """Synchronous entry point for Airflow tasks.

    Returns dicts rather than EnrichedSignal objects so they're XCom-serializable.
    """
    signals = asyncio.run(classify_batch(events))
    return [s.model_dump(mode="json") for s in signals]
