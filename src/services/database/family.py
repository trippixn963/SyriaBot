"""
SyriaBot - Database Family Mixin
================================

Family system database operations (marriages, adoptions, divorce cooldowns).

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import time
from typing import Optional, List

from src.core.logger import logger


class FamilyMixin:
    """
    Mixin for family system database operations.

    DESIGN:
        - Marriages stored as two rows (A→B and B→A) for fast lookups.
        - Adoptions stored as one row per parent-child pair (PK on child).
        - Divorce cooldowns tracked separately for 24h remarry restriction.
    """

    # =========================================================================
    # Marriages
    # =========================================================================

    def marry(self, user1_id: int, user2_id: int, guild_id: int) -> None:
        """Create a marriage between two users (inserts both directions)."""
        now = int(time.time())

        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO family_marriages (user_id, spouse_id, guild_id, married_at)
                VALUES (?, ?, ?, ?)
            """, (user1_id, user2_id, guild_id, now))
            cur.execute("""
                INSERT INTO family_marriages (user_id, spouse_id, guild_id, married_at)
                VALUES (?, ?, ?, ?)
            """, (user2_id, user1_id, guild_id, now))

        logger.tree("Marriage Created", [
            ("User 1", str(user1_id)),
            ("User 2", str(user2_id)),
            ("Guild", str(guild_id)),
        ], emoji="💍")

    def divorce(self, user_id: int, guild_id: int) -> Optional[int]:
        """Divorce a user. Returns the ex-spouse ID or None if not married."""
        with self._get_conn() as conn:
            cur = conn.cursor()

            # Get spouse first
            cur.execute("""
                SELECT spouse_id FROM family_marriages
                WHERE user_id = ? AND guild_id = ?
            """, (user_id, guild_id))
            row = cur.fetchone()

            if not row:
                return None

            spouse_id = row["spouse_id"]

            # Delete both directions
            cur.execute("""
                DELETE FROM family_marriages
                WHERE guild_id = ? AND (
                    (user_id = ? AND spouse_id = ?) OR
                    (user_id = ? AND spouse_id = ?)
                )
            """, (guild_id, user_id, spouse_id, spouse_id, user_id))

            # Set cooldown for both users
            now = int(time.time())
            cur.execute("""
                INSERT INTO family_divorce_cooldowns (user_id, guild_id, divorced_at)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, guild_id) DO UPDATE SET divorced_at = ?
            """, (user_id, guild_id, now, now))
            cur.execute("""
                INSERT INTO family_divorce_cooldowns (user_id, guild_id, divorced_at)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, guild_id) DO UPDATE SET divorced_at = ?
            """, (spouse_id, guild_id, now, now))

        logger.tree("Divorce Completed", [
            ("User", str(user_id)),
            ("Ex-Spouse", str(spouse_id)),
            ("Guild", str(guild_id)),
        ], emoji="💔")

        return spouse_id

    def get_spouse(self, user_id: int, guild_id: int) -> Optional[int]:
        """Get the spouse ID for a user, or None if not married."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT spouse_id FROM family_marriages
                WHERE user_id = ? AND guild_id = ?
            """, (user_id, guild_id))
            row = cur.fetchone()
            return row["spouse_id"] if row else None

    def get_divorce_cooldown(self, user_id: int, guild_id: int) -> Optional[int]:
        """Get the divorced_at timestamp, or None if no cooldown."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT divorced_at FROM family_divorce_cooldowns
                WHERE user_id = ? AND guild_id = ?
            """, (user_id, guild_id))
            row = cur.fetchone()
            return row["divorced_at"] if row else None

    # =========================================================================
    # Adoptions
    # =========================================================================

    def adopt(self, parent_id: int, child_id: int, guild_id: int) -> None:
        """Create a parent-child relationship."""
        now = int(time.time())

        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT OR IGNORE INTO family_adoptions (parent_id, child_id, guild_id, adopted_at)
                VALUES (?, ?, ?, ?)
            """, (parent_id, child_id, guild_id, now))

        logger.tree("Adoption Created", [
            ("Parent", str(parent_id)),
            ("Child", str(child_id)),
            ("Guild", str(guild_id)),
        ], emoji="👨‍👧")

    def disown(self, parent_id: int, child_id: int, guild_id: int) -> bool:
        """Remove a child from a parent. Returns True if deleted."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                DELETE FROM family_adoptions
                WHERE parent_id = ? AND child_id = ? AND guild_id = ?
            """, (parent_id, child_id, guild_id))
            deleted = cur.rowcount > 0

        if deleted:
            logger.tree("Child Disowned", [
                ("Parent", str(parent_id)),
                ("Child", str(child_id)),
                ("Guild", str(guild_id)),
            ], emoji="👋")

        return deleted

    def runaway(self, child_id: int, guild_id: int) -> Optional[int]:
        """Child removes themselves from their parent. Returns parent ID or None."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT parent_id FROM family_adoptions
                WHERE child_id = ? AND guild_id = ?
            """, (child_id, guild_id))
            row = cur.fetchone()

            if not row:
                return None

            parent_id = row["parent_id"]

            cur.execute("""
                DELETE FROM family_adoptions
                WHERE child_id = ? AND guild_id = ?
            """, (child_id, guild_id))

        logger.tree("Child Ran Away", [
            ("Child", str(child_id)),
            ("Parent", str(parent_id)),
            ("Guild", str(guild_id)),
        ], emoji="🏃")

        return parent_id

    def get_parent(self, user_id: int, guild_id: int) -> Optional[int]:
        """Get the parent ID for a user, or None."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT parent_id FROM family_adoptions
                WHERE child_id = ? AND guild_id = ?
            """, (user_id, guild_id))
            row = cur.fetchone()
            return row["parent_id"] if row else None

    def get_children(self, user_id: int, guild_id: int) -> List[int]:
        """Get list of child IDs for a user."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT child_id FROM family_adoptions
                WHERE parent_id = ? AND guild_id = ?
                ORDER BY adopted_at ASC
            """, (user_id, guild_id))
            return [row["child_id"] for row in cur.fetchall()]

    def get_children_count(self, user_id: int, guild_id: int) -> int:
        """Get number of children for a user."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT COUNT(*) as cnt FROM family_adoptions
                WHERE parent_id = ? AND guild_id = ?
            """, (user_id, guild_id))
            return cur.fetchone()["cnt"]

    def get_household_children(self, user_id: int, guild_id: int) -> List[int]:
        """Get merged, deduplicated children for user + spouse."""
        children = self.get_children(user_id, guild_id)
        spouse_id = self.get_spouse(user_id, guild_id)
        if spouse_id:
            spouse_children = self.get_children(spouse_id, guild_id)
            children = list(dict.fromkeys(children + spouse_children))
        return children

    def get_household_children_count(self, user_id: int, guild_id: int) -> int:
        """Get total children count for user + spouse (deduplicated)."""
        return len(self.get_household_children(user_id, guild_id))

    # =========================================================================
    # Cleanup (member leave)
    # =========================================================================

    def cleanup_family_on_leave(self, user_id: int, guild_id: int) -> dict:
        """
        Clean up all family data for a user who left the server.

        Returns dict with counts of cleaned records.
        """
        result = {"divorces": 0, "orphaned_children": 0, "removed_from_parent": 0}

        with self._get_conn() as conn:
            cur = conn.cursor()

            # Divorce if married
            cur.execute("""
                SELECT spouse_id FROM family_marriages
                WHERE user_id = ? AND guild_id = ?
            """, (user_id, guild_id))
            row = cur.fetchone()
            if row:
                spouse_id = row["spouse_id"]
                cur.execute("""
                    DELETE FROM family_marriages
                    WHERE guild_id = ? AND (
                        (user_id = ? AND spouse_id = ?) OR
                        (user_id = ? AND spouse_id = ?)
                    )
                """, (guild_id, user_id, spouse_id, spouse_id, user_id))
                result["divorces"] = 1

            # Free children (remove parent link)
            cur.execute("""
                DELETE FROM family_adoptions
                WHERE parent_id = ? AND guild_id = ?
            """, (user_id, guild_id))
            result["orphaned_children"] = cur.rowcount

            # Remove from own parent
            cur.execute("""
                DELETE FROM family_adoptions
                WHERE child_id = ? AND guild_id = ?
            """, (user_id, guild_id))
            result["removed_from_parent"] = cur.rowcount

            # Clean divorce cooldowns
            cur.execute("""
                DELETE FROM family_divorce_cooldowns
                WHERE user_id = ? AND guild_id = ?
            """, (user_id, guild_id))

        return result

    # =========================================================================
    # Date-aware queries
    # =========================================================================

    def get_marriage_timestamp(self, user_id: int, guild_id: int) -> Optional[int]:
        """Get the married_at timestamp for a user, or None."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT married_at FROM family_marriages
                WHERE user_id = ? AND guild_id = ?
            """, (user_id, guild_id))
            row = cur.fetchone()
            return row["married_at"] if row else None

    def get_adoption_timestamp(self, child_id: int, guild_id: int) -> Optional[int]:
        """Get the adopted_at timestamp for a child, or None."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT adopted_at FROM family_adoptions
                WHERE child_id = ? AND guild_id = ?
            """, (child_id, guild_id))
            row = cur.fetchone()
            return row["adopted_at"] if row else None

    # =========================================================================
    # Cooldown cleanup
    # =========================================================================

    def delete_divorce_cooldown(self, user_id: int, guild_id: int) -> None:
        """Delete a specific user's divorce cooldown."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                DELETE FROM family_divorce_cooldowns
                WHERE user_id = ? AND guild_id = ?
            """, (user_id, guild_id))

    # =========================================================================
    # Siblings
    # =========================================================================

    def is_ancestor(self, target_id: int, user_id: int, guild_id: int, max_depth: int = 20) -> bool:
        """Check if target_id is an ancestor of user_id by walking the parent chain."""
        current = user_id
        for _ in range(max_depth):
            parent: Optional[int] = self.get_parent(current, guild_id)
            if parent is None:
                break
            if parent == target_id:
                return True
            current = parent
        return False

    # =========================================================================
    # Siblings
    # =========================================================================

    def get_siblings(self, user_id: int, guild_id: int) -> List[int]:
        """Get sibling IDs (other children of the same parent, excluding self)."""
        parent_id = self.get_parent(user_id, guild_id)
        if not parent_id:
            return []
        children = self.get_children(parent_id, guild_id)
        # Also include spouse's children
        spouse_id = self.get_spouse(parent_id, guild_id)
        if spouse_id:
            spouse_children = self.get_children(spouse_id, guild_id)
            children = list(dict.fromkeys(children + spouse_children))
        return [c for c in children if c != user_id]
