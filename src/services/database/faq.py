"""
SyriaBot - Database FAQ Analytics Mixin
=======================================

FAQ usage counters and analytics.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

from typing import Dict, List, Tuple

from src.core.logger import logger


class FAQAnalyticsMixin:
    """Mixin for FAQ analytics database operations."""

    def faq_increment(self, topic: str, metric: str) -> None:
        """Increment a FAQ analytics counter."""
        try:
            with self._get_conn() as conn:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO faq_analytics (topic, metric, count)
                    VALUES (?, ?, 1)
                    ON CONFLICT(topic, metric) DO UPDATE SET count = count + 1
                """, (topic, metric))
        except Exception as e:
            logger.error_tree("DB: FAQ Increment Error", e, [
                ("Topic", topic),
                ("Metric", metric),
            ])

    def faq_get_all_stats(self) -> Dict[str, Dict[str, int]]:
        """
        Get all FAQ stats grouped by metric.

        Returns:
            Dict like {"triggers": {"xp": 5, "roles": 3}, "helpful": {...}, ...}
        """
        try:
            with self._get_conn() as conn:
                cur = conn.cursor()
                cur.execute("SELECT topic, metric, count FROM faq_analytics")
                rows = cur.fetchall()

                stats: Dict[str, Dict[str, int]] = {}
                for row in rows:
                    metric = row["metric"]
                    topic = row["topic"]
                    if metric not in stats:
                        stats[metric] = {}
                    stats[metric][topic] = row["count"]
                return stats
        except Exception as e:
            logger.error_tree("DB: FAQ Get All Stats Error", e)
            return {}

    def faq_get_top(self, metric: str, limit: int = 5) -> List[Tuple[str, int]]:
        """Get top topics by a given metric."""
        try:
            with self._get_conn() as conn:
                cur = conn.cursor()
                cur.execute("""
                    SELECT topic, count FROM faq_analytics
                    WHERE metric = ?
                    ORDER BY count DESC
                    LIMIT ?
                """, (metric, limit))
                return [(row["topic"], row["count"]) for row in cur.fetchall()]
        except Exception as e:
            logger.error_tree("DB: FAQ Get Top Error", e, [
                ("Metric", metric),
            ])
            return []
