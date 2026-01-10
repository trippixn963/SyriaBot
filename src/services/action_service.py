"""
SyriaBot - Action Service
=========================

Handles action commands like slap, hug, kiss, etc.
Uses nekos.best API (primary) with waifu.pics fallback for SFW anime GIFs.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import asyncio
import aiohttp
import random
from typing import Optional, Dict, List

from src.core.logger import log


# API endpoints
NEKOS_BEST_API = "https://nekos.best/api/v2"
WAIFU_PICS_API = "https://api.waifu.pics/sfw"

# Actions available on nekos.best (better curated anime content)
NEKOS_BEST_ACTIONS = {
    "slap", "hug", "kiss", "pat", "poke", "bite", "cuddle", "kick",
    "wave", "highfive", "wink", "punch", "yeet", "handhold",
    "cry", "smile", "dance", "blush", "happy", "smug", "tickle",
    "feed", "shoot", "shrug", "stare", "think", "thumbsup", "pout",
    "laugh", "nod", "nom", "nope", "peck", "run", "sleep", "yawn",
    "facepalm", "bored", "angry", "baka", "handshake"
}

# Available actions (target required)
ACTIONS: Dict[str, Dict] = {
    "slap": {
        "endpoint": "slap",
        "messages": [
            "{user} slapped {target}",
            "{user} slaps {target} across the face",
            "{target} got slapped by {user}",
        ]
    },
    "hug": {
        "endpoint": "hug",
        "messages": [
            "{user} hugged {target}",
            "{user} gives {target} a warm hug",
            "{target} received a hug from {user}",
        ]
    },
    "kiss": {
        "endpoint": "kiss",
        "messages": [
            "{user} kissed {target}",
            "{user} gives {target} a kiss",
            "{target} got kissed by {user}",
        ]
    },
    "pat": {
        "endpoint": "pat",
        "messages": [
            "{user} pats {target}",
            "{user} gives {target} head pats",
            "{target} received pats from {user}",
        ]
    },
    "poke": {
        "endpoint": "poke",
        "messages": [
            "{user} poked {target}",
            "{user} pokes {target}",
            "{target} got poked by {user}",
        ]
    },
    "bite": {
        "endpoint": "bite",
        "messages": [
            "{user} bit {target}",
            "{user} bites {target}",
            "{target} got bitten by {user}",
        ]
    },
    "cuddle": {
        "endpoint": "cuddle",
        "messages": [
            "{user} cuddles with {target}",
            "{user} snuggles up to {target}",
            "{target} is being cuddled by {user}",
        ]
    },
    "bonk": {
        "endpoint": "bonk",  # waifu.pics only
        "messages": [
            "{user} bonked {target}",
            "{user} bonks {target} on the head",
            "{target} got bonked by {user}",
        ]
    },
    "kick": {
        "endpoint": "kick",
        "messages": [
            "{user} kicked {target}",
            "{user} kicks {target}",
            "{target} got kicked by {user}",
        ]
    },
    "wave": {
        "endpoint": "wave",
        "messages": [
            "{user} waves at {target}",
            "{user} waves hello to {target}",
            "{target} received a wave from {user}",
        ]
    },
    "highfive": {
        "endpoint": "highfive",
        "messages": [
            "{user} high-fived {target}",
            "{user} gives {target} a high five",
            "{target} high-fived {user}",
        ]
    },
    "wink": {
        "endpoint": "wink",
        "messages": [
            "{user} winked at {target}",
            "{user} winks at {target}",
            "{target} got a wink from {user}",
        ]
    },
    "kill": {
        "endpoint": "kill",  # waifu.pics only
        "messages": [
            "{user} killed {target}",
            "{user} ends {target}",
            "{target} was eliminated by {user}",
        ]
    },
    "lick": {
        "endpoint": "lick",  # waifu.pics only
        "messages": [
            "{user} licked {target}",
            "{user} licks {target}",
            "{target} got licked by {user}",
        ]
    },
    "punch": {
        "endpoint": "punch",
        "messages": [
            "{user} punched {target}",
            "{user} punches {target}",
            "{target} got punched by {user}",
        ]
    },
    "yeet": {
        "endpoint": "yeet",
        "messages": [
            "{user} yeeted {target}",
            "{user} yeets {target} into orbit",
            "{target} got yeeted by {user}",
        ]
    },
    "bully": {
        "endpoint": "bully",  # waifu.pics only
        "messages": [
            "{user} bullied {target}",
            "{user} bullies {target}",
            "{target} got bullied by {user}",
        ]
    },
    "handhold": {
        "endpoint": "handhold",
        "messages": [
            "{user} holds {target}'s hand",
            "{user} and {target} are holding hands",
            "{target}'s hand is held by {user}",
        ]
    },
    "tickle": {
        "endpoint": "tickle",
        "messages": [
            "{user} tickles {target}",
            "{user} tickles {target} mercilessly",
            "{target} got tickled by {user}",
        ]
    },
    "feed": {
        "endpoint": "feed",
        "messages": [
            "{user} feeds {target}",
            "{user} gives {target} some food",
            "{target} got fed by {user}",
        ]
    },
    "shoot": {
        "endpoint": "shoot",
        "messages": [
            "{user} shoots {target}",
            "{user} shot {target}",
            "{target} got shot by {user}",
        ]
    },
    "peck": {
        "endpoint": "peck",
        "messages": [
            "{user} pecks {target}",
            "{user} gives {target} a peck",
            "{target} got a peck from {user}",
        ]
    },
    "stare": {
        "endpoint": "stare",
        "messages": [
            "{user} stares at {target}",
            "{user} is staring at {target}",
            "{target} is being stared at by {user}",
        ]
    },
}

# Self-actions (no target needed)
SELF_ACTIONS: Dict[str, Dict] = {
    "cry": {
        "endpoint": "cry",
        "messages": [
            "{user} is crying",
            "{user} bursts into tears",
            "{user} starts crying",
        ]
    },
    "smile": {
        "endpoint": "smile",
        "messages": [
            "{user} is smiling",
            "{user} smiles happily",
            "{user} has a big smile",
        ]
    },
    "dance": {
        "endpoint": "dance",
        "messages": [
            "{user} is dancing",
            "{user} starts dancing",
            "{user} busts a move",
        ]
    },
    "blush": {
        "endpoint": "blush",
        "messages": [
            "{user} is blushing",
            "{user} blushes",
            "{user} turned red",
        ]
    },
    "happy": {
        "endpoint": "happy",
        "messages": [
            "{user} is happy",
            "{user} looks happy",
            "{user} is feeling great",
        ]
    },
    "smug": {
        "endpoint": "smug",
        "messages": [
            "{user} looks smug",
            "{user} has a smug face",
            "{user} is feeling smug",
        ]
    },
    "laugh": {
        "endpoint": "laugh",
        "messages": [
            "{user} is laughing",
            "{user} bursts out laughing",
            "{user} can't stop laughing",
        ]
    },
    "sleep": {
        "endpoint": "sleep",
        "messages": [
            "{user} is sleeping",
            "{user} fell asleep",
            "{user} is taking a nap",
        ]
    },
    "think": {
        "endpoint": "think",
        "messages": [
            "{user} is thinking",
            "{user} is deep in thought",
            "{user} ponders",
        ]
    },
    "pout": {
        "endpoint": "pout",
        "messages": [
            "{user} is pouting",
            "{user} pouts",
            "{user} looks upset",
        ]
    },
    "shrug": {
        "endpoint": "shrug",
        "messages": [
            "{user} shrugs",
            "{user} doesn't know",
            "{user} shrugged",
        ]
    },
    "facepalm": {
        "endpoint": "facepalm",
        "messages": [
            "{user} facepalms",
            "{user} can't believe it",
            "{user} is disappointed",
        ]
    },
    "angry": {
        "endpoint": "angry",
        "messages": [
            "{user} is angry",
            "{user} looks furious",
            "{user} is mad",
        ]
    },
    "bored": {
        "endpoint": "bored",
        "messages": [
            "{user} is bored",
            "{user} looks bored",
            "{user} has nothing to do",
        ]
    },
    "run": {
        "endpoint": "run",
        "messages": [
            "{user} is running",
            "{user} runs away",
            "{user} started running",
        ]
    },
    "yawn": {
        "endpoint": "yawn",
        "messages": [
            "{user} yawns",
            "{user} is yawning",
            "{user} looks tired",
        ]
    },
    "nod": {
        "endpoint": "nod",
        "messages": [
            "{user} nods",
            "{user} is nodding",
            "{user} agrees",
        ]
    },
    "nope": {
        "endpoint": "nope",
        "messages": [
            "{user} says nope",
            "{user} refuses",
            "{user} is not having it",
        ]
    },
    "thumbsup": {
        "endpoint": "thumbsup",
        "messages": [
            "{user} gives a thumbs up",
            "{user} approves",
            "{user} likes it",
        ]
    },
}


class ActionService:
    """Service for handling action commands."""

    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None
        log.tree("Action Service Initialized", [
            ("Actions", str(len(ACTIONS))),
            ("Self-Actions", str(len(SELF_ACTIONS))),
            ("Primary API", "nekos.best"),
            ("Fallback API", "waifu.pics"),
        ], emoji="🎬")

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        """Close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()
            log.tree("Action Service Closed", [
                ("Status", "Session closed"),
            ], emoji="🛑")

    async def _fetch_from_nekos_best(self, endpoint: str) -> Optional[str]:
        """Fetch GIF from nekos.best API."""
        url = f"{NEKOS_BEST_API}/{endpoint}"
        try:
            session = await self._get_session()
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    data = await response.json()
                    # nekos.best returns {"results": [{"url": "..."}]}
                    results = data.get("results", [])
                    if results and results[0].get("url"):
                        return results[0]["url"]
        except asyncio.TimeoutError:
            log.tree("Nekos.best API Timeout", [
                ("Endpoint", endpoint),
                ("URL", url),
            ], emoji="⏳")
        except Exception as e:
            log.tree("Nekos.best API Error", [
                ("Endpoint", endpoint),
                ("Error", str(e)[:80]),
            ], emoji="⚠️")
        return None

    async def _fetch_from_waifu_pics(self, endpoint: str) -> Optional[str]:
        """Fetch GIF from waifu.pics API."""
        url = f"{WAIFU_PICS_API}/{endpoint}"
        try:
            session = await self._get_session()
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    data = await response.json()
                    # waifu.pics returns {"url": "..."}
                    return data.get("url")
        except asyncio.TimeoutError:
            log.tree("Waifu.pics API Timeout", [
                ("Endpoint", endpoint),
                ("URL", url),
            ], emoji="⏳")
        except Exception as e:
            log.tree("Waifu.pics API Error", [
                ("Endpoint", endpoint),
                ("Error", str(e)[:80]),
            ], emoji="⚠️")
        return None

    async def get_action_gif(self, action: str) -> Optional[str]:
        """
        Fetch a random GIF URL for the given action.
        Uses nekos.best as primary (better curated), waifu.pics as fallback.

        Args:
            action: The action name (slap, hug, etc.)

        Returns:
            GIF URL or None if failed
        """
        # Get endpoint for action
        action_data = ACTIONS.get(action) or SELF_ACTIONS.get(action)
        if not action_data:
            log.tree("Action Unknown", [
                ("Action", action),
                ("Reason", "Not in ACTIONS or SELF_ACTIONS"),
            ], emoji="⚠️")
            return None

        endpoint = action_data["endpoint"]
        gif_url = None
        source = None

        # Try nekos.best first (better curated anime content)
        if endpoint in NEKOS_BEST_ACTIONS:
            gif_url = await self._fetch_from_nekos_best(endpoint)
            if gif_url:
                source = "nekos.best"

        # Fallback to waifu.pics
        if not gif_url:
            gif_url = await self._fetch_from_waifu_pics(endpoint)
            if gif_url:
                source = "waifu.pics"

        if gif_url:
            log.tree("Action GIF Fetched", [
                ("Action", action),
                ("Endpoint", endpoint),
                ("Source", source),
            ], emoji="🎬")
            return gif_url

        log.tree("Action GIF Failed", [
            ("Action", action),
            ("Endpoint", endpoint),
            ("Reason", "Both APIs failed"),
        ], emoji="⚠️")
        return None

    def get_action_message(self, action: str, user: str, target: Optional[str] = None) -> str:
        """
        Get a random message for the action.

        Args:
            action: The action name
            user: The user performing the action
            target: The target of the action (None for self-actions)

        Returns:
            Formatted message string
        """
        action_data = ACTIONS.get(action) or SELF_ACTIONS.get(action)
        if not action_data:
            return f"{user} used {action}"

        message_template = random.choice(action_data["messages"])

        if target:
            return message_template.format(user=user, target=target)
        elif "{target}" in message_template:
            # Target action used as self-action (e.g., "hug" alone)
            return message_template.format(user=user, target="themselves")
        else:
            return message_template.format(user=user)

    def is_action(self, word: str) -> bool:
        """Check if a word is a valid action."""
        return word.lower() in ACTIONS or word.lower() in SELF_ACTIONS

    def is_target_action(self, word: str) -> bool:
        """Check if an action requires a target."""
        return word.lower() in ACTIONS

    def is_self_action(self, word: str) -> bool:
        """Check if an action is self-targeted."""
        return word.lower() in SELF_ACTIONS

    def get_all_actions(self) -> List[str]:
        """Get list of all available actions."""
        return list(ACTIONS.keys()) + list(SELF_ACTIONS.keys())


# Singleton instance
action_service = ActionService()
