"""Offset management helpers for exactly-once stream processing.

Each streaming consumer writes its last successfully committed offset to
kafka_stream_offsets immediately after the DB write succeeds.  On restart
the consumer seeks to that offset, so no message is processed twice even if
the Kafka consumer-group state is lost or reset.

All functions accept an open psycopg2 connection.  The caller is responsible
for committing the transaction after calling commit_offsets().
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def load_offsets(conn, consumer_group: str, topic: str) -> dict[int, int]:
    """Return {partition: committed_offset} for the given group and topic.

    Returns an empty dict if no offsets have been committed yet (first run),
    in which case the consumer should fall back to its auto_offset_reset policy.
    """
    sql = """
        SELECT partition, committed_offset
        FROM kafka_stream_offsets
        WHERE consumer_group = %s AND topic = %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, (consumer_group, topic))
        return {row[0]: row[1] for row in cur.fetchall()}


def commit_offsets(
    conn,
    consumer_group: str,
    topic: str,
    offsets: dict[int, int],
) -> None:
    """Upsert committed offsets into kafka_stream_offsets.

    offsets maps partition → next_offset_to_consume (last_processed + 1).
    Caller must commit the transaction.
    """
    if not offsets:
        return

    sql = """
        INSERT INTO kafka_stream_offsets
            (consumer_group, topic, partition, committed_offset, updated_at)
        VALUES (%s, %s, %s, %s, NOW())
        ON CONFLICT (consumer_group, topic, partition) DO UPDATE
            SET committed_offset = EXCLUDED.committed_offset,
                updated_at       = NOW()
    """
    with conn.cursor() as cur:
        for partition, offset in offsets.items():
            cur.execute(sql, (consumer_group, topic, partition, offset))

    logger.debug(
        "Offsets committed: group=%s topic=%s partitions=%s",
        consumer_group,
        topic,
        offsets,
    )
