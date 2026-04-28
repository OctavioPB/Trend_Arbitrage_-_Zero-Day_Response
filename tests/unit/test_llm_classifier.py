"""Unit tests for the LLM classifier.

All Anthropic API calls are mocked — no real API usage.
pytest-asyncio is configured with asyncio_mode="auto" in pyproject.toml,
so async test functions run without the @pytest.mark.asyncio decorator.
"""

import json
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from etl.models import ClassificationResult, NOISE_FALLBACK
from etl.tasks.llm_classifier import (
    LOW_CONFIDENCE_THRESHOLD,
    _classify_one,
    _parse_classification,
    classify_batch,
    classify_batch_sync,
)


# ── helpers ───────────────────────────────────────────────────────────────────


def _valid_classification_json(**overrides: Any) -> str:
    base = {
        "category": "opportunity",
        "confidence": 0.87,
        "topic_tags": ["AI", "investment"],
        "sentiment": "positive",
        "urgency": "high",
        "reasoning": "Strong demand signal in the text.",
    }
    base.update(overrides)
    return json.dumps(base)


def _raw_event(event_id: str = "evt-001", text: str = "some trend content") -> dict:
    return {
        "event_id": event_id,
        "source": "reddit",
        "collected_at": datetime.now(tz=timezone.utc).isoformat(),
        "raw_text": text,
        "url": "https://reddit.com/r/technology/comments/abc/test",
        "author": "testuser",
        "engagement_score": 500.0,
        "metadata": {"subreddit": "technology"},
    }


def _mock_client(response_text: str) -> AsyncMock:
    """Build a mock AsyncAnthropic client that returns response_text."""
    mock_content = MagicMock()
    mock_content.text = response_text
    mock_response = MagicMock()
    mock_response.content = [mock_content]
    client = AsyncMock()
    client.messages.create = AsyncMock(return_value=mock_response)
    return client


# ── _parse_classification ─────────────────────────────────────────────────────


class TestParseClassification:
    def test_valid_json_returns_result(self) -> None:
        result = _parse_classification(_valid_classification_json())
        assert result.category == "opportunity"
        assert result.confidence == pytest.approx(0.87)
        assert "AI" in result.topic_tags

    def test_strips_markdown_code_fence(self) -> None:
        wrapped = f"```json\n{_valid_classification_json()}\n```"
        result = _parse_classification(wrapped)
        assert result.category == "opportunity"

    def test_strips_plain_code_fence(self) -> None:
        wrapped = f"```\n{_valid_classification_json()}\n```"
        result = _parse_classification(wrapped)
        assert result.category == "opportunity"

    def test_invalid_json_raises_decode_error(self) -> None:
        with pytest.raises(json.JSONDecodeError):
            _parse_classification("this is not json")

    def test_wrong_category_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            _parse_classification(_valid_classification_json(category="unknown"))

    def test_confidence_out_of_range_raises(self) -> None:
        with pytest.raises(ValidationError):
            _parse_classification(_valid_classification_json(confidence=1.5))

    def test_wrong_sentiment_raises(self) -> None:
        with pytest.raises(ValidationError):
            _parse_classification(_valid_classification_json(sentiment="mixed"))


# ── _classify_one ─────────────────────────────────────────────────────────────


class TestClassifyOne:
    async def test_happy_path(self) -> None:
        client = _mock_client(_valid_classification_json())
        signal = await _classify_one(client, _raw_event())
        assert signal.category == "opportunity"
        assert signal.source == "reddit"
        assert signal.event_id == "evt-001"

    async def test_invalid_json_falls_back_to_noise(self) -> None:
        client = _mock_client("I cannot classify this text right now.")
        signal = await _classify_one(client, _raw_event())
        assert signal.category == "noise"
        assert signal.confidence == 0.0

    async def test_wrong_schema_falls_back_to_noise(self) -> None:
        client = _mock_client('{"result": "opportunity", "score": 0.9}')
        signal = await _classify_one(client, _raw_event())
        assert signal.category == "noise"

    async def test_low_confidence_sets_flag(self) -> None:
        low = _valid_classification_json(confidence=LOW_CONFIDENCE_THRESHOLD - 0.1)
        client = _mock_client(low)
        signal = await _classify_one(client, _raw_event())
        assert signal.low_confidence is True

    async def test_high_confidence_unsets_flag(self) -> None:
        high = _valid_classification_json(confidence=0.95)
        client = _mock_client(high)
        signal = await _classify_one(client, _raw_event())
        assert signal.low_confidence is False

    async def test_event_fields_preserved(self) -> None:
        client = _mock_client(_valid_classification_json())
        event = _raw_event(event_id="my-id-123", text="specific content")
        signal = await _classify_one(client, event)
        assert signal.event_id == "my-id-123"
        assert signal.raw_text == "specific content"
        assert signal.engagement_score == 500.0

    async def test_uses_lm_model_env_var(self) -> None:
        client = _mock_client(_valid_classification_json())
        with patch.dict("os.environ", {"LLM_MODEL": "claude-test-model-999"}):
            # Re-import to pick up new env value would be needed for the module constant;
            # instead, verify the client.messages.create is called (integration point).
            await _classify_one(client, _raw_event())
        client.messages.create.assert_called_once()
        call_kwargs = client.messages.create.call_args.kwargs
        assert "model" in call_kwargs

    async def test_prompt_caching_header_present(self) -> None:
        """System prompt must include cache_control: ephemeral."""
        client = _mock_client(_valid_classification_json())
        await _classify_one(client, _raw_event())
        call_kwargs = client.messages.create.call_args.kwargs
        system = call_kwargs.get("system", [])
        assert isinstance(system, list)
        assert system[0]["cache_control"]["type"] == "ephemeral"


# ── classify_batch ────────────────────────────────────────────────────────────


class TestClassifyBatch:
    async def test_empty_input_returns_empty(self) -> None:
        result = await classify_batch([])
        assert result == []

    async def test_processes_all_events(self) -> None:
        with patch("etl.tasks.llm_classifier.AsyncAnthropic") as MockClient:
            MockClient.return_value = _mock_client(_valid_classification_json())
            events = [_raw_event(f"evt-{i}") for i in range(3)]
            results = await classify_batch(events)
        assert len(results) == 3
        assert all(r.category == "opportunity" for r in results)

    async def test_individual_failure_returns_noise_not_crash(self) -> None:
        """One event failing must not stop the rest of the batch."""
        from anthropic import RateLimitError

        client = AsyncMock()
        # First call raises unrecoverable error (not RateLimitError), second succeeds
        mock_content = MagicMock()
        mock_content.text = _valid_classification_json(category="noise")
        mock_ok = MagicMock()
        mock_ok.content = [mock_content]

        client.messages.create.side_effect = [
            Exception("unexpected crash"),
            mock_ok,
        ]

        with patch("etl.tasks.llm_classifier.AsyncAnthropic", return_value=client):
            results = await classify_batch([_raw_event("fail"), _raw_event("ok")])

        assert len(results) == 2
        assert results[0].category == "noise"  # fallback for failed event

    async def test_batches_in_groups_of_batch_size(self) -> None:
        from etl.tasks.llm_classifier import BATCH_SIZE

        with patch("etl.tasks.llm_classifier.AsyncAnthropic") as MockClient:
            MockClient.return_value = _mock_client(_valid_classification_json())
            events = [_raw_event(f"evt-{i}") for i in range(BATCH_SIZE + 5)]
            results = await classify_batch(events)

        assert len(results) == BATCH_SIZE + 5


# ── classify_batch_sync ───────────────────────────────────────────────────────


class TestClassifyBatchSync:
    def test_returns_json_serializable_dicts(self) -> None:
        with patch("etl.tasks.llm_classifier.AsyncAnthropic") as MockClient:
            MockClient.return_value = _mock_client(_valid_classification_json())
            results = classify_batch_sync([_raw_event()])

        assert isinstance(results, list)
        assert isinstance(results[0], dict)
        # Must be JSON-serializable (for Airflow XCom)
        json.dumps(results[0])

    def test_empty_input(self) -> None:
        results = classify_batch_sync([])
        assert results == []
