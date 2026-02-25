"""
SyriaBot - Fun Service
======================

Handles fun commands like ship, howsimp, howgay with random results.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import random
from typing import Tuple, List

from src.core.logger import logger
from src.core.config import config


# Ship messages based on percentage ranges
SHIP_MESSAGES = {
    (0, 10): [
        "Not meant to be... 💔",
        "Absolutely not happening.",
        "The stars say no.",
    ],
    (10, 25): [
        "Very unlikely...",
        "Maybe in another universe.",
        "The odds are not in your favor.",
    ],
    (25, 40): [
        "There's a small chance...",
        "Stranger things have happened.",
        "Don't give up hope... yet.",
    ],
    (40, 55): [
        "It could work!",
        "There's potential here.",
        "Give it a shot!",
    ],
    (55, 70): [
        "Looking good! 💕",
        "There's definitely chemistry!",
        "The vibes are strong.",
    ],
    (70, 85): [
        "Great match! 💖",
        "You two would be cute together!",
        "The compatibility is real!",
    ],
    (85, 95): [
        "Almost perfect! 💘",
        "Soulmate material!",
        "You're made for each other!",
    ],
    (95, 101): [
        "PERFECT MATCH! 💞",
        "Destiny has spoken! 💗",
        "True love! 💝",
    ],
}

# Simp messages based on percentage
SIMP_MESSAGES = {
    (0, 15): [
        "Not a simp at all.",
        "Completely unbothered.",
        "Chad energy.",
    ],
    (15, 30): [
        "Barely simping.",
        "Mostly in control.",
        "Slight simp tendencies.",
    ],
    (30, 50): [
        "Moderate simp.",
        "Starting to catch feelings.",
        "The simp is showing.",
    ],
    (50, 70): [
        "Certified simp.",
        "Down bad.",
        "The simping is strong.",
    ],
    (70, 85): [
        "Major simp alert!",
        "Extremely down bad.",
        "Professional simp.",
    ],
    (85, 101): [
        "MEGA SIMP! 🥺",
        "Simp level: MAXIMUM",
        "Ultimate simp detected.",
    ],
}

# Gay messages based on percentage
GAY_MESSAGES = {
    (0, 15): [
        "Straight as an arrow.",
        "0% fruity.",
        "Heterosexual vibes.",
    ],
    (15, 30): [
        "Mostly straight.",
        "A little curious maybe?",
        "Straight with a twist.",
    ],
    (30, 50): [
        "Bi vibes detected.",
        "Flexible orientation.",
        "The rainbow is calling.",
    ],
    (50, 70): [
        "Pretty fruity! 🍇",
        "The gay is strong.",
        "Rainbow energy!",
    ],
    (70, 85): [
        "Very gay! 🌈",
        "Certified fruity.",
        "Pride parade ready!",
    ],
    (85, 101): [
        "MAXIMUM GAY! 🏳️‍🌈",
        "Gay level: LEGENDARY",
        "The gayest of them all!",
    ],
}

# Smart messages based on percentage
SMART_MESSAGES = {
    (0, 15): [
        "Smooth brain detected.",
        "IQ: Room temperature.",
        "Not the sharpest tool.",
    ],
    (15, 30): [
        "A bit slow...",
        "Below average intelligence.",
        "Needs some work.",
    ],
    (30, 50): [
        "Average intelligence.",
        "Perfectly normal brain.",
        "Nothing special here.",
    ],
    (50, 70): [
        "Above average! 📚",
        "Pretty smart actually.",
        "Quick learner!",
    ],
    (70, 85): [
        "Very intelligent! 🧠",
        "Big brain energy.",
        "Certified smart!",
    ],
    (85, 101): [
        "GENIUS LEVEL! 🎓",
        "IQ: Off the charts!",
        "Einstein reincarnated!",
    ],
}

# Body fat messages based on percentage
HOWFAT_MESSAGES = {
    (0, 10): [
        "Shredded! 💪",
        "Competition ready.",
        "Veins on veins.",
    ],
    (10, 15): [
        "Very lean!",
        "Abs visible.",
        "Athletic build.",
    ],
    (15, 20): [
        "Fit and healthy.",
        "Good shape!",
        "Looking solid.",
    ],
    (20, 25): [
        "Average build.",
        "Room for improvement.",
        "Dad bod territory.",
    ],
    (25, 35): [
        "A bit fluffy.",
        "Bulk season forever.",
        "Needs some cardio.",
    ],
    (35, 101): [
        "Maximum fluff! 🍔",
        "Cultivating mass.",
        "Hibernation mode.",
    ],
}


def _get_message(messages_dict: dict, percentage: int) -> str:
    """Get a deterministic message based on percentage range."""
    for (low, high), messages in messages_dict.items():
        if low <= percentage < high:
            # Use percentage to pick message deterministically
            return messages[percentage % len(messages)]
    return messages_dict[(85, 101)][0]  # Fallback


class FunService:
    """
    Service for fun commands with deterministic results.

    DESIGN:
        Provides ship/howsimp/howgay calculations with random percentages.
        Special overrides for owner user (0% for self, 100% with specific user).
        Messages are deterministic based on percentage ranges.
    """

    def __init__(self) -> None:
        logger.tree("Fun Service Initialized", [
            ("Commands", "ship, howsimp, howgay"),
        ], emoji="🎮")

    def _random_percentage(self) -> int:
        """Generate a random percentage (0-100) for fun commands."""
        return random.randint(0, 100)

    def calculate_ship(self, user1_id: int, user2_id: int) -> Tuple[int, str]:
        """
        Calculate ship compatibility between two users.

        Args:
            user1_id: First user's ID
            user2_id: Second user's ID

        Returns:
            Tuple of (percentage, message)
        """
        # Special ship override - owner + special user = 100%
        users = {user1_id, user2_id}
        if config.OWNER_ID in users and any(uid in users for uid in config.SHIP_SPECIAL_USER_IDS):
            logger.tree("Ship Calculated", [
                ("User 1", str(user1_id)),
                ("User 2", str(user2_id)),
                ("Result", "100% (special override)"),
            ], emoji="💕")
            return 100, "PERFECT MATCH! 💞"

        # Owner override - anyone shipped with owner = 0%
        if config.OWNER_ID in (user1_id, user2_id):
            logger.tree("Ship Calculated", [
                ("User 1", str(user1_id)),
                ("User 2", str(user2_id)),
                ("Result", "0% (owner override)"),
            ], emoji="💕")
            return 0, "Not meant to be... 💔"

        # Special user override - anyone shipped with special user = 0%
        if user1_id in config.SHIP_SPECIAL_USER_IDS or user2_id in config.SHIP_SPECIAL_USER_IDS:
            logger.tree("Ship Calculated", [
                ("User 1", str(user1_id)),
                ("User 2", str(user2_id)),
                ("Result", "0% (special user override)"),
            ], emoji="💕")
            return 0, "Not meant to be... 💔"

        # Random percentage each time
        percentage = self._random_percentage()
        message = _get_message(SHIP_MESSAGES, percentage)

        logger.tree("Ship Calculated", [
            ("User 1", str(user1_id)),
            ("User 2", str(user2_id)),
            ("Result", f"{percentage}%"),
        ], emoji="💕")

        return percentage, message

    def calculate_howsimp(self, user_id: int, guild_id: int) -> Tuple[int, str]:
        """
        Calculate howsimp level for a user.

        Args:
            user_id: User's ID
            guild_id: Guild ID (for per-server consistency)

        Returns:
            Tuple of (percentage, message)
        """
        # Developer override - not a simp
        if user_id == config.OWNER_ID:
            logger.tree("Howsimp Calculated", [
                ("User", str(user_id)),
                ("Result", "0% (owner override)"),
            ], emoji="🥺")
            return 0, "Not a simp at all."

        percentage = self._random_percentage()
        message = _get_message(SIMP_MESSAGES, percentage)

        logger.tree("Howsimp Calculated", [
            ("User", str(user_id)),
            ("Result", f"{percentage}%"),
        ], emoji="🥺")

        return percentage, message

    def calculate_gay(self, user_id: int, guild_id: int) -> Tuple[int, str]:
        """
        Calculate gay level for a user.

        Args:
            user_id: User's ID
            guild_id: Guild ID (for per-server consistency)

        Returns:
            Tuple of (percentage, message)
        """
        # Developer override
        if user_id == config.OWNER_ID:
            logger.tree("Gay Calculated", [
                ("User", str(user_id)),
                ("Result", "0% (owner override)"),
            ], emoji="🌈")
            return 0, "Straight as an arrow."

        percentage = self._random_percentage()
        message = _get_message(GAY_MESSAGES, percentage)

        logger.tree("Gay Calculated", [
            ("User", str(user_id)),
            ("Result", f"{percentage}%"),
        ], emoji="🌈")

        return percentage, message

    def calculate_smart(self, user_id: int, guild_id: int) -> Tuple[int, str]:
        """
        Calculate smart level for a user.

        Args:
            user_id: User's ID
            guild_id: Guild ID (for per-server consistency)

        Returns:
            Tuple of (percentage, message)
        """
        # Developer override - always genius
        if user_id == config.OWNER_ID:
            logger.tree("Smart Calculated", [
                ("User", str(user_id)),
                ("Result", "100% (owner override)"),
            ], emoji="🧠")
            return 100, "GENIUS LEVEL! 🎓"

        percentage = self._random_percentage()
        message = _get_message(SMART_MESSAGES, percentage)

        logger.tree("Smart Calculated", [
            ("User", str(user_id)),
            ("Result", f"{percentage}%"),
        ], emoji="🧠")

        return percentage, message

    def calculate_howfat(self, user_id: int, guild_id: int) -> Tuple[int, str]:
        """
        Calculate body fat percentage for a user.

        Args:
            user_id: User's ID
            guild_id: Guild ID (for per-server consistency)

        Returns:
            Tuple of (percentage, message)
        """
        # Developer override - shredded
        if user_id == config.OWNER_ID:
            logger.tree("Howfat Calculated", [
                ("User", str(user_id)),
                ("Result", "8% (owner override)"),
            ], emoji="💪")
            return 8, "Shredded! 💪"

        percentage = self._random_percentage()
        message = _get_message(HOWFAT_MESSAGES, percentage)

        logger.tree("Howfat Calculated", [
            ("User", str(user_id)),
            ("Result", f"{percentage}%"),
        ], emoji="💪")

        return percentage, message

    def get_ship_name(self, name1: str, name2: str) -> str:
        """
        Generate a ship name from two names.

        Args:
            name1: First name
            name2: Second name

        Returns:
            Combined ship name
        """
        # Take first half of first name + second half of second name
        half1 = len(name1) // 2
        half2 = len(name2) // 2

        # Try different combinations and pick based on hash
        options = [
            name1[:half1 + 1] + name2[half2:],
            name2[:half2 + 1] + name1[half1:],
            name1[:3] + name2[-3:] if len(name1) >= 3 and len(name2) >= 3 else name1 + name2,
        ]

        # Pick deterministically
        combined = name1.lower() + name2.lower()
        idx = sum(ord(c) for c in combined) % len(options)

        return options[idx].capitalize()


# Singleton instance
fun_service = FunService()
